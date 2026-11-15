"""Tests de la localidad de cada celda (src/ml/places.py y tools/build_cell_places.py): armado de límites desde la respuesta
de Overpass, punto en polígono con huecos, asignación por cercanía en la costa y archivos con manifiesto. Sin red."""

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_cell_places as tool  # noqa: E402

from src.ml import grid, panorama, places  # noqa: E402

DATA_ML = ROOT / "data" / "ml"


def pt(lat, lon):
    return {"lat": lat, "lon": lon}


def via(*puntos):
    return {"type": "way", "role": "outer", "geometry": [pt(*p) for p in puntos]}


def hueco(*puntos):
    return {"type": "way", "role": "inner", "geometry": [pt(*p) for p in puntos]}


def relacion(osm_id, nombre, miembros, nivel="8", **etiquetas):
    return {
        "type": "relation",
        "id": osm_id,
        "tags": {"boundary": "administrative", "admin_level": nivel, "name": nombre, **etiquetas},
        "members": miembros,
    }


# Cuadrado de 0,01° de lado con el vértice sur-oeste en (35.90, 14.50), partido en dos tramos que llegan en distinto sentido.
SUR, OESTE, N, E = 35.90, 14.50, 35.91, 14.51
TRAMO_A = via((SUR, OESTE), (SUR, E), (N, E))
TRAMO_B = via((SUR, OESTE), (N, OESTE), (N, E))  # empieza en el mismo vértice: hay que darle la vuelta


@pytest.fixture
def cuadrado():
    (loc,) = places.parse_boundaries([relacion(1, "Cuadrado", [TRAMO_A, TRAMO_B])])
    return loc


# ---- límites -----------------------------------------------------------------------------------------------------
def test_los_tramos_se_unen_en_un_anillo_cerrado_aunque_lleguen_desordenados_y_al_reves(cuadrado):
    assert len(cuadrado.exteriores) == 1
    anillo = cuadrado.exteriores[0]
    assert anillo[0] == anillo[-1] and {(SUR, OESTE), (SUR, E), (N, E), (N, OESTE)} <= set(anillo)


def test_una_relacion_sin_ningun_anillo_cerrado_se_conserva_vacia_y_marcada():
    """QA de Codex (menor): antes se descartaba en silencio y la herramienta no podía avisar de ella."""
    (abierto,) = places.parse_boundaries([relacion(1, "Abierto", [via((SUR, OESTE), (SUR, E), (N, E))])])
    assert abierto.exteriores == [] and abierto.tramos_descartados == 1
    assert not places.contained_mask(np.array([35.905]), np.array([14.505]), abierto).any()  # no contiene nada
    assert places.assign_places([35.905], [14.505], [abierto])["localidad"].iloc[0] == ""  # ni asigna por cercanía


def test_solo_se_toman_las_relaciones_del_nivel_pedido_con_nombre():
    elementos = [
        relacion(1, "Región", [TRAMO_A, TRAMO_B], nivel="7"),
        relacion(2, "", [TRAMO_A, TRAMO_B]),
        relacion(3, "Buena", [TRAMO_A, TRAMO_B]),
        {"type": "node", "id": 9, "tags": {"admin_level": "8", "name": "Nodo"}},
    ]
    assert [l.nombre for l in places.parse_boundaries(elementos)] == ["Buena"]


def test_el_nombre_en_ingles_gana_al_local():
    (loc,) = places.parse_boundaries([relacion(1, "Wied il-Għajn", [TRAMO_A, TRAMO_B], **{"name:en": "Marsaskala"})])
    assert loc.nombre == "Marsaskala"


# ---- asignación --------------------------------------------------------------------------------------------------
def test_un_punto_dentro_se_asigna_y_uno_lejos_queda_vacio(cuadrado):
    r = places.assign_places([35.905, 36.5], [14.505, 14.505], [cuadrado])
    assert list(r["localidad"]) == ["Cuadrado", ""] and list(r["criterio"]) == ["dentro", ""]
    assert r["osm_relacion"].iloc[0] == "1"


