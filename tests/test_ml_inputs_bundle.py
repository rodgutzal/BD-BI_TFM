"""Tests de la fase 1c: paquete de entrada del ML para entrenar en otra máquina (src/ml/inputs_bundle.py), su
exportador tools/export_ml_inputs.py y que las herramientas de la fase 0 y 1 aceptan el paquete en `--db`."""

import hashlib
import importlib.util
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.locations import LOCATIONS  # noqa: E402
from src.ml import data_access, grid, inputs_bundle  # noqa: E402


def _cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, ROOT / "tools" / f"{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exportador = _cargar("export_ml_inputs")
mlv = _cargar("measure_lens_variance")
vlm = _cargar("validate_location_model")

ZONAS = list(LOCATIONS)


def _punto(fila, col, cat, sub):
    lat, lon = grid.cell_center(fila, col)
    return (cat, sub, f"{cat}{fila}{col}", float(lat), float(lon))


def crear_base(path, con_fsq=True, con_demografia=True, con_rutas=True, pois=True):
    """Base mínima con el mismo esquema (y columnas de más) que mobility.db."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE pois (id INTEGER PRIMARY KEY, osm_type TEXT, osm_id INTEGER, category TEXT, subcategory TEXT, "
                 "name TEXT, latitude REAL, longitude REAL, updated_at TEXT)")
    if pois:
        filas = [_punto(10 + i % 5, 10 + i // 5, "restaurant" if i % 2 else "retail", "cafe" if i % 2 else "shop")
                 for i in range(20)]
        conn.executemany("INSERT INTO pois (category, subcategory, name, latitude, longitude, osm_type) VALUES (?,?,?,?,?,'node')", filas)
    if con_fsq:
        conn.execute("CREATE TABLE pois_foursquare (id INTEGER PRIMARY KEY, fsq_place_id TEXT, category TEXT, subcategory TEXT, "
                     "name TEXT, latitude REAL, longitude REAL, updated_at TEXT)")
        conn.executemany("INSERT INTO pois_foursquare (category, subcategory, name, latitude, longitude) VALUES (?,?,?,?,?)",
                         [_punto(11, 11, "restaurant", "pizza"), _punto(12, 12, "retail", "shoes")])
    if con_demografia:
        conn.execute("CREATE TABLE zone_demographics (id INTEGER PRIMARY KEY, zone_name TEXT, dcid TEXT, population INTEGER, "
                     "observation_date TEXT, source TEXT)")
        conn.executemany("INSERT INTO zone_demographics (zone_name, population) VALUES (?,?)",
                         [(z, 1000 * (i + 1)) for i, z in enumerate(ZONAS)])
    if con_rutas:
        conn.execute("CREATE TABLE route_measurements (id INTEGER PRIMARY KEY, timestamp TEXT, origin TEXT, destination TEXT, "
                     "travel_time_min REAL, polyline TEXT)")
        conn.executemany("INSERT INTO route_measurements (timestamp, origin, destination, travel_time_min, polyline) VALUES (?,?,?,?,?)",
                         [("t1", ZONAS[0], ZONAS[1], 10.0, "x" * 50), ("t2", ZONAS[0], ZONAS[1], 20.0, "y" * 50),
                          ("t1", ZONAS[1], ZONAS[2], 7.0, "z")])
    conn.commit()
    conn.close()
    return path


def contexto_df():
    return pd.DataFrame([{"category": "edificio", "subcategory": "yes", "latitude": 35.9, "longitude": 14.45},
                         {"category": "alojamiento", "subcategory": "hotel", "latitude": 35.91, "longitude": 14.46}])


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def base(tmp_path):
    return crear_base(tmp_path / "mobility.db")


@pytest.fixture
def paquete(tmp_path, base):
    out = tmp_path / "ml_inputs.sqlite"
    inputs_bundle.export_bundle(base, out, contexto_df(), commit="abc1234")
    return out


# ---- hash de tablas ----------------------------------------------------------------------------------------------
def test_table_hash_no_depende_del_orden_de_las_filas():
    """El hash de una tabla es el mismo aunque cambie el orden de las filas."""
    df = pd.DataFrame({"a": [3, 1, 2], "b": ["z", "x", "y"]})
    assert inputs_bundle.table_hash(df) == inputs_bundle.table_hash(df.iloc[::-1])


def test_table_hash_detecta_un_cambio_de_valor():
    """Cambiar un solo valor cambia el hash."""
    df = pd.DataFrame({"a": [1.0, 2.0], "b": ["x", "y"]})
    cambiado = df.copy()
    cambiado.loc[0, "a"] = 1.0000001
    assert inputs_bundle.table_hash(df) != inputs_bundle.table_hash(cambiado)


def test_table_hash_distingue_columnas_y_nulos():
    """Un nulo no es lo mismo que un 0, y otra columna con los mismos valores da otro hash."""
    a = pd.DataFrame({"x": [1.0, np.nan]})
    assert inputs_bundle.table_hash(a) != inputs_bundle.table_hash(pd.DataFrame({"x": [1.0, 0.0]}))
    assert inputs_bundle.table_hash(a) != inputs_bundle.table_hash(a.rename(columns={"x": "y"}))


def test_table_hash_tabla_vacia_es_estable():
    """Una tabla sin filas tiene un hash definido (no falla) y depende de sus columnas."""
    v = pd.DataFrame(columns=["a", "b"])
    assert inputs_bundle.table_hash(v) == inputs_bundle.table_hash(pd.DataFrame(columns=["a", "b"]))
    assert inputs_bundle.table_hash(v) != inputs_bundle.table_hash(pd.DataFrame(columns=["a", "c"]))


# ---- exportación -------------------------------------------------------------------------------------------------
def test_el_paquete_se_lee_igual_que_la_base(base, paquete):
    """Las funciones de data_access devuelven lo mismo con el paquete que con la base de origen."""
    pd.testing.assert_frame_equal(data_access.load_pois(base).sort_values(["latitude", "longitude"]).reset_index(drop=True),
                                  data_access.load_pois(paquete).sort_values(["latitude", "longitude"]).reset_index(drop=True))
    assert len(data_access.load_pois_foursquare(paquete)) == len(data_access.load_pois_foursquare(base)) == 2
    pd.testing.assert_frame_equal(data_access.load_zone_table(base), data_access.load_zone_table(paquete))


def test_las_rutas_se_agregan_por_par_origen_destino(base, paquete):
    """El paquete guarda un tiempo medio por par (no las mediciones) y lleva cuántas mediciones lo respaldan."""
    rutas = inputs_bundle._leer(paquete, "SELECT * FROM route_measurements").set_index(["origin", "destination"])
    assert len(rutas) == 2
    assert rutas.loc[(ZONAS[0], ZONAS[1]), "travel_time_min"] == pytest.approx(15.0)
    assert rutas.loc[(ZONAS[0], ZONAS[1]), "n_mediciones"] == 2


def test_el_paquete_no_trae_la_polilinea_ni_columnas_innecesarias(paquete):
    """Se excluye lo que el ML no usa (la polilínea es lo que más pesa en la base real)."""
    conn = sqlite3.connect(paquete)
    columnas = {t: [r[1] for r in conn.execute(f"PRAGMA table_info({t})")] for t in inputs_bundle.TABLAS}
    conn.close()
    assert "polyline" not in columnas["route_measurements"]
    assert columnas["pois"] == ["category", "subcategory", "name", "latitude", "longitude"]
    assert columnas["zone_demographics"] == ["zone_name", "population"]


def test_el_paquete_pesa_mucho_menos_que_la_base(tmp_path):
    """Con mediciones de rutas voluminosas, el paquete es una fracción del tamaño de la base."""
    db = crear_base(tmp_path / "grande.db")
    conn = sqlite3.connect(db)
    conn.executemany("INSERT INTO route_measurements (timestamp, origin, destination, travel_time_min, polyline) VALUES (?,?,?,?,?)",
                     [(f"t{i}", ZONAS[3], ZONAS[4], 5.0, "p" * 400) for i in range(3000)])
    conn.commit()
    conn.close()
    out = tmp_path / "p.sqlite"
    inputs_bundle.export_bundle(db, out)
    assert out.stat().st_size < db.stat().st_size / 10


def test_exportar_no_modifica_la_base_de_origen(tmp_path, base):
    """La base de origen queda byte a byte igual."""
    antes = sha(base)
    inputs_bundle.export_bundle(base, tmp_path / "p.sqlite", contexto_df())
    assert sha(base) == antes


def test_no_pisa_un_paquete_existente_sin_sobrescribir(tmp_path, base, paquete):
    """Con el archivo ya creado falla, y con sobrescribir=True lo reemplaza."""
    with pytest.raises(FileExistsError):
        inputs_bundle.export_bundle(base, paquete)
    antes = sha(paquete)
    inputs_bundle.export_bundle(base, paquete, None, sobrescribir=True)
    assert sha(paquete) != antes
    assert inputs_bundle.load_context_table(paquete).empty


def test_el_paquete_no_puede_ser_la_base_de_origen(base):
    """Exportar sobre la propia base está prohibido incluso con sobrescribir (la destruiría)."""
    with pytest.raises(ValueError):
        inputs_bundle.export_bundle(base, base, sobrescribir=True)
    assert len(data_access.load_pois(base)) == 20


def test_sin_pois_no_hay_nada_que_exportar(tmp_path):
    """Una base sin POIs (o sin la tabla) se rechaza en lugar de producir un paquete vacío."""
    with pytest.raises(ValueError):
        inputs_bundle.export_bundle(crear_base(tmp_path / "v.db", pois=False), tmp_path / "p.sqlite")
    sin_tabla = tmp_path / "s.db"
    sqlite3.connect(sin_tabla).close()
    with pytest.raises(Exception):
        inputs_bundle.export_bundle(sin_tabla, tmp_path / "q.sqlite")
    assert not (tmp_path / "p.sqlite").exists()


def test_las_tablas_opcionales_ausentes_quedan_vacias(tmp_path):
    """Sin Foursquare, demografía ni rutas, el paquete se crea y las zonas quedan con NaN, no con 0."""
    db = crear_base(tmp_path / "m.db", con_fsq=False, con_demografia=False, con_rutas=False)
    out = tmp_path / "p.sqlite"
    inputs_bundle.export_bundle(db, out)
    assert inputs_bundle.verify_bundle(out) == []
    assert data_access.load_pois_foursquare(out).empty
    zonas = data_access.load_zone_table(out)
    assert zonas["demanda"].isna().all() and zonas["tiempo_viaje_prom"].isna().all()


# ---- verificación ------------------------------------------------------------------------------------------------
def test_un_paquete_recien_exportado_es_integro(paquete):
    """verify_bundle no encuentra problemas en un paquete sin tocar."""
    assert inputs_bundle.verify_bundle(paquete) == []


def test_verify_detecta_un_valor_alterado(paquete):
    """Cambiar un valor sin cambiar el número de filas se detecta por el hash."""
    conn = sqlite3.connect(paquete)
    conn.execute("UPDATE pois SET latitude = latitude + 0.001 WHERE rowid = 1")
    conn.commit()
    conn.close()
    problemas = inputs_bundle.verify_bundle(paquete)
    assert len(problemas) == 1 and problemas[0].startswith("pois:") and "hash" in problemas[0]


def test_verify_detecta_filas_perdidas(paquete):
    """Una copia truncada se detecta por el número de filas."""
    conn = sqlite3.connect(paquete)
    conn.execute("DELETE FROM osm_context WHERE rowid = 1")
    conn.commit()
    conn.close()
    problemas = inputs_bundle.verify_bundle(paquete)
    assert any(p.startswith("osm_context: 1 filas") for p in problemas)


def test_verify_detecta_una_tabla_ausente(paquete):
    """Si falta una tabla, lo dice por su nombre."""
    conn = sqlite3.connect(paquete)
    conn.execute("DROP TABLE pois_foursquare")
    conn.commit()
    conn.close()
    assert "falta la tabla pois_foursquare" in inputs_bundle.verify_bundle(paquete)


def test_verify_detecta_un_formato_distinto(paquete):
    """Un paquete de otro formato se rechaza aunque su contenido sea coherente."""
    conn = sqlite3.connect(paquete)
    conn.execute("UPDATE manifest SET valor = '99' WHERE clave = 'formato'")
    conn.commit()
    conn.close()
    assert any("formato" in p for p in inputs_bundle.verify_bundle(paquete))


def test_verify_de_la_base_completa_o_de_un_archivo_que_no_es_paquete(tmp_path, base):
    """La base completa no tiene manifiesto: se informa en vez de lanzar una excepción."""
    assert inputs_bundle.verify_bundle(base)[0].startswith("no se pudo leer el manifiesto")
    assert inputs_bundle.verify_bundle(tmp_path / "no_existe.sqlite")


def test_is_bundle_distingue_el_paquete_de_la_base(base, paquete, tmp_path):
    """Solo el paquete tiene manifiesto; un archivo inexistente no lo es."""
    assert inputs_bundle.is_bundle(paquete) is True
    assert inputs_bundle.is_bundle(base) is False
    assert inputs_bundle.is_bundle(tmp_path / "nada.sqlite") is False


def test_el_manifiesto_registra_commit_versiones_y_filas(paquete):
    """El manifiesto deja constancia de con qué se produjo el paquete."""
    m = inputs_bundle.read_manifest(paquete)
    assert m["commit"] == "abc1234" and m["origen"] == "mobility.db" and m["formato"] == "1"
    assert m["version.scikit-learn"] and m["version.pandas"] and m["version.numpy"] and m["version.scipy"]
    assert m["tabla.pois.filas"] == "20" and m["tabla.osm_context.filas"] == "2"


# ---- contexto de OSM ---------------------------------------------------------------------------------------------
def test_el_contexto_viaja_dentro_del_paquete(paquete):
    """El contexto de OSM se guarda normalizado y data_access lo devuelve sin necesidad del directorio de JSON."""
    ctx = data_access.load_context(paquete)
    assert sorted(ctx["category"]) == ["alojamiento", "edificio"]
    assert list(ctx.columns) == inputs_bundle.COLUMNAS_CONTEXTO


def test_con_la_base_completa_y_sin_directorio_no_hay_contexto(base):
    """Con la base completa no hay tabla osm_context: el resultado es un DataFrame vacío con las columnas correctas."""
    ctx = data_access.load_context(base)
    assert ctx.empty and list(ctx.columns) == inputs_bundle.COLUMNAS_CONTEXTO


def test_el_directorio_tiene_prioridad_sobre_la_tabla_del_paquete(paquete, tmp_path):
    """Si se da --contexto, se usa ese directorio aunque el paquete traiga su propia tabla."""
    import json
    d = tmp_path / "ctx"
    d.mkdir()
    (d / "transporte_0.json").write_text(json.dumps({"tema": "transporte", "elements": [
        {"type": "node", "lat": 35.9, "lon": 14.5, "tags": {"highway": "bus_stop"}}]}), encoding="utf-8")
    ctx = data_access.load_context(paquete, str(d))
    assert list(ctx["category"]) == ["transporte"]


def test_sin_contexto_la_tabla_va_vacia_pero_integra(tmp_path, base):
    """Exportar sin contexto da una tabla osm_context vacía y el paquete sigue siendo íntegro."""
    out = tmp_path / "p.sqlite"
    inputs_bundle.export_bundle(base, out, None)
    assert inputs_bundle.verify_bundle(out) == [] and data_access.load_context(out).empty


# ---- procedencia -------------------------------------------------------------------------------------------------
def test_provenance_incluye_el_hash_del_archivo_y_los_datos_del_manifiesto(paquete):
    """La procedencia de un resultado dice qué paquete y qué versiones lo produjeron."""
    p = inputs_bundle.provenance(paquete, commit="def5678")
    assert p["entrada_sha256"] == sha(paquete) and p["commit"] == "def5678"
    assert p["entrada_commit"] == "abc1234" and p["version.scikit-learn"]


def test_provenance_con_la_base_completa_no_tiene_datos_de_manifiesto(base):
    """Con la base completa no hay manifiesto; la procedencia lo omite en vez de fallar."""
    p = inputs_bundle.provenance(base)
    assert "entrada_creada" not in p and p["commit"] == "desconocido"


# ---- herramientas ------------------------------------------------------------------------------------------------
def test_export_ml_inputs_crea_y_verifica(tmp_path, base, capsys):
    """La herramienta escribe el paquete, lo verifica y se niega a pisarlo sin --force."""
    out = tmp_path / "salida" / "p.sqlite"
    assert exportador.main(["--db", str(base), "--out", str(out)]) == 0
    assert "pois" in capsys.readouterr().out and out.exists()
    assert exportador.main(["--verify", str(out)]) == 0
    assert "íntegro" in capsys.readouterr().out
    assert exportador.main(["--db", str(base), "--out", str(out)]) == 1
    assert "ya existe" in capsys.readouterr().out
    assert exportador.main(["--db", str(base), "--out", str(out), "--force"]) == 0


def test_export_ml_inputs_verify_falla_con_un_paquete_alterado(paquete, capsys):
    """--verify sale con 1 y nombra la tabla alterada."""
    conn = sqlite3.connect(paquete)
    conn.execute("DELETE FROM pois WHERE rowid = 1")
    conn.commit()
    conn.close()
    assert exportador.main(["--verify", str(paquete)]) == 1
    assert "pois" in capsys.readouterr().out


def test_export_ml_inputs_avisa_si_el_directorio_de_contexto_esta_vacio(tmp_path, base, capsys):
    """Un directorio de contexto sin JSON válidos no rompe la exportación, pero avisa."""
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    assert exportador.main(["--db", str(base), "--out", str(tmp_path / "p.sqlite"), "--contexto", str(vacio)]) == 0
    assert "AVISO" in capsys.readouterr().out


def test_export_ml_inputs_no_exporta_sobre_la_base(base, capsys):
    """Apuntar --out a la base de origen se rechaza sin tocarla."""
    antes = sha(base)
    assert exportador.main(["--db", str(base), "--out", str(base), "--force"]) == 1
    assert sha(base) == antes


def test_validate_location_model_rechaza_un_paquete_alterado(paquete, capsys):
    """La herramienta de validación comprueba el paquete antes de entrenar y no sigue si no coincide."""
    conn = sqlite3.connect(paquete)
    conn.execute("UPDATE zone_demographics SET population = 1")
    conn.commit()
    conn.close()
    assert vlm.main(["--db", str(paquete), "--target", "food_drink", "--repeats", "1"]) == 1
    assert "no coincide" in capsys.readouterr().out


def test_measure_lens_variance_da_lo_mismo_con_el_paquete_que_con_la_base(base, paquete, tmp_path, capsys):
    """Los indicadores de las lentes salen idénticos desde la base y desde el paquete (sin contexto en ambos)."""
    sin_ctx = tmp_path / "sin_ctx.sqlite"
    inputs_bundle.export_bundle(base, sin_ctx, None)
    mlv.main(["--db", str(base)])
    desde_base = capsys.readouterr().out
    mlv.main(["--db", str(sin_ctx)])
    assert capsys.readouterr().out == desde_base


def test_measure_lens_variance_usa_el_contexto_del_paquete(paquete, capsys):
    """Sin --contexto, el contexto que lleva el paquete se suma a los conteos y se informa."""
    mlv.main(["--db", str(paquete)])
    salida = capsys.readouterr().out
    assert "Contexto de OSM cargado" in salida and "edificio" in salida


def test_requirements_fija_scipy_y_statsmodels():
    """Las dos librerías estadísticas del dashboard van con == (antes >=): una versión nueva puede cambiar resultados o
    no tener wheels para el Python de Docker y CI."""
    lineas = [l.split("#")[0].strip().lower() for l in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()]
    for paquete in ("scipy", "statsmodels"):
        fijas = [l for l in lineas if l.startswith(paquete)]
        assert len(fijas) == 1 and fijas[0].startswith(paquete + "=="), f"{paquete} no está fijado con == en requirements.txt"


def test_requirements_ml_fija_versiones_exactas():
    """requirements-ml.txt fija con == las librerías que cambian los números, y coinciden con las de requirements.txt
    cuando esta también las fija."""
    def pins(nombre):
        out = {}
        for linea in (ROOT / nombre).read_text(encoding="utf-8").splitlines():
            linea = linea.split("#")[0].strip()
            if "==" in linea:
                k, v = linea.split("==")
                out[k.strip().lower()] = v.strip()
        return out
    ml, base = pins("requirements-ml.txt"), pins("requirements.txt")
    assert {"pandas", "numpy", "scikit-learn", "scipy"} <= set(ml)
    for k in ("pandas", "numpy"):
        assert ml[k] == base[k], f"{k} distinto entre requirements.txt y requirements-ml.txt"
