"""Tests de la fase 1b: contexto de OpenStreetMap (src/ml/osm_context.py) y su efecto en las lentes, las variables y los
modelos, y la herramienta de descarga tools/download_osm_context.py (sin red: cliente falso)."""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import business_profiles as bp  # noqa: E402
from src.ml import features, grid, models, osm_context, validation  # noqa: E402
from src.ml.cell_counts import CellCounts, Selector  # noqa: E402
from src.ml.lenses import compute_lenses  # noqa: E402

_s = importlib.util.spec_from_file_location("download_osm_context", ROOT / "tools" / "download_osm_context.py")
dl = importlib.util.module_from_spec(_s)
_s.loader.exec_module(dl)
_s2 = importlib.util.spec_from_file_location("validate_location_model", ROOT / "tools" / "validate_location_model.py")
vlm = importlib.util.module_from_spec(_s2)
_s2.loader.exec_module(vlm)
_s3 = importlib.util.spec_from_file_location("measure_lens_variance", ROOT / "tools" / "measure_lens_variance.py")
mlv = importlib.util.module_from_spec(_s3)
_s3.loader.exec_module(mlv)


def punto(fila, col, cat, sub):
    lat, lon = grid.cell_center(fila, col)
    return {"category": cat, "subcategory": sub, "latitude": float(lat), "longitude": float(lon)}


def nodo(fila, col, **tags):
    lat, lon = grid.cell_center(fila, col)
    return {"type": "node", "id": 1, "lat": float(lat), "lon": float(lon), "tags": tags}


def via(fila, col, **tags):
    lat, lon = grid.cell_center(fila, col)
    return {"type": "way", "id": 2, "center": {"lat": float(lat), "lon": float(lon)}, "tags": tags}


# ---------------------------------------------------------------------------
# Conversión del contexto
# ---------------------------------------------------------------------------

def test_edificios_se_convierten_con_su_tipo_y_yes_por_defecto():
    """Los edificios de OSM se convierten en POIs de categoría «edificio» con su tipo como subcategoría, y «yes» si no tienen tipo."""
    df = osm_context.elements_to_pois("edificios", [via(20, 20, building="apartments"), via(20, 21, building="yes"),
                                                    via(20, 22)])
    assert list(df["category"].unique()) == ["edificio"] and df["subcategory"].tolist() == ["apartments", "yes", "yes"]


def test_los_elementos_sin_coordenadas_se_descartan():
    """Los elementos de OSM sin coordenadas se descartan."""
    df = osm_context.elements_to_pois("edificios", [{"type": "way", "id": 3, "tags": {"building": "yes"}},
                                                    via(20, 20, building="yes")])
    assert len(df) == 1


def test_transporte_conserva_paradas_y_descarta_las_posiciones_duplicadas():
    """En transporte se conservan paradas, estaciones, andenes y terminales de ferry, y se descartan las posiciones de parada duplicadas."""
    df = osm_context.elements_to_pois("transporte", [
        nodo(20, 20, highway="bus_stop"), nodo(20, 21, public_transport="stop_position"),
        nodo(20, 22, amenity="ferry_terminal"), nodo(20, 23, railway="station"), nodo(20, 24, public_transport="platform")])
    assert sorted(df["subcategory"]) == ["bus_stop", "ferry", "platform", "station"]


def test_alojamiento_e_industria():
    """Alojamiento e industria se convierten en POIs con el tipo de OSM como subcategoría."""
    aloj = osm_context.elements_to_pois("alojamiento", [nodo(20, 20, tourism="hotel"), via(20, 21, tourism="hostel")])
    assert aloj["subcategory"].tolist() == ["hotel", "hostel"] and set(aloj["category"]) == {"alojamiento"}
    ind = osm_context.elements_to_pois("industria", [via(20, 20, landuse="industrial"), nodo(20, 21, shop="wholesale")])
    assert ind["subcategory"].tolist() == ["industrial", "wholesale"]