def test_un_hueco_deja_fuera_el_punto_y_se_asigna_a_la_localidad_que_lo_ocupa():
    exterior = relacion(
        1,
        "Grande",
        [
            TRAMO_A,
            TRAMO_B,
            hueco((35.903, 14.503), (35.903, 14.507), (35.907, 14.507), (35.907, 14.503), (35.903, 14.503)),
        ],
    )
    interior = relacion(
        2,
        "Enclave",
        [
            via((35.903, 14.503), (35.903, 14.507), (35.907, 14.507)),
            via((35.903, 14.503), (35.907, 14.503), (35.907, 14.507)),
        ],
    )
    r = places.assign_places([35.905, 35.9015], [14.505, 14.5015], places.parse_boundaries([exterior, interior]))
    assert list(r["localidad"]) == ["Enclave", "Grande"]


def test_el_centro_en_el_mar_se_asigna_por_cercania_solo_dentro_de_la_tolerancia(cuadrado):
    # 0,001° de latitud al sur = ~111 m (dentro de 250 m); 0,005° = ~557 m (fuera)
    r = places.assign_places([SUR - 0.001, SUR - 0.005], [14.505, 14.505], [cuadrado], tolerancia_m=250)
    assert list(r["localidad"]) == ["Cuadrado", ""] and list(r["criterio"]) == ["cercana", ""]


def test_la_distancia_al_borde_es_la_correcta(cuadrado):
    d = places.distance_to_boundary_m(np.array([SUR - 0.001]), np.array([14.505]), cuadrado)
    assert d[0] == pytest.approx(0.001 * 111_320, rel=0.01)


def test_en_un_solape_gana_la_localidad_de_menor_id():
    a, b = relacion(7, "Siete", [TRAMO_A, TRAMO_B]), relacion(3, "Tres", [TRAMO_A, TRAMO_B])
    for orden in ([a, b], [b, a]):
        r = places.assign_places([35.905], [14.505], places.parse_boundaries(orden))
        assert r["localidad"].iloc[0] == "Tres"


# ---- archivos ----------------------------------------------------------------------------------------------------
def tabla_ejemplo():
    return pd.DataFrame(
        {
            "cell_id": ["r02c03", "r01c01"],
            "localidad": ["Qormi", ""],
            "osm_relacion": ["7510556", ""],
            "criterio": ["dentro", ""],
        }
    )


def test_escribir_y_leer_devuelve_la_localidad_por_celda(tmp_path):
    manifiesto = places.write_places(tmp_path, tabla_ejemplo(), {"ejecutado": "x"})
    assert manifiesto["filas"] == 2 and manifiesto["sin_localidad"] == 1 and "OpenStreetMap" in manifiesto["atribucion"]
    lugares = places.read_places(tmp_path)
    assert lugares["r02c03"] == "Qormi" and lugares["r01c01"] == ""  # la celda sin localidad sigue siendo cadena vacía


def test_un_csv_alterado_o_ausente_no_se_lee(tmp_path):
    assert places.read_places(tmp_path) is None  # ni manifiesto
    places.write_places(tmp_path, tabla_ejemplo(), {})
    ruta = tmp_path / places.ARCHIVOS["places"]
    ruta.write_text(ruta.read_text(encoding="utf-8").replace("Qormi", "Luqa"), encoding="utf-8")
    assert places.read_places(tmp_path) is None and "hash" in places.verify_places(tmp_path)[0]
    ruta.unlink()
    assert "falta" in places.verify_places(tmp_path)[0]


def test_la_tabla_publicada_esta_integra_y_cubre_todas_las_celdas_del_panorama():
    assert places.verify_places(DATA_ML) == []
    lugares = places.read_places(DATA_ML)
    celdas = set(panorama.read_panorama(DATA_ML)["cell_id"])
    assert set(lugares.index) == celdas
    manifiesto = json.loads((DATA_ML / places.ARCHIVOS["manifest"]).read_text(encoding="utf-8"))
    assert "OpenStreetMap" in manifiesto["atribucion"] and manifiesto["nivel_admin"] == places.NIVEL_LOCALIDAD
    assert (lugares != "").mean() > 0.95  # casi todas tienen localidad; las del mar quedan vacías


# ---- herramienta -------------------------------------------------------------------------------------------------
def test_la_consulta_es_una_sola_y_cubre_la_rejilla():
    q = tool.construir_consulta()
    assert q.count("relation[") == 1 and '"admin_level"="8"' in q and f"{grid.SOUTH:.6f}" in q and "out geom;" in q


