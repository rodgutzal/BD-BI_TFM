"""Tests de la herramienta del estudio de riesgo de cierre (`tools/validate_closure_risk.py`, fase 4, protocolo 3.M).

Datos sintéticos: ninguno lee `data/osm_history/` ni `data/mobility.db`. La verificación real de la descarga se prueba en
`tests/test_download_osm_history.py` y la lectura única en `tests/test_closure_labels.py`.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import closure_features, closure_labels, closure_validation, grid  # noqa: E402
from tools import build_closure_labels as etiquetas_tool  # noqa: E402
from tools import download_osm_history as dh  # noqa: E402
from tools import validate_closure_risk as estudio_tool  # noqa: E402

REPETICIONES, REMUESTREOS = 2, 30  # pocas, para que los tests sean rápidos (el estudio real usa 10 y 2.000)


@pytest.fixture(autouse=True)
def sin_tocar_docs(tmp_path_factory, monkeypatch):
    """Ningún test puede escribir en `docs/`: el destino por defecto apunta a una carpeta temporal y se vigila el archivo real."""
    monkeypatch.setattr(estudio_tool, "RESULTADO_POR_DEFECTO", tmp_path_factory.mktemp("docs") / "RESULTADO.json")
    real = ROOT / "docs" / "RESULTADO_RIESGO_CIERRE.json"
    antes = real.read_bytes() if real.exists() else None
    yield
    assert (
        real.read_bytes() if real.exists() else None
    ) == antes, "un test ha modificado docs/RESULTADO_RIESGO_CIERRE.json"


def local(ident, lat, lon, nombre=None, **extra):
    return {
        "type": "node",
        "id": ident,
        "lat": lat,
        "lon": lon,
        "tags": {"amenity": "cafe", "name": nombre or f"Local {ident}", **extra},
    }


def fotos_sinteticas(n=400, fuertes=60, supervivientes=180, semilla=0):
    """2022: `n` cafés repartidos por el interior de la rejilla. Hoy: `supervivientes` siguen igual; `fuertes` tienen marca de
    ciclo de vida (cierre explícito); el resto no figura (probable). 2024: la misma foto que 2022."""
    rng = np.random.default_rng(semilla)
    lats = rng.uniform(grid.SOUTH + 0.007, grid.NORTH - 0.007, n)
    lons = rng.uniform(grid.WEST + 0.009, grid.EAST - 0.009, n)
    antes = [local(i, lats[i], lons[i]) for i in range(n)]
    hoy = [local(i, lats[i], lons[i]) for i in range(supervivientes)]
    ciclo = [
        {
            "type": "node",
            "id": i,
            "lat": lats[i],
            "lon": lons[i],
            "tags": {"disused:amenity": "cafe", "name": f"Local {i}"},
        }
        for i in range(supervivientes, supervivientes + fuertes)
    ]
    return {"2022": antes, "2024": list(antes), "hoy": hoy, "ciclo": ciclo}, list(zip(lats, lons))


def foursquare_de(puntos, cuantos=40):
    return pd.DataFrame(
        [(f"Local {i}", lat, lon) for i, (lat, lon) in enumerate(puntos[:cuantos])],
        columns=["name", "latitude", "longitude"],
    )


@pytest.fixture(scope="module")
def estudio_completo():
    fotos, puntos = fotos_sinteticas()
    resultado = estudio_tool.estudio(
        fotos, foursquare_de(puntos), puntos, n_remuestreos=REMUESTREOS, repeticiones=REPETICIONES
    )
    return fotos, puntos, resultado


# ---- el estudio -------------------------------------------------------------------------------------------------------------
def test_el_estudio_aplica_primero_la_puerta_y_despues_entrena(estudio_completo):
    _, _, r = estudio_completo
    assert r["puerta"]["pasa"] and r["protocolo"].endswith("(v2.3)")
    assert r["principal"]["positivos"] == r["puerta"]["cierres_principales"]
    assert r["principal"]["n"] == r["puerta"]["cierres_principales"] + r["puerta"]["por_nivel"]["superviviente"]
    assert set(r["principal"]["auc"]) == set(closure_validation.MODELOS)
    assert r["conclusion"].startswith(("señal de entorno UTILIZABLE", "NO utilizable"))
    assert r["principal"]["utilizable"] == r["conclusion"].startswith("señal de entorno UTILIZABLE")


def test_los_descriptivos_se_ejecutan_con_al_menos_30_positivos_y_la_c_nunca(estudio_completo):
    _, _, r = estudio_completo
    d = r["descriptivos"]
    assert set(d) == {"A_solo_fuertes", "control_2024_a_hoy", "B_con_foursquare", "C_contexto_estatico_2022"}
    for nombre in ("A_solo_fuertes", "control_2024_a_hoy", "B_con_foursquare"):
        assert d[nombre]["ejecutado"] and d[nombre]["positivos"] >= 30, nombre
    assert d["A_solo_fuertes"]["positivos"] == 60  # los 60 con marca de ciclo de vida
    assert (
        d["C_contexto_estatico_2022"]["ejecutado"] is False
        and "no se ha descargado" in d["C_contexto_estatico_2022"]["motivo"]
    )


def test_los_descriptivos_no_influyen_en_la_conclusion(estudio_completo, monkeypatch):
    fotos, puntos, r = estudio_completo
    monkeypatch.setattr(
        estudio_tool, "_descriptivo", lambda *a, **k: {"ejecutado": False, "motivo": "anulado", "positivos": 0}
    )
    sin = estudio_tool.estudio(
        fotos, foursquare_de(puntos), puntos, n_remuestreos=REMUESTREOS, repeticiones=REPETICIONES
    )
    assert sin["conclusion"] == r["conclusion"] and sin["principal"] == r["principal"]


def test_la_sensibilidad_a_usa_solo_fuertes_contra_supervivientes(estudio_completo):
    _, _, r = estudio_completo
    a = r["descriptivos"]["A_solo_fuertes"]
    assert (
        a["positivos"] == r["puerta"]["por_nivel"]["fuerte"]
        and a["n"] == a["positivos"] + r["puerta"]["por_nivel"]["superviviente"]
    )


def test_cada_analisis_calcula_las_variables_con_la_foto_de_su_instante_de_partida(monkeypatch):
    fotos, puntos = fotos_sinteticas()
    fotos["2024"] = fotos["2024"][:250]  # distinta de 2022, para distinguirlas
    vistas = []
    original = closure_features.variables

    def espia(poblacion, elementos):
        vistas.append(len(list(elementos)))
        return original(poblacion, elementos)

    monkeypatch.setattr(closure_features, "variables", espia)
    estudio_tool.estudio(fotos, foursquare_de(puntos), puntos, n_remuestreos=REMUESTREOS, repeticiones=REPETICIONES)
    # principal, A y B con la foto de 2022 (400 elementos); el control de 2024 con la suya (250)
    assert vistas == [400, 400, 250, 400]


def test_el_control_de_2024_mide_los_cierres_entre_2024_y_hoy(monkeypatch):
    fotos, puntos = fotos_sinteticas()
    capturado = {}
    original = closure_labels.etiquetar

    def espia(antes, hoy, ciclo):
        capturado.setdefault("llamadas", []).append((len(antes), len(hoy), len(ciclo)))
        return original(antes, hoy, ciclo)

    monkeypatch.setattr(closure_labels, "etiquetar", espia)
    estudio_tool.estudio(fotos, foursquare_de(puntos), puntos, n_remuestreos=REMUESTREOS, repeticiones=REPETICIONES)
    assert capturado["llamadas"] == [(400, 180, 60), (400, 180, 60)]  # 2022 → hoy y 2024 → hoy


def test_un_descriptivo_con_menos_de_30_positivos_no_se_ejecuta_y_se_informa_del_recuento():
    fotos, puntos = fotos_sinteticas(fuertes=12)
    r = estudio_tool.estudio(fotos, foursquare_de(puntos), puntos, n_remuestreos=REMUESTREOS, repeticiones=REPETICIONES)
    a = r["descriptivos"]["A_solo_fuertes"]
    assert a == {"ejecutado": False, "motivo": "solo 12 positivos (mínimo 30)", "positivos": 12}
    assert r["principal"] is not None  # el análisis principal no depende de los descriptivos


def test_sin_datos_de_foursquare_la_b_no_se_ejecuta_y_se_dice():
    fotos, puntos = fotos_sinteticas()
    for vacio in (None, pd.DataFrame(columns=["name", "latitude", "longitude"])):
        r = estudio_tool.estudio(fotos, vacio, puntos, n_remuestreos=REMUESTREOS, repeticiones=REPETICIONES)
        assert r["descriptivos"]["B_con_foursquare"] == {"ejecutado": False, "motivo": "no hay datos de Foursquare"}


def test_si_no_se_cumple_la_puerta_no_se_entrena_y_el_resultado_es_no_concluyente(monkeypatch):
    fotos, puntos = fotos_sinteticas(n=60, fuertes=3, supervivientes=50)
    monkeypatch.setattr(
        closure_validation, "evaluar", lambda *a, **k: pytest.fail("no debe entrenar sin cumplir la puerta")
    )
    r = estudio_tool.estudio(fotos, foursquare_de(puntos), puntos, n_remuestreos=REMUESTREOS, repeticiones=REPETICIONES)
    assert r["principal"] is None and not r["puerta"]["pasa"]
    assert r["conclusion"].startswith("no concluyente: no se entrena") and "descriptivos" not in r


def test_el_resultado_no_contiene_nombres_posiciones_ni_identificadores(estudio_completo):
    _, _, r = estudio_completo
    texto = json.dumps(r, ensure_ascii=False)
    assert "Local " not in texto and '"lat"' not in texto and '"lon"' not in texto and '"id"' not in texto
    assert len(texto) < 20_000  # agregados, no una fila por local


def test_preparar_descarta_los_dudosos_y_alinea_variables_etiqueta_y_celda():
    antes = [
        local(1, grid.SOUTH + 0.02, grid.WEST + 0.03),
        local(2, grid.SOUTH + 0.04, grid.WEST + 0.05),
        local(3, grid.SOUTH + 0.06, grid.WEST + 0.07),
    ]
    hoy = [local(2, antes[1]["lat"], antes[1]["lon"]), local(3, antes[2]["lat"], antes[2]["lon"], nombre="Otro nombre")]
    etiquetas, _ = closure_labels.etiquetar(antes, hoy, [])
    assert sorted(zip(etiquetas["id"], etiquetas["nivel"].astype(str))) == [
        (1, "probable"),
        (2, "superviviente"),
        (3, "dudoso"),
    ]
    t, X, y, filas, cols = estudio_tool.preparar(etiquetas, antes, "cierre_principal")
    assert (
        list(t["id"]) == [1, 2]
        and list(y) == [1, 0]
        and len(X) == 2
        and list(X.columns) == list(closure_features.COLUMNAS)
    )
    esperada_f, esperada_c = grid.cell_index(t["lat"].to_numpy(), t["lon"].to_numpy())
    assert list(filas) == list(esperada_f) and list(cols) == list(esperada_c) and y.dtype.kind == "i"


# ---- imprimir y main --------------------------------------------------------------------------------------------------------
def test_imprimir_muestra_la_puerta_los_modelos_la_decision_y_los_descriptivos(estudio_completo, capsys):
    _, _, r = estudio_completo
    estudio_tool.imprimir(r)
    salida = capsys.readouterr().out
    for esperado in (
        "Puerta:",
        "ANÁLISIS PRINCIPAL",
        "logistica",
        "boosting",
        "solo_categoria",
        "solo_densidad",
        "mejor línea base trivial",
        "CONCLUSIÓN",
        "DESCRIPTIVOS",
        "no ejecutado",
    ):
        assert esperado in salida, esperado


def test_imprimir_con_la_puerta_sin_cumplir_solo_da_la_conclusion(capsys):
    estudio_tool.imprimir(
        {
            "puerta": {"cierres_principales": 3, "bloques_con_cierre": 2, "veredicto": "no concluyente: no se entrena"},
            "principal": None,
            "conclusion": "no concluyente: no se entrena",
        }
    )
    salida = capsys.readouterr().out
    assert "CONCLUSIÓN: no concluyente" in salida and "ANÁLISIS PRINCIPAL" not in salida


def _simula_main(monkeypatch, tmp_path, fotos, puntos, con_foursquare=True):
    hashes = {f"f{i}.json": f"{i:064x}" for i in range(7)}
    monkeypatch.setattr(dh, "cargar_huella", lambda ruta: {"archivos": {}})
    llamadas = []
    monkeypatch.setattr(
        etiquetas_tool,
        "fotos_verificadas",
        lambda out_dir, huella: llamadas.append((out_dir, huella)) or (fotos, hashes),
    )
    monkeypatch.setattr(estudio_tool.data_access, "load_pois_foursquare", lambda db: foursquare_de(puntos))
    monkeypatch.setattr(
        estudio_tool,
        "build_search_points",
        lambda *a: {f"p{i}": type("P", (), {"latitude": la, "longitude": lo})() for i, (la, lo) in enumerate(puntos)},
    )
    real = closure_validation.evaluar
    monkeypatch.setattr(
        closure_validation,
        "evaluar",
        lambda *a, **k: real(*a, **{**k, "repeticiones": REPETICIONES, "n_remuestreos": REMUESTREOS}),
    )
    db = tmp_path / "base.db"
    if con_foursquare:
        db.write_text("x")
    return llamadas, hashes, db


def test_main_lee_por_la_via_verificada_imprime_y_no_escribe_sin_guardar(tmp_path, monkeypatch, capsys):
    fotos, puntos = fotos_sinteticas()
    llamadas, _, db = _simula_main(monkeypatch, tmp_path, fotos, puntos)
    assert estudio_tool.main(["--out", str(tmp_path), "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert llamadas == [(tmp_path, {"archivos": {}})] and "ANÁLISIS PRINCIPAL" in salida and "CONCLUSIÓN" in salida
    assert not estudio_tool.RESULTADO_POR_DEFECTO.exists()


def test_main_con_guardar_escribe_solo_agregados_y_los_sha256_de_las_entradas(tmp_path, monkeypatch):
    fotos, puntos = fotos_sinteticas()
    _, hashes, db = _simula_main(monkeypatch, tmp_path, fotos, puntos)
    destino = tmp_path / "resultado.json"
    assert estudio_tool.main(["--out", str(tmp_path), "--db", str(db), "--guardar", "--destino", str(destino)]) == 0
    datos = json.loads(destino.read_text(encoding="utf-8"))
    assert datos["entradas_sha256"] == hashes and datos["protocolo"].endswith("(v2.3)")
    assert "Local " not in destino.read_text(encoding="utf-8")
    assert not estudio_tool.RESULTADO_POR_DEFECTO.exists()  # con --destino no se toca el de por defecto


def test_main_con_guardar_sin_destino_usa_el_de_por_defecto(tmp_path, monkeypatch):
    fotos, puntos = fotos_sinteticas()
    _, _, db = _simula_main(monkeypatch, tmp_path, fotos, puntos)
    assert estudio_tool.main(["--out", str(tmp_path), "--db", str(db), "--guardar"]) == 0
    assert json.loads(estudio_tool.RESULTADO_POR_DEFECTO.read_text(encoding="utf-8"))["puerta"]["pasa"]


def test_main_sin_la_base_de_foursquare_sigue_y_dice_que_la_b_no_se_ejecuta(tmp_path, monkeypatch, capsys):
    fotos, puntos = fotos_sinteticas()
    _, _, db = _simula_main(monkeypatch, tmp_path, fotos, puntos, con_foursquare=False)
    assert estudio_tool.main(["--out", str(tmp_path), "--db", str(db)]) == 0
    assert "B_con_foursquare: no ejecutado (no hay datos de Foursquare)" in capsys.readouterr().out


def test_main_se_niega_si_la_verificacion_falla_y_no_estudia_nada(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(dh, "cargar_huella", lambda ruta: {"archivos": {}})

    def niega(out_dir, huella):
        raise ValueError("Los datos no son utilizables para el análisis: hoy_0.json: no está verificado")

    monkeypatch.setattr(etiquetas_tool, "fotos_verificadas", niega)
    monkeypatch.setattr(
        estudio_tool, "estudio", lambda *a, **k: pytest.fail("no debe estudiar con datos sin verificar")
    )
    assert estudio_tool.main(["--out", str(tmp_path)]) == 1
    assert "no son utilizables" in capsys.readouterr().out


def test_main_con_la_verificacion_real_rechaza_datos_sin_verificar(tmp_path, monkeypatch, capsys):
    """Sin doble de la verificación: archivos y manifiesto sin `verificacion` los rechaza la función real."""
    rutas = {}
    for nombre, franja, _, _ in dh.plan():
        archivo = f"{nombre}_{franja}.json"
        rutas[archivo] = tmp_path / archivo
        rutas[archivo].write_text(json.dumps({"elements": []}), encoding="utf-8")
    manifiesto = {
        "archivos": {
            a: {"sha256": dh.sha256_de(r), "elementos": 0, "fecha_pedida": None, "espejo": "x"}
            for a, r in rutas.items()
        }
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    monkeypatch.setattr(dh, "cargar_huella", lambda ruta: {"archivos": {}})
    monkeypatch.setattr(
        estudio_tool, "estudio", lambda *a, **k: pytest.fail("no debe estudiar con datos sin verificar")
    )
    assert estudio_tool.main(["--out", str(tmp_path)]) == 1
    assert "no está verificado como completo" in capsys.readouterr().out


def test_main_sin_huella_se_niega(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(dh, "cargar_huella", lambda ruta: None)
    monkeypatch.setattr(estudio_tool, "estudio", lambda *a, **k: pytest.fail("no debe estudiar sin huella"))
    assert estudio_tool.main(["--out", str(tmp_path)]) == 1
    assert "falta docs/HUELLA_OSM_HISTORY.json" in capsys.readouterr().out


@pytest.mark.parametrize("utilizable", [True, False])
def test_la_conclusion_sale_solo_del_analisis_principal_y_con_el_texto_fijado(monkeypatch, utilizable):
    """Los descriptivos corren después y no pueden tocar la conclusión: se comprueba el texto exacto."""
    fotos, puntos = fotos_sinteticas()
    stub = {"utilizable": utilizable, "auc": {}, "decision": {}}
    monkeypatch.setattr(closure_validation, "evaluar", lambda *a, **k: dict(stub))
    r = estudio_tool.estudio(fotos, foursquare_de(puntos), puntos, n_remuestreos=REMUESTREOS, repeticiones=REPETICIONES)
    esperado = (
        "señal de entorno UTILIZABLE según la regla fijada (pasaría a un PR aparte con su revisión)"
        if utilizable
        else "NO utilizable: ningún candidato cumple la regla fijada; queda como hallazgo del TFM y no se expone nada al usuario"
    )
    assert r["conclusion"] == esperado and "descriptivos" in r