def test_un_tema_desconocido_o_sin_uso_da_un_dataframe_vacio_con_las_columnas():
    """Un tema desconocido o que no se usa devuelve una tabla vacía pero con sus columnas."""
    df = osm_context.elements_to_pois("suelo_residencial", [via(20, 20, landuse="residential")])
    assert df.empty and list(df.columns) == ["category", "subcategory", "latitude", "longitude"]


def test_load_context_lee_los_json_ignora_los_corruptos_y_un_directorio_vacio_da_vacio(tmp_path):
    """`load_context` lee los JSON de la carpeta, ignora los corruptos y devuelve una tabla vacía si el directorio no tiene datos."""
    (tmp_path / "edificios_0.json").write_text(json.dumps({"tema": "edificios", "trozo": 0, "elements": [via(20, 20, building="house")]}))
    (tmp_path / "alojamiento_0.json").write_text(json.dumps({"tema": "alojamiento", "trozo": 0, "elements": [nodo(21, 21, tourism="hotel")]}))
    (tmp_path / "roto.json").write_text("{esto no es json")
    df = osm_context.load_context(tmp_path)
    assert sorted(df["category"]) == ["alojamiento", "edificio"]
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    assert osm_context.load_context(vacio).empty


def test_no_residenciales_excluye_lo_que_no_es_vivienda():
    """La lista de edificios no residenciales incluye los industriales, iglesias, escuelas y garajes, y no las viviendas."""
    assert {"industrial", "church", "school", "garage"} <= osm_context.NO_RESIDENCIALES
    assert not ({"yes", "apartments", "house", "residential", "terrace"} & osm_context.NO_RESIDENCIALES)


# ---------------------------------------------------------------------------
# Efecto en los conteos, las lentes y las variables
# ---------------------------------------------------------------------------

def _con_contexto():
    pois = pd.DataFrame([punto(20, 20, "food_drink", "cafe"), punto(20, 21, "school", "school")])
    filas_ctx = ([punto(20, 20, "edificio", "yes")] * 6
                 + [punto(20, 20, "edificio", "industrial"), punto(20, 20, "alojamiento", "hotel"), punto(5, 5, "edificio", "yes")])
    ctx = pd.DataFrame(filas_ctx)
    return CellCounts.from_pois(pd.concat([pois, ctx], ignore_index=True))


def test_las_celdas_activas_no_cambian_al_cargar_el_contexto():
    """Un edificio lejos de cualquier POI no activa una celda: así el conjunto de celdas es el mismo con y sin contexto."""
    sin = CellCounts.from_pois(pd.DataFrame([punto(20, 20, "food_drink", "cafe"), punto(20, 21, "school", "school")]))
    con = _con_contexto()
    np.testing.assert_array_equal(sin.active_mask(), con.active_mask())
    assert not con.active_mask()[5, 5]


def test_residentes_cuenta_edificios_pero_no_los_industriales():
    """La lente de residentes cuenta los edificios de vivienda de la celda pero no los industriales."""
    lentes = compute_lenses(_con_contexto(), bp.get_default_profile("food_drink"))
    assert lentes.loc["r20c20", "mercado_residentes"] == 6.0               # 6 'yes'; el industrial no cuenta
    assert lentes["mercado_estudiantes"].notna().all()


def test_los_hoteles_cuentan_como_turistas_aunque_no_haya_atracciones():
    """Los hoteles cuentan como turistas en su celda aunque no haya atracciones."""
    lentes = compute_lenses(_con_contexto(), bp.get_default_profile("food_drink"))
    assert lentes.loc["r20c20", "mercado_turistas"] == 1.0


def test_sin_contexto_residentes_y_turistas_siguen_sin_datos():
    """Sin contexto de OSM, las lentes de residentes y turistas quedan sin dato (NaN)."""
    cc = CellCounts.from_pois(pd.DataFrame([punto(20, 20, "food_drink", "cafe")]))
    lentes = compute_lenses(cc, bp.get_default_profile("food_drink"))
    assert lentes["mercado_residentes"].isna().all() and lentes["mercado_turistas"].isna().all()