def test_el_dry_run_no_llama_a_la_red(monkeypatch, capsys):
    monkeypatch.setattr(tool, "pedir", lambda *a, **k: pytest.fail("no debe pedir nada"))
    assert tool.main(["--dry-run"]) == 0 and "dry-run" in capsys.readouterr().out


def test_la_herramienta_asigna_desde_una_respuesta_guardada(tmp_path, monkeypatch, capsys):
    """Con una respuesta local (sin red) escribe el CSV y el manifiesto en el directorio indicado, sin tocar el panorama."""
    destino = tmp_path / "ml"
    shutil.copytree(DATA_ML, destino)
    (destino / places.ARCHIVOS["places"]).unlink()
    antes = (destino / "panorama.csv").read_bytes()
    celda = panorama.read_panorama(destino).iloc[0]
    lat, lon = celda["lat"], celda["lon"]
    cuadro = via(
        (lat - 0.01, lon - 0.01),
        (lat - 0.01, lon + 0.01),
        (lat + 0.01, lon + 0.01),
        (lat + 0.01, lon - 0.01),
        (lat - 0.01, lon - 0.01),
    )
    crudo = tmp_path / "crudo.json"
    crudo.write_text(
        json.dumps(
            {"osm3s": {"timestamp_osm_base": "2026-11-15T00:00:00Z"}, "elements": [relacion(5, "Prueba", [cuadro])]}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(tool, "pedir", lambda *a, **k: pytest.fail("no debe pedir nada"))
    assert tool.main(["--data-dir", str(destino), "--crudo", str(crudo)]) == 0
    lugares = places.read_places(destino)
    assert (
        lugares[celda["cell_id"]] == "Prueba" and len(lugares) == panorama.read_panorama(destino)["cell_id"].nunique()
    )
    manifiesto = json.loads((destino / places.ARCHIVOS["manifest"]).read_text(encoding="utf-8"))
    assert manifiesto["base_osm"] == "2026-11-15T00:00:00Z" and manifiesto["localidades"] == 1
    assert (destino / "panorama.csv").read_bytes() == antes  # el panorama no cambia


def test_sin_localidades_en_la_respuesta_no_se_escribe_nada(tmp_path, capsys):
    destino = tmp_path / "ml"
    shutil.copytree(DATA_ML, destino)
    (destino / places.ARCHIVOS["places"]).unlink()
    (destino / places.ARCHIVOS["manifest"]).unlink()
    crudo = tmp_path / "vacio.json"
    crudo.write_text(json.dumps({"elements": []}), encoding="utf-8")
    assert tool.main(["--data-dir", str(destino), "--crudo", str(crudo)]) == 1
    assert not (destino / places.ARCHIVOS["places"]).exists()


def test_una_isla_dentro_de_un_hueco_de_la_misma_relacion_cuenta_como_dentro():
    """Regresión del code-review: los huecos se restaban de la unión de todos los anillos exteriores y borraban la isla."""
    hueco_ = hueco((35.903, 14.503), (35.903, 14.507), (35.907, 14.507), (35.907, 14.503), (35.903, 14.503))
    isla = via((35.9045, 14.5045), (35.9045, 14.5055), (35.9055, 14.5055), (35.9055, 14.5045), (35.9045, 14.5045))
    (loc,) = places.parse_boundaries([relacion(1, "Con isla", [TRAMO_A, TRAMO_B, hueco_, isla])])
    # en el cuerpo, en el hueco vacío, en la isla (dentro del hueco)
    r = places.contained_mask(np.array([35.9015, 35.9035, 35.905]), np.array([14.5015, 14.5035, 14.505]), loc)
    assert list(r) == [True, False, True]


def test_los_tramos_que_no_cierran_se_cuentan_para_avisar():
    completa = relacion(1, "Completa", [TRAMO_A, TRAMO_B])
    rota = relacion(2, "Rota", [TRAMO_A, TRAMO_B, via((35.95, 14.55), (35.96, 14.56))])  # un tramo suelto
    por_nombre = {l.nombre: l.tramos_descartados for l in places.parse_boundaries([completa, rota])}
    assert por_nombre == {"Completa": 0, "Rota": 1}


def test_la_publicada_no_tiene_limites_incompletos():
    manifiesto = json.loads((DATA_ML / places.ARCHIVOS["manifest"]).read_text(encoding="utf-8"))
    assert manifiesto["localidades_incompletas"] == []
