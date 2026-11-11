"""Tests de la fase 2a: panorama por celda (src/ml/panorama.py) — lentes con percentiles y confianza, brecha exploratoria
etiquetada, archivos de salida con manifiesto, reconstrucción de los conteos para recalcular con otro perfil y la
herramienta tools/build_panorama.py."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.locations import LOCATIONS  # noqa: E402
from src.ml import business_profiles as bp  # noqa: E402
from src.ml import grid, inputs_bundle, panorama, validation  # noqa: E402
from src.ml.cell_counts import CellCounts  # noqa: E402
from src.ml.lenses import compute_lenses  # noqa: E402

_s = importlib.util.spec_from_file_location("build_panorama", ROOT / "tools" / "build_panorama.py")
bpn = importlib.util.module_from_spec(_s)
_s.loader.exec_module(bpn)

PERFIL = bp.get_default_profile("food_drink")


def punto(fila, col, cat, sub):
    lat, lon = grid.cell_center(fila, col)
    return {"category": cat, "subcategory": sub, "latitude": float(lat), "longitude": float(lon)}


def pois_sinteticos(n=400, seed=0):
    """POIs repartidos en una zona de 20×20 celdas, con restauración, comercio, colegios y contexto de OSM."""
    rng = np.random.default_rng(seed)
    filas = []
    for _ in range(n):
        f, c = 20 + int(rng.integers(0, 20)), 12 + int(rng.integers(0, 20))
        r = rng.random()
        if r < 0.35:
            filas.append(punto(f, c, "food_drink", "restaurant"))
        elif r < 0.55:
            filas.append(punto(f, c, "business", "bakery"))
        elif r < 0.65:
            filas.append(punto(f, c, "school", "school"))
        elif r < 0.75:
            filas.append(punto(f, c, "leisure", "museum"))
        elif r < 0.9:
            filas.append(punto(f, c, "edificio", "apartments"))
        else:
            filas.append(punto(f, c, "alojamiento", "hotel"))
    return pd.DataFrame(filas)


@pytest.fixture(scope="module")
def counts():
    return CellCounts.from_pois(pois_sinteticos())


# ---- reconstrucción de los conteos -------------------------------------------------------------------------------
def test_from_frame_es_la_inversa_de_to_frame(counts):
    """Reconstruir los conteos desde la tabla da las mismas matrices en las celdas de la tabla."""
    mascara = counts.active_mask()
    de_tabla = CellCounts.from_frame(counts.to_frame(mascara))
    assert set(de_tabla.arrays) == set(counts.arrays)
    for clave, matriz in counts.arrays.items():
        np.testing.assert_array_equal(de_tabla.arrays[clave][mascara], matriz[mascara])


def test_las_lentes_recalculadas_desde_la_tabla_son_identicas(counts):
    """Con los conteos reconstruidos desde toda celda con algún conteo, cada perfil por defecto da exactamente las
    mismas lentes: el dashboard puede recalcular sin la base de datos."""
    de_tabla = CellCounts.from_frame(counts.to_frame(counts.total_grid() > 0))
    for perfil in bp.DEFAULT_PROFILES.values():
        pd.testing.assert_frame_equal(compute_lenses(counts, perfil), compute_lenses(de_tabla, perfil))


def test_cell_counts_incluye_el_contexto_de_celdas_inactivas(tmp_path):
    """Regresión: las celdas activas se definen solo con POIs de Overpass, pero un edificio en una celda inactiva vecina
    suma en las lentes de la activa. Si cell_counts.csv solo trajera las activas, recalcular daría otros números."""
    pois = pd.DataFrame([punto(10, 10, "food_drink", "restaurant"), punto(10, 12, "edificio", "apartments")])
    c = CellCounts.from_pois(pois)
    assert not c.active_mask()[10, 12]  # a 2 celdas del restaurante: inactiva
    p = panorama.build_panorama(c, PERFIL)
    panorama.write_outputs(tmp_path, p, c, {})
    leidos = panorama.read_counts(tmp_path)
    assert leidos.arrays[("edificio", "apartments")][10, 12] == 1
    pd.testing.assert_frame_equal(compute_lenses(c, PERFIL), compute_lenses(leidos, PERFIL))
    assert p.loc["r10c10", "mercado_residentes"] > 0  # el edificio vecino sí cuenta


def test_from_frame_conserva_la_subcategoria_vacia():
    """Una subcategoría vacía se guarda como 'categoria|' y vuelve como ''."""
    pois = pd.DataFrame([punto(10, 10, "food_drink", ""), punto(10, 10, "food_drink", "cafe")])
    c = CellCounts.from_pois(pois)
    de_tabla = CellCounts.from_frame(c.to_frame())
    assert ("food_drink", "") in de_tabla.arrays and de_tabla.arrays[("food_drink", "")].sum() == 1


def test_from_frame_con_tabla_vacia_no_falla():
    """Sin columnas no hay conteos, pero tampoco error."""
    assert CellCounts.from_frame(pd.DataFrame(index=pd.Index([], name="cell_id"))).arrays == {}


# ---- percentiles -------------------------------------------------------------------------------------------------
def test_percentile_rank_conserva_los_nan_y_es_monotono():
    """Sin datos sigue siendo NaN (no una posición baja) y el orden se respeta."""
    s = pd.Series([5.0, np.nan, 1.0, 3.0])
    p = panorama.percentile_rank(s)
    assert np.isnan(p[1]) and p[2] < p[3] < p[0] and p.max() == 1.0 and p.min() > 0


def test_percentile_rank_empates_reciben_el_rango_medio():
    """Valores iguales tienen el mismo percentil."""
    p = panorama.percentile_rank(pd.Series([2.0, 2.0, 2.0, 9.0]))
    assert p[0] == p[1] == p[2] == 0.5 and p[3] == 1.0  # rango medio de las posiciones 1-3 = 2 de 4


# ---- confianza ---------------------------------------------------------------------------------------------------
def _lentes(apoyos, datos):
    n = len(apoyos[0])
    d = {}
    for lente, a, ok in zip(("competencia", "mercado", "proveedores"), apoyos, datos):
        d[f"apoyo_{lente}"] = a
        d[f"datos_{lente}"] = [ok] * n
    return pd.DataFrame(d, index=pd.Index([f"r10c1{i}" for i in range(n)], name="cell_id"))


def test_confianza_una_lente_sin_datos_cuenta_cero():
    """Con apoyo de sobra pero una lente sin datos, la confianza máxima es 2/3 (nivel media-alta, nunca 1)."""
    lentes = _lentes([[50], [50], [50]], [True, True, False])
    c = panorama.confidence(lentes, [50])
    assert c["confianza"].iloc[0] == pytest.approx(2 / 3) and c["confianza_nivel"].iloc[0] == "alta"


def test_confianza_toda_la_informacion_da_uno_y_ninguna_da_cero():
    """Los extremos: apoyo suficiente en las tres lentes = 1; sin datos en ninguna = 0 (baja)."""
    lentes = _lentes([[50, 0], [50, 0], [50, 0]], [True, True, True])
    c = panorama.confidence(lentes, [50, 0])
    assert c["confianza"].tolist() == [1.0, 0.0] and c["confianza_nivel"].tolist() == ["alta", "baja"]


def test_confianza_competencia_usa_los_pois_de_la_vecindad_no_los_competidores():
    """Una celda sin competidores pero rodeada de POIs tiene confianza ALTA en competencia: cero competidores es una
    observación creíble donde hay mucho mapeado. (Con el número de competidores saldría baja, y penalizaría justo las
    celdas de oportunidad.)"""
    lentes = _lentes([[0], [20], [20]], [True, True, True])  # cero competidores
    assert panorama.confidence(lentes, [40])["confianza"].iloc[0] == 1.0
    assert panorama.confidence(lentes, [0])["confianza"].iloc[0] == pytest.approx(2 / 3)  # nada mapeado alrededor


def test_confianza_niveles_en_los_umbrales():
    """Los umbrales son 1/3 y 2/3, inclusivos hacia arriba."""
    lentes = _lentes([[5, 5, 0], [0, 5, 0], [0, 5, 0]], [True, True, True])
    c = panorama.confidence(lentes, [5, 5, 0])
    assert c["confianza"].round(4).tolist() == [0.3333, 1.0, 0.0]
    assert c["confianza_nivel"].tolist() == ["media", "alta", "baja"]


# ---- localización ------------------------------------------------------------------------------------------------
def test_locate_da_la_zona_mas_cercana_y_su_distancia():
    """El centro de la celda de una zona se asigna a esa zona, a menos de media celda de distancia."""
    nombre, z = next(iter(LOCATIONS.items()))
    f, c = grid.cell_index(np.array([z.latitude]), np.array([z.longitude]))
    info = panorama.locate(pd.Index([grid.cell_id(f[0], c[0])]))
    assert info["zona_cercana"].iloc[0] == nombre and info["dist_zona_m"].iloc[0] < grid.CELL_SIZE_M
    assert info["fila"].iloc[0] == f[0] and info["col"].iloc[0] == c[0]


# ---- panorama ----------------------------------------------------------------------------------------------------
def test_panorama_sin_brecha_deja_la_brecha_vacia_y_no_validada(counts):
    """Sin tabla de brecha, sus columnas son NaN, no hay modelo y brecha_validada es False."""
    p = panorama.build_panorama(counts, PERFIL)
    assert p["perfil"].eq("food_drink").all() and p.index.name == "cell_id"
    assert p[list(panorama.COLUMNAS_BRECHA)].isna().all().all()
    assert (p["modelo_brecha"] == "").all() and not p["brecha_validada"].any()


def test_panorama_incluye_las_lentes_sin_alterarlas(counts):
    """Las columnas de lentes del panorama son exactamente las de compute_lenses."""
    p = panorama.build_panorama(counts, PERFIL)
    lentes = compute_lenses(counts, PERFIL)
    pd.testing.assert_frame_equal(p[lentes.columns], lentes)


def test_panorama_percentiles_entre_cero_y_uno(counts):
    """Cada percentil está en (0, 1] y la celda con más competencia tiene el máximo."""
    p = panorama.build_panorama(counts, PERFIL)
    for col in panorama.PERCENTILES:
        v = p[f"pct_{col}"].dropna()
        assert len(v) and v.min() > 0 and v.max() <= 1.0
    assert p.loc[p["competencia_directa"].idxmax(), "pct_competencia_directa"] == 1.0


def test_panorama_con_brecha_se_alinea_por_celda(counts):
    """La brecha se une por cell_id: las celdas sin brecha quedan en NaN y las sobrantes se ignoran."""
    base = panorama.build_panorama(counts, PERFIL)
    ids = list(base.index[:3]) + ["r00c00"]  # r00c00 no está en el panorama
    brecha = pd.DataFrame(
        {
            "esperado": [1.0, 2.0, 3.0, 9.0],
            "brecha_relativa": [0.5, -0.5, 1.5, 9.9],
            "brecha_p10": [0.0, -1.0, 1.0, 9.0],
            "brecha_p90": [1.0, 0.0, 2.0, 10.0],
        },
        index=ids,
    )
    p = panorama.build_panorama(counts, PERFIL, brecha, "boosting", brecha_validada=False)
    assert len(p) == len(base) and "r00c00" not in p.index
    assert p["brecha_relativa"].iloc[:3].tolist() == [0.5, -0.5, 1.5]
    assert p["brecha_relativa"].iloc[3:].isna().all()
    assert (p["modelo_brecha"] == "boosting").all() and not p["brecha_validada"].any()


def test_pois_vecindad_cuenta_solo_pois_de_overpass_no_el_contexto():
    """El apoyo general de la confianza son POIs de Overpass en la celda y sus 8 vecinas; los edificios del contexto de
    OSM no cuentan (no dicen cuán completo está el mapa de comercios)."""
    pois = pd.DataFrame(
        [punto(10, 10, "food_drink", "restaurant"), punto(10, 11, "business", "bakery")]
        + [punto(10, 10, "edificio", "yes")] * 30
    )
    p = panorama.build_panorama(CellCounts.from_pois(pois), PERFIL)
    assert p.loc["r10c10", "pois_vecindad"] == 2 and p.loc["r10c11", "pois_vecindad"] == 2


def test_la_brecha_no_modifica_ninguna_otra_columna(counts):
    """Con o sin brecha, las lentes, percentiles y confianza son idénticos: la brecha no entra en nada más."""
    sin = panorama.build_panorama(counts, PERFIL)
    brecha = pd.DataFrame({c: np.ones(len(sin)) for c in panorama.COLUMNAS_BRECHA}, index=sin.index)
    con = panorama.build_panorama(counts, PERFIL, brecha, "boosting")
    otras = [
        c for c in sin.columns if c not in panorama.COLUMNAS_BRECHA and c not in ("modelo_brecha", "brecha_validada")
    ]
    pd.testing.assert_frame_equal(sin[otras], con[otras])


def test_brecha_validada_se_propaga_solo_si_hay_brecha(counts):
    """brecha_validada=True solo se refleja cuando se entrega una brecha; sin ella el panorama no afirma nada."""
    sin = panorama.build_panorama(counts, PERFIL, None, "boosting", brecha_validada=True)
    assert not sin["brecha_validada"].any() and (sin["modelo_brecha"] == "").all()  # sin brecha no hay modelo
    brecha = pd.DataFrame({c: [0.0] for c in panorama.COLUMNAS_BRECHA}, index=[sin.index[0]])
    assert panorama.build_panorama(counts, PERFIL, brecha, "boosting", brecha_validada=True)["brecha_validada"].all()


def test_el_modulo_del_panorama_no_importa_scikit_learn():
    """El dashboard debe poder importar el panorama sin cargar scikit-learn (el contenedor tiene 1 GiB). scipy sí: la
    rejilla ya lo usa y está en requirements.txt."""
    codigo = (
        "import sys; sys.path.insert(0, sys.argv[1]); import src.ml.panorama, src.ml.cell_counts, src.ml.lenses; "
        "bad = [m for m in sys.modules if m.split('.')[0] == 'sklearn']; print(bad[:3]); sys.exit(1 if bad else 0)"
    )
    r = subprocess.run([sys.executable, "-c", codigo, str(ROOT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# ---- brecha desde una validación ---------------------------------------------------------------------------------
def test_gap_from_evaluation_calcula_esperado_brecha_y_percentiles():
    """Con predicciones conocidas: el esperado es la media entre repeticiones y la brecha, la relativa de la media."""
    y = np.array([0.0, 4.0, 8.0])
    oof = np.array([[2.0, 4.0, 3.0], [4.0, 4.0, 5.0]])
    ev = validation.Evaluation(["m"], y, {"m": oof}, np.zeros(3, dtype=int), pd.DataFrame(), 1)
    g = validation.gap_from_evaluation(ev, "m")
    assert g["esperado"].tolist() == [3.0, 4.0, 4.0]
    assert g["brecha_relativa"].tolist() == pytest.approx(
        ((np.array([3.0, 4.0, 4.0]) - y) / np.sqrt(np.array([3.0, 4.0, 4.0]) + 1)).tolist()
    )
    assert (g["brecha_p10"] <= g["brecha_p90"]).all()
    assert g["brecha_p10"].iloc[1] == g["brecha_p90"].iloc[1] == 0.0  # misma predicción en las dos repeticiones
    celda0 = [validation.brecha_relativa(oof[r][0], y[0]) for r in range(2)]
    assert g["brecha_p10"].iloc[0] == pytest.approx(np.percentile(celda0, 10))
    assert g["brecha_p90"].iloc[0] == pytest.approx(np.percentile(celda0, 90))
    assert g["brecha_p10"].iloc[0] < g["brecha_p90"].iloc[0]


def test_gap_from_evaluation_una_repeticion_no_tiene_dispersion():
    """Con una sola repetición los percentiles coinciden con la brecha de esa repetición."""
    y = np.array([1.0, 2.0])
    ev = validation.Evaluation(["m"], y, {"m": np.array([[3.0, 1.0]])}, np.zeros(2, dtype=int), pd.DataFrame(), 1)
    g = validation.gap_from_evaluation(ev, "m")
    assert g["brecha_p10"].tolist() == g["brecha_p90"].tolist() == g["brecha_relativa"].tolist()


# ---- archivos de salida ------------------------------------------------------------------------------------------
@pytest.fixture
def salida(tmp_path, counts):
    p = pd.concat(
        [panorama.build_panorama(counts, PERFIL), panorama.build_panorama(counts, bp.get_default_profile("school"))]
    )
    panorama.write_outputs(tmp_path, p, counts, {"procedencia": {"commit": "abc"}})
    return tmp_path, p


def test_los_archivos_se_escriben_y_se_verifican(salida):
    """Se escriben los tres archivos y la verificación no encuentra problemas."""
    d, p = salida
    assert sorted(x.name for x in d.iterdir()) == sorted(panorama.ARCHIVOS.values())
    assert panorama.verify_outputs(d) == []
    m = json.loads((d / "panorama_manifest.json").read_text(encoding="utf-8"))
    assert (
        m["archivos"]["panorama.csv"]["filas"] == len(p) and m["procedencia"]["commit"] == "abc" and m["formato"] == 1
    )


def test_el_panorama_leido_coincide_con_el_escrito(salida):
    """La ida y vuelta por CSV conserva columnas, índice y valores (con la precisión escrita)."""
    d, p = salida
    leido = panorama.read_panorama(d)
    assert list(leido["cell_id"]) == list(p.index) and set(p.columns) <= set(leido.columns)
    for col in ("competencia_directa", "mercado_total", "confianza", "dist_zona_m"):
        np.testing.assert_allclose(
            leido[col].to_numpy(dtype=float), p[col].to_numpy(dtype=float), rtol=1e-5, equal_nan=True
        )
    assert leido["brecha_validada"].dtype == bool and leido["modelo_brecha"].eq("").all()


def test_los_conteos_leidos_dan_las_mismas_lentes(salida, counts):
    """read_counts reconstruye los conteos: las lentes recalculadas coinciden con las de los conteos originales."""
    d, _ = salida
    leidos = panorama.read_counts(d)
    for perfil in bp.DEFAULT_PROFILES.values():
        pd.testing.assert_frame_equal(compute_lenses(counts, perfil), compute_lenses(leidos, perfil))


def test_escribir_dos_veces_da_los_mismos_bytes(tmp_path, counts):
    """La salida es determinista (sin fechas dentro de los CSV): el hash no cambia entre ejecuciones."""
    p = panorama.build_panorama(counts, PERFIL)
    a = panorama.write_outputs(tmp_path / "a", p, counts, {})["archivos"]
    b = panorama.write_outputs(tmp_path / "b", p, counts, {})["archivos"]
    assert a == b


def test_los_tres_archivos_se_escriben_con_saltos_de_linea_lf(salida):
    """Los archivos salen iguales en Windows y Linux (sin CRLF), para que la tabla versionada no cambie según dónde se
    genere."""
    d, _ = salida
    for nombre in panorama.ARCHIVOS.values():
        assert b"\r" not in (d / nombre).read_bytes(), nombre


def test_verify_detecta_un_csv_alterado(salida):
    """Cambiar un valor del panorama se detecta por el hash y read_panorama se niega a leerlo."""
    d, _ = salida
    ruta = d / "panorama.csv"
    ruta.write_text(ruta.read_text(encoding="utf-8").replace("food_drink", "food_drinK", 1), encoding="utf-8")
    assert any("panorama.csv" in x and "hash" in x for x in panorama.verify_outputs(d))
    with pytest.raises(ValueError):
        panorama.read_panorama(d)
    assert len(panorama.read_panorama(d, verificar=False)) > 0


def test_verify_detecta_archivos_ausentes_y_manifiesto_roto(salida):
    """Falta un CSV, falta el manifiesto, o el formato no es el esperado."""
    d, _ = salida
    (d / "cell_counts.csv").unlink()
    assert "falta cell_counts.csv" in panorama.verify_outputs(d)
    m = json.loads((d / "panorama_manifest.json").read_text(encoding="utf-8"))
    m["formato"] = 99
    (d / "panorama_manifest.json").write_text(json.dumps(m), encoding="utf-8")
    assert any("formato" in x for x in panorama.verify_outputs(d))
    (d / "panorama_manifest.json").unlink()
    assert panorama.verify_outputs(d)[0].startswith("no se pudo leer el manifiesto")


def test_el_manifiesto_no_puede_omitir_un_archivo(salida):
    """Un CSV que existe pero no figura en el manifiesto se reporta."""
    d, _ = salida
    m = json.loads((d / "panorama_manifest.json").read_text(encoding="utf-8"))
    del m["archivos"]["cell_counts.csv"]
    (d / "panorama_manifest.json").write_text(json.dumps(m), encoding="utf-8")
    assert "cell_counts.csv no está en el manifiesto" in panorama.verify_outputs(d)


# ---- tabla versionada en el repositorio --------------------------------------------------------------------------
DATA_ML = ROOT / "data" / "ml"


def test_la_tabla_versionada_coincide_con_su_manifiesto():
    """data/ml/ (la tabla que llevará el dashboard) está íntegra: los hashes del manifiesto coinciden con los archivos
    y ningún saneamiento de saltos de línea los alteró (ver .gitattributes)."""
    assert panorama.verify_outputs(DATA_ML) == []
    assert b"\r\n" not in (DATA_ML / "panorama.csv").read_bytes()


def test_la_tabla_versionada_declara_la_brecha_como_lo_dice_la_validacion():
    """La brecha solo aparece en food_drink y business; brecha_validada coincide con la decisión del manifiesto (hoy
    ninguna) y las otras cinco categorías no afirman nada. Si algún día un candidato gana, habrá que regenerarla."""
    p = panorama.read_panorama(DATA_ML)
    m = json.loads((DATA_ML / "panorama_manifest.json").read_text(encoding="utf-8"))
    assert set(p["perfil"]) == set(bp.DEFAULT_PROFILES)
    assert set(p.loc[p["esperado"].notna(), "perfil"]) == set(m["brecha"]) == {"food_drink", "business"}
    for clave, info in m["brecha"].items():
        assert p.loc[p["perfil"] == clave, "brecha_validada"].eq(info["ganador"] is not None).all()
    assert not p.loc[~p["perfil"].isin(m["brecha"]), "brecha_validada"].any()
    assert "EXPLORATORIA" in m["advertencia"]


def test_la_tabla_versionada_recalcula_las_mismas_lentes():
    """Con data/ml/cell_counts.csv, el panorama de cada perfil sale igual que el guardado: es lo que hará el dashboard."""
    p = panorama.read_panorama(DATA_ML)
    c = panorama.read_counts(DATA_ML)
    for clave, perfil in bp.DEFAULT_PROFILES.items():
        guardado = p[p["perfil"] == clave].set_index("cell_id")
        nuevo = panorama.build_panorama(c, perfil)
        assert list(nuevo.index) == list(guardado.index)
        for col in ("competencia_directa", "mercado_total", "proveedores_total", "apoyo_mercado", "pois_vecindad"):
            np.testing.assert_allclose(
                nuevo[col].to_numpy(dtype=float),
                guardado[col].to_numpy(dtype=float),
                rtol=1e-5,
                equal_nan=True,
                err_msg=f"{clave}.{col}",
            )


# ---- herramienta -------------------------------------------------------------------------------------------------
@pytest.fixture
def paquete(tmp_path):
    """Paquete de entrada pequeño, con contexto, construido con la misma librería que el exportador real."""
    import sqlite3

    db = tmp_path / "m.db"
    pois = pois_sinteticos()
    solo_pois = pois[~pois["category"].isin(["edificio", "alojamiento"])]
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE pois (id INTEGER PRIMARY KEY, category TEXT, subcategory TEXT, name TEXT, latitude REAL, longitude REAL)"
    )
    conn.executemany(
        "INSERT INTO pois (category, subcategory, name, latitude, longitude) VALUES (?,?,?,?,?)",
        [(r.category, r.subcategory, "x", r.latitude, r.longitude) for r in solo_pois.itertuples()],
    )
    conn.commit()
    conn.close()
    out = tmp_path / "p.sqlite"
    inputs_bundle.export_bundle(db, out, pois[pois["category"].isin(["edificio", "alojamiento"])])
    return out


def test_build_panorama_sin_brecha_de_punta_a_punta(tmp_path, paquete, capsys):
    """La herramienta escribe los tres archivos con la procedencia del paquete y las siete categorías."""
    out = tmp_path / "ml"
    assert bpn.main(["--db", str(paquete), "--sin-brecha", "--out-dir", str(out)]) == 0
    assert panorama.verify_outputs(out) == []
    p = panorama.read_panorama(out)
    assert set(p["perfil"]) == set(bp.DEFAULT_PROFILES) and p["esperado"].isna().all()
    m = json.loads((out / "panorama_manifest.json").read_text(encoding="utf-8"))
    assert m["procedencia"]["entrada_sha256"] == inputs_bundle.file_hash(paquete)
    assert m["parametros"]["con_brecha"] is False and m["parametros"]["con_contexto"] is True
    assert "Sin brecha" in m["advertencia"]


def test_build_panorama_con_brecha_la_etiqueta_como_exploratoria(tmp_path, paquete):
    """Con brecha, solo food_drink y business la llevan; el manifiesto declara la decisión y la advertencia, y la
    columna brecha_validada solo es True si un candidato superó a la línea base."""
    out = tmp_path / "ml"
    assert (
        bpn.main(["--db", str(paquete), "--out-dir", str(out), "--repeats", "1", "--folds", "2", "--boot", "30"]) == 0
    )
    p = panorama.read_panorama(out)
    con = p[p["esperado"].notna()]
    assert set(con["perfil"]) == {"food_drink", "business"}
    assert (con["modelo_brecha"] != "").all()
    m = json.loads((out / "panorama_manifest.json").read_text(encoding="utf-8"))
    assert set(m["brecha"]) == {"food_drink", "business"} and "EXPLORATORIA" in m["advertencia"]
    for clave, info in m["brecha"].items():
        validada = info["ganador"] is not None
        assert con[con["perfil"] == clave]["brecha_validada"].eq(validada).all()
    assert p[~p["perfil"].isin(["food_drink", "business"])]["brecha_validada"].eq(False).all()


def test_build_panorama_rechaza_un_paquete_alterado(tmp_path, paquete, capsys):
    """Antes de calcular se verifica el paquete; si no coincide, no se escribe nada."""
    import sqlite3

    conn = sqlite3.connect(paquete)
    conn.execute("DELETE FROM pois WHERE rowid = 1")
    conn.commit()
    conn.close()
    out = tmp_path / "ml"
    assert bpn.main(["--db", str(paquete), "--sin-brecha", "--out-dir", str(out)]) == 1
    assert "no coincide" in capsys.readouterr().out and not out.exists()