def test_el_indice_de_mercado_va_de_0_a_1_y_los_edificios_no_aplastan_a_los_demas_segmentos():
    """Regresión: mercado_total sumaba conteos en bruto, y con ~90 edificios por celda frente a ~1 colegio el índice era
    solo 'cuántos edificios hay'. Ahora cada segmento se escala por su máximo antes de promediar."""
    filas = [punto(30, 30, "school", "school")] + [punto(10, 10, "edificio", "yes")] * 200 + [punto(10, 10, "food_drink", "cafe")]
    cc = CellCounts.from_pois(pd.DataFrame(filas))
    lentes = compute_lenses(cc, bp.get_default_profile("food_drink"), np.ones(grid.SHAPE, dtype=bool))
    assert lentes["mercado_total"].between(0, 1).all()
    colegio, edificios = lentes.loc["r30c30", "mercado_total"], lentes.loc["r10c10", "mercado_total"]
    assert colegio == pytest.approx(edificios, rel=0.01)        # cada segmento en su máximo vale lo mismo (media de 2 segmentos)


def test_el_indice_de_mercado_es_una_media_y_no_una_suma():
    """Una celda que es el máximo en TODOS los segmentos con datos vale exactamente 1 (con una suma valdría 2)."""
    cc = CellCounts.from_pois(pd.DataFrame([punto(10, 10, "school", "school"), punto(10, 10, "edificio", "yes"),
                                            punto(10, 10, "food_drink", "cafe")]))
    lentes = compute_lenses(cc, bp.get_default_profile("food_drink"), np.ones(grid.SHAPE, dtype=bool))
    assert lentes.loc["r10c10", "mercado_total"] == pytest.approx(1.0)


def test_las_variables_incluyen_el_contexto_solo_si_se_piden():
    """Las variables del modelo incluyen las de contexto solo si se piden, y el índice de celdas es el mismo."""
    cc = _con_contexto()
    sin = features.build_features(cc, [Selector("food_drink")])
    con = features.build_features(cc, [Selector("food_drink")], categorias=features.CATEGORIAS + osm_context.CONTEXTO)
    assert not any(c.startswith("edificio_") for c in sin.columns)
    assert con.loc["r20c20", "edificio_celda"] == 7 and con.loc["r20c20", "alojamiento_celda"] == 1
    assert list(con.index) == list(sin.index)                       # las mismas celdas


# ---------------------------------------------------------------------------
# Modelos y validación con contexto
# ---------------------------------------------------------------------------

def _x_con_contexto():
    rng = np.random.default_rng(0)
    f, c = np.meshgrid(np.arange(16) + 10, np.arange(20) + 10, indexing="ij")
    ids = [grid.cell_id(a, b) for a, b in zip(f.ravel(), c.ravel())]
    cats = features.CATEGORIAS + osm_context.CONTEXTO
    X = pd.DataFrame({f"{cat}_{z}": rng.poisson(1.5, len(ids)).astype(float) for cat in cats for z in ("celda", "anillo1", "anillo2")},
                     index=pd.Index(ids, name="cell_id"))
    X["dist_centro_m"], X["pob_suavizada"], X["tiempo_viaje_suavizado"] = rng.uniform(0, 3000, len(ids)), 9000.0, 10.0
    y = rng.poisson(0.2 + 0.9 * X["edificio_celda"].to_numpy()).astype(float)
    return X, y


def test_boosting_poi_no_usa_las_variables_de_contexto_y_solo_edificios_solo_esas():
    """El modelo `boosting_poi` no usa las variables de contexto y `solo_edificios` usa únicamente las de edificios."""
    X, _ = _x_con_contexto()
    poi = models.columnas_de("boosting_poi", X)
    assert not any(c.startswith(osm_context.CONTEXTO) for c in poi.columns) and "school_celda" in poi.columns
    assert list(models.columnas_de("solo_edificios", X).columns) == ["edificios_celda", "edificios_anillo1", "edificios_anillo2"]


@pytest.mark.parametrize("nombre", models.OPCIONALES)
def test_los_modelos_opcionales_predicen_valores_positivos(nombre):
    """Los modelos opcionales (parametrizado) predicen valores positivos, por encima del mínimo esperado."""
    X, y = _x_con_contexto()
    p = models.fit_predict(nombre, X.iloc[:200], y[:200], X.iloc[200:])
    assert len(p) == len(X) - 200 and (p >= models.MIN_ESPERADO).all()


def test_el_boosting_con_contexto_gana_al_que_no_lo_tiene_cuando_la_senal_esta_en_el_contexto():
    """Cuando la señal está en el contexto, el boosting con contexto gana al que no lo usa y la comparación lo marca como mejora."""
    X, y = _x_con_contexto()
    ev = validation.evaluate(X, y, nombres=("boosting", "boosting_poi", "solo_densidad"), repeats=2, n_folds=4, seed=1)
    r = validation.compare_models(ev, "boosting", "boosting_poi", n_boot=200)
    assert r["diferencia"] < 0 and r["veredicto"] == "mejora"


def test_compare_models_con_el_mismo_modelo_es_indistinguible():
    """Comparar un modelo consigo mismo da diferencia cero y veredicto «indistinguible»."""
    X, y = _x_con_contexto()
    ev = validation.evaluate(X, y, nombres=("boosting",), repeats=2, n_folds=4, seed=1)
    r = validation.compare_models(ev, "boosting", "boosting", n_boot=100)
    assert r == {"diferencia": 0.0, "ic_inf": 0.0, "ic_sup": 0.0, "veredicto": "indistinguible"}


def _db_y_contexto(tmp_path):
    db = tmp_path / "t.db"
    rng = np.random.default_rng(0)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE pois (id INTEGER PRIMARY KEY, category TEXT, subcategory TEXT, latitude REAL, longitude REAL)")
    for _ in range(600):
        f, c = int(rng.integers(12, 34)), int(rng.integers(10, 32))
        p = punto(f, c, ["food_drink", "business", "school", "sport"][int(rng.integers(0, 4))], "x")
        con.execute("INSERT INTO pois (category, subcategory, latitude, longitude) VALUES (?,?,?,?)",
                    (p["category"], p["subcategory"], p["latitude"], p["longitude"]))
    con.execute("CREATE TABLE zone_demographics (zone_name TEXT, population INTEGER)")
    con.execute("CREATE TABLE route_measurements (origin TEXT, destination TEXT, travel_time_min REAL)")
    con.commit()
    con.close()
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    edificios = [via(int(rng.integers(12, 34)), int(rng.integers(10, 32)), building="yes") for _ in range(500)]
    (ctx / "edificios_0.json").write_text(json.dumps({"tema": "edificios", "trozo": 0, "elements": edificios}))
    return db, ctx


def test_validate_location_model_con_contexto_informa_si_el_contexto_aporta(tmp_path, capsys):
    """El script de validación con contexto informa de si el contexto aporta y no modifica la base de datos."""
    db, ctx = _db_y_contexto(tmp_path)
    antes = db.read_bytes()
    assert vlm.main(["--db", str(db), "--contexto", str(ctx), "--target", "food_drink", "--repeats", "2", "--folds", "3", "--boot", "50"]) == 0
    salida = capsys.readouterr().out
    assert "Contexto de OSM (fase 1b)" in salida and "¿Aporta el contexto" in salida
    assert "boosting_poi" in salida and "solo_edificios" in salida
    assert db.read_bytes() == antes


def test_validate_location_model_sin_contexto_no_evalua_los_modelos_opcionales(tmp_path, capsys):
    """Sin contexto, el script de validación no evalúa los modelos opcionales."""
    db, _ = _db_y_contexto(tmp_path)
    assert vlm.main(["--db", str(db), "--target", "food_drink", "--repeats", "2", "--folds", "3", "--boot", "50"]) == 0
    salida = capsys.readouterr().out
    assert "¿Aporta el contexto" not in salida and "boosting_poi" not in salida


def test_validate_location_model_con_un_directorio_de_contexto_vacio_valida_sin_contexto(tmp_path, capsys):
    """Con un directorio de contexto vacío, el script valida sin contexto y lo avisa."""
    db, _ = _db_y_contexto(tmp_path)
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    assert vlm.main(["--db", str(db), "--contexto", str(vacio), "--target", "business", "--repeats", "2", "--folds", "3", "--boot", "30"]) == 0
    assert "directorio sin datos válidos" in capsys.readouterr().out


def test_measure_lens_variance_con_contexto_da_datos_a_residentes(tmp_path, capsys):
    """El script de varianza de lentes, con contexto, da datos a la lente de residentes."""
    db, ctx = _db_y_contexto(tmp_path)
    assert mlv.main(["--db", str(db), "--contexto", str(ctx)]) == 0
    salida = capsys.readouterr().out
    assert "Contexto de OSM cargado" in salida and "mercado_residentes" in salida and "(POIs + contexto)" in salida


# ---------------------------------------------------------------------------
# Herramienta de descarga (sin red)
# ---------------------------------------------------------------------------

class Respuesta:
    def __init__(self, datos=None, error=False):
        self.datos, self.error = datos, error

    def raise_for_status(self):
        if self.error:
            raise RuntimeError("HTTP 504")

    def json(self):
        return self.datos


class SesionFalsa:
    def __init__(self, responder):
        self.responder, self.llamadas = responder, []

    def post(self, url, data=None, timeout=None):
        self.llamadas.append((url, data["data"], timeout))
        return self.responder(url, data["data"])


class ClienteFalso:
    def __init__(self, responder, endpoints=("https://uno", "https://dos")):
        self.endpoints, self.session = list(endpoints), SesionFalsa(responder)


def test_las_franjas_cubren_toda_el_area_sin_huecos_ni_solapes():
    """Las franjas de descarga cubren toda el área sin huecos ni solapes, y pedir 0 franjas lanza `ValueError`."""
    franjas = dl.bbox_franjas(3)
    assert franjas[0][0] == grid.SOUTH and franjas[-1][2] == grid.NORTH
    for a, b in zip(franjas, franjas[1:]):
        assert a[2] == pytest.approx(b[0])                       # el norte de una es el sur de la siguiente
    assert all(f[1] == grid.WEST and f[3] == grid.EAST for f in franjas)
    with pytest.raises(ValueError):
        dl.bbox_franjas(0)


def test_la_consulta_lleva_el_bbox_el_timeout_del_servidor_y_pide_centro_y_etiquetas():
    """La consulta lleva el rectángulo, el timeout del servidor y pide el centro y las etiquetas."""
    q = dl.construir_consulta(['way["building"]({bbox});'], (35.84, 14.44, 35.9, 14.5))
    assert "(35.840000,14.440000,35.900000,14.500000)" in q and "[timeout:150]" in q and q.rstrip().endswith("out center tags;")


def test_el_plan_pide_siete_trozos_y_el_edificado_va_en_franjas():
    """El plan de descarga pide siete trozos y el edificado va dividido en tres franjas."""
    plan = dl.consultas(list(dl.TEMAS))
    assert len(plan) == 7 and [t for t, _, _ in plan].count("edificios") == 3
    assert len(dl.consultas(["alojamiento"])) == 1


def test_descargar_guarda_un_archivo_por_trozo_y_resume(tmp_path):
    """La descarga guarda un archivo por trozo y devuelve el resumen de elementos y trozos por tema."""
    cliente = ClienteFalso(lambda url, q: Respuesta({"elements": [nodo(20, 20, tourism="hotel")] * 3}))
    resumen = dl.descargar(cliente, tmp_path / "salida", ["alojamiento", "industria"], pausa_s=0, log=lambda *_: None)
    assert resumen["alojamiento"] == {"elementos": 3, "trozos_ok": 1, "trozos_fallidos": 0}
    assert sorted(p.name for p in (tmp_path / "salida").iterdir()) == ["alojamiento_0.json", "industria_0.json"]
    guardado = json.loads((tmp_path / "salida" / "alojamiento_0.json").read_text())
    assert guardado["tema"] == "alojamiento" and len(guardado["elements"]) == 3


def test_se_espera_entre_peticiones_pero_no_despues_de_la_ultima(tmp_path, monkeypatch):
    """Cortesía con el servicio público: pausa entre peticiones, y ninguna espera inútil al terminar."""
    esperas = []
    monkeypatch.setattr(dl.time, "sleep", lambda s: esperas.append(s))
    cliente = ClienteFalso(lambda url, q: Respuesta({"elements": []}))
    dl.descargar(cliente, tmp_path, ["alojamiento", "industria", "transporte"], pausa_s=7, log=lambda *_: None)
    assert esperas == [7, 7]                                       # 3 peticiones -> 2 pausas


def test_si_un_espejo_falla_se_prueba_el_siguiente():
    """Si un espejo de Overpass falla, se prueba el siguiente."""
    def responder(url, q):
        return Respuesta(error=True) if url == "https://uno" else Respuesta({"elements": [1, 2]})

    cliente = ClienteFalso(responder)
    assert dl.pedir(cliente, "q") == {"elements": [1, 2]} and [c[0] for c in cliente.session.llamadas] == ["https://uno", "https://dos"]


def test_si_todos_los_espejos_fallan_lanza_runtimeerror():
    """Si todos los espejos fallan, se lanza `RuntimeError`."""
    with pytest.raises(RuntimeError, match="Todos los espejos"):
        dl.pedir(ClienteFalso(lambda url, q: Respuesta(error=True)), "q")


def test_un_trozo_fallido_se_anota_y_el_resto_se_descarga(tmp_path):
    """Un trozo fallido se anota en el resumen y el resto se descarga."""
    def responder(url, q):
        return Respuesta(error=True) if "wholesale" in q else Respuesta({"elements": [nodo(20, 20, tourism="hotel")]})

    resumen = dl.descargar(ClienteFalso(responder), tmp_path, ["industria", "alojamiento"], pausa_s=0, log=lambda *_: None)
    assert resumen["industria"]["trozos_fallidos"] == 1 and resumen["alojamiento"]["trozos_ok"] == 1
    assert [p.name for p in tmp_path.iterdir()] == ["alojamiento_0.json"]


def test_dry_run_no_hace_llamadas_de_red_ni_crea_la_carpeta(tmp_path, monkeypatch, capsys):
    """Con `--dry-run` no se crea el cliente, no hay llamadas de red y no se crea la carpeta de salida."""
    monkeypatch.setattr(dl, "OverpassClient", lambda *a, **k: pytest.fail("dry-run no debe crear el cliente"))
    destino = tmp_path / "no_debe_existir"
    assert dl.main(["--out", str(destino), "--dry-run"]) == 0
    assert "dry-run" in capsys.readouterr().out and not destino.exists()


def test_main_descarga_con_un_cliente_falso_y_devuelve_el_codigo_segun_los_fallos(tmp_path, monkeypatch):
    """`main` devuelve 0 si la descarga va bien y 1 si algún trozo falla."""
    monkeypatch.setattr(dl, "OverpassClient", lambda *a, **k: ClienteFalso(lambda url, q: Respuesta({"elements": []})))
    assert dl.main(["--out", str(tmp_path / "a"), "--themes", "alojamiento", "--pausa", "0"]) == 0
    monkeypatch.setattr(dl, "OverpassClient", lambda *a, **k: ClienteFalso(lambda url, q: Respuesta(error=True)))
    assert dl.main(["--out", str(tmp_path / "b"), "--themes", "alojamiento", "--pausa", "0"]) == 1


def test_la_descarga_no_escribe_fuera_del_directorio_indicado(tmp_path):
    """La descarga solo escribe dentro de la carpeta indicada."""
    cliente = ClienteFalso(lambda url, q: Respuesta({"elements": []}))
    carpeta = tmp_path / "solo_aqui"
    dl.descargar(cliente, carpeta, ["alojamiento"], pausa_s=0, log=lambda *_: None)
    assert [p.name for p in tmp_path.iterdir()] == ["solo_aqui"]
