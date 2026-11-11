"""Pruebas de los dos recolectores de POIs (`src/poi_extraction.py`, Overpass, y
`src/poi_extraction_foursquare.py`, Foursquare).

No hacen llamadas de red: el cliente es un doble y la base de datos es un SQLite
temporal. Los archivos que los módulos escriben en `logs/` (heartbeat, contador de
llamadas) se redirigen a `tmp_path`.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import poi_extraction as ov
from src import poi_extraction_foursquare as fs
from src.database import RouteDatabase


class ClienteFalso:
    """Doble de OverpassClient / FoursquareClient."""

    def __init__(self, pois=None, error=None):
        self.pois = pois or []
        self.error = error
        self.llamadas = []
        self.cerrado = 0

    def fetch_pois(self, *args, **kwargs):
        self.llamadas.append((args, kwargs))
        if self.error:
            raise self.error
        return self.pois

    def close(self):
        self.cerrado += 1


@pytest.fixture
def db(tmp_path):
    return RouteDatabase(tmp_path / "datos.csv", tmp_path / "mobility.db")


@pytest.fixture
def logs(tmp_path, monkeypatch):
    """Redirige el directorio de logs (heartbeat y contador) de ambos módulos."""
    destino = tmp_path / "logs"
    destino.mkdir()
    monkeypatch.setattr(ov, "LOG_DIR", destino)
    monkeypatch.setattr(fs, "LOG_DIR", destino)
    monkeypatch.setattr(fs, "CALL_COUNTER_PATH", destino / "foursquare_calls_this_month.json")
    return destino


def _pois_osm(n):
    return [
        {
            "osm_type": "node",
            "osm_id": i,
            "category": "business" if i % 2 else "school",
            "subcategory": "x",
            "name": f"p{i}",
            "latitude": 35.9,
            "longitude": 14.4,
        }
        for i in range(n)
    ]


def _pois_fsq(n):
    return [
        {
            "fsq_place_id": f"f{i}",
            "category": "restaurant",
            "subcategory": "Bar",
            "name": f"p{i}",
            "latitude": 35.9,
            "longitude": 14.4,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Overpass: run_once y heartbeat
# ---------------------------------------------------------------------------


def test_overpass_run_once_guarda_los_pois_y_escribe_el_heartbeat(db, logs):
    """`run_once` de Overpass guarda los POIs en la base y escribe el heartbeat."""
    cliente = ClienteFalso(_pois_osm(4))
    assert ov.run_once(db, cliente, margin_deg=0.02) == 4
    assert len(db.get_pois()) == 4
    assert (logs / "poi_heartbeat").exists()


def test_overpass_run_once_pasa_el_margen_al_cliente(db, logs):
    """`run_once` de Overpass pasa el margen indicado al cliente."""
    cliente = ClienteFalso(_pois_osm(1))
    ov.run_once(db, cliente, margin_deg=0.033)
    assert cliente.llamadas[0][1] == {"margin_deg": 0.033}


def test_overpass_un_segundo_ciclo_actualiza_en_vez_de_duplicar(db, logs):
    """Un segundo ciclo de Overpass actualiza los POIs existentes en vez de duplicarlos."""
    cliente = ClienteFalso(_pois_osm(3))
    ov.run_once(db, cliente, margin_deg=0.015)
    ov.run_once(db, cliente, margin_deg=0.015)
    assert len(db.get_pois()) == 3


def test_overpass_si_la_descarga_falla_devuelve_0_y_no_toca_nada(db, logs, caplog):
    """Si la descarga de Overpass falla, `run_once` devuelve 0, no guarda nada y no escribe el heartbeat."""
    cliente = ClienteFalso(error=RuntimeError("Overpass caído"))
    with caplog.at_level(logging.ERROR):
        assert ov.run_once(db, cliente, margin_deg=0.015) == 0
    assert db.get_pois().empty
    assert not (logs / "poi_heartbeat").exists()  # sin ciclo bueno no hay señal de salud
    assert "Overpass caído" in caplog.text


def test_overpass_heartbeat_contiene_una_fecha_iso_utc(logs):
    """El heartbeat de Overpass contiene una fecha ISO en UTC reciente."""
    ov._write_heartbeat()
    fecha = datetime.fromisoformat((logs / "poi_heartbeat").read_text())
    assert fecha.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - fecha).total_seconds()) < 60


def test_overpass_heartbeat_no_rompe_si_no_puede_escribir(tmp_path, monkeypatch, caplog):
    """El heartbeat de Overpass no rompe el ciclo si no puede escribirse; deja un aviso en el log."""
    monkeypatch.setattr(ov, "LOG_DIR", tmp_path / "no_existe")
    with caplog.at_level(logging.WARNING):
        ov._write_heartbeat()  # no lanza
    assert "heartbeat" in caplog.text.lower()


# ---------------------------------------------------------------------------
# Overpass: main
# ---------------------------------------------------------------------------


@pytest.fixture
def main_overpass(monkeypatch):
    """Prepara ov.main() con doble de cliente/BD y run_once registrado."""
    estado = {"cliente": ClienteFalso(), "ciclos": [], "esperas": []}
    monkeypatch.setattr(ov, "RouteDatabase", lambda *a, **k: "bd")
    monkeypatch.setattr(ov, "OverpassClient", lambda: estado["cliente"])
    monkeypatch.setattr(ov, "run_once", lambda db, cl, margen: estado["ciclos"].append((db, cl, margen)) or 0)
    return estado


def test_overpass_main_sin_intervalo_hace_un_ciclo_y_cierra_el_cliente(main_overpass, monkeypatch):
    """`main` de Overpass sin intervalo hace un único ciclo con el margen indicado y cierra el cliente."""
    monkeypatch.setattr(sys, "argv", ["poi_extraction", "--margin-deg", "0.05"])
    ov.main()
    assert main_overpass["ciclos"] == [("bd", main_overpass["cliente"], 0.05)]
    assert main_overpass["cliente"].cerrado == 1


def test_overpass_main_con_intervalo_repite_y_ctrl_c_sale_con_0(main_overpass, monkeypatch):
    """`main` de Overpass con intervalo repite los ciclos esperando el intervalo en horas, y Ctrl+C sale con código 0."""

    def dormir(segundos):
        main_overpass["esperas"].append(segundos)
        if len(main_overpass["esperas"]) == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(ov.time, "sleep", dormir)
    monkeypatch.setattr(sys, "argv", ["poi_extraction", "--interval-hours", "2"])
    with pytest.raises(SystemExit) as salida:
        ov.main()
    assert salida.value.code == 0
    assert main_overpass["esperas"] == [7200, 7200]
    assert len(main_overpass["ciclos"]) == 2
    assert main_overpass["cliente"].cerrado == 1


def test_overpass_main_un_error_fatal_sale_con_1_y_cierra_el_cliente(main_overpass, monkeypatch):
    """Un error fatal en `main` de Overpass sale con código 1 y cierra el cliente."""

    def romper(*args):
        raise RuntimeError("fallo")

    monkeypatch.setattr(ov, "run_once", romper)
    monkeypatch.setattr(sys, "argv", ["poi_extraction"])
    with pytest.raises(SystemExit) as salida:
        ov.main()
    assert salida.value.code == 1
    assert main_overpass["cliente"].cerrado == 1


# ---------------------------------------------------------------------------
# Foursquare: contador de llamadas
# ---------------------------------------------------------------------------


def test_contador_nuevo_empieza_en_las_llamadas_dadas_y_guarda_el_mes(logs):
    """El contador mensual nuevo empieza con las llamadas dadas y guarda el mes en curso."""
    assert fs._bump_call_counter(27) == 27
    guardado = json.loads(fs.CALL_COUNTER_PATH.read_text())
    assert guardado == {"month": datetime.now(timezone.utc).strftime("%Y-%m"), "calls": 27}


def test_contador_acumula_dentro_del_mismo_mes(logs):
    """El contador mensual acumula las llamadas dentro del mismo mes."""
    fs._bump_call_counter(27)
    assert fs._bump_call_counter(27) == 54


def test_contador_se_reinicia_al_cambiar_de_mes(logs):
    """El contador mensual se reinicia al cambiar de mes."""
    fs.CALL_COUNTER_PATH.write_text(json.dumps({"month": "2000-01", "calls": 499}))
    assert fs._bump_call_counter(27) == 27


def test_contador_corrupto_se_reinicia_sin_fallar(logs):
    """Un contador corrupto se reinicia sin fallar."""
    fs.CALL_COUNTER_PATH.write_text("{esto no es json")
    assert fs._bump_call_counter(5) == 5


def test_contador_no_rompe_si_no_puede_guardar(logs, caplog):
    """El contador devuelve la cuenta aunque no pueda guardarla y deja un aviso en el log."""
    fs.CALL_COUNTER_PATH.mkdir()  # una carpeta donde debería ir el archivo: escribir falla
    with caplog.at_level(logging.WARNING):
        assert fs._bump_call_counter(3) == 3  # devuelve la cuenta igualmente
    assert "contador" in caplog.text


# ---------------------------------------------------------------------------
# Foursquare: run_once
# ---------------------------------------------------------------------------


def test_foursquare_run_once_guarda_los_pois_cuenta_las_llamadas_y_escribe_el_heartbeat(db, logs):
    """`run_once` de Foursquare guarda los POIs, suma las llamadas del ciclo al contador y escribe el heartbeat."""
    cliente = ClienteFalso(_pois_fsq(5))
    assert fs.run_once(db, cliente) == 5
    assert len(db.get_pois_foursquare()) == 5
    assert (logs / "foursquare_heartbeat").exists()
    n_llamadas = len(fs.build_search_points(fs.LOCATIONS, fs.ROUTES))
    assert json.loads(fs.CALL_COUNTER_PATH.read_text())["calls"] == n_llamadas


def test_foursquare_run_once_pide_zonas_y_rutas_al_cliente(db, logs):
    """`run_once` de Foursquare pide al cliente las zonas y las rutas."""
    cliente = ClienteFalso(_pois_fsq(1))
    fs.run_once(db, cliente)
    args, kwargs = cliente.llamadas[0]
    assert args == (fs.LOCATIONS,)
    assert kwargs == {"routes": fs.ROUTES}


def test_foursquare_avisa_al_superar_el_limite_mensual(db, logs, caplog):
    """Foursquare avisa al superar el límite mensual del tier gratis."""
    mes = datetime.now(timezone.utc).strftime("%Y-%m")
    fs.CALL_COUNTER_PATH.write_text(json.dumps({"month": mes, "calls": fs.FREE_TIER_MONTHLY_LIMIT}))
    with caplog.at_level(logging.WARNING):
        fs.run_once(db, ClienteFalso(_pois_fsq(1)))
    assert "Se superó el estimado del tier gratis" in caplog.text


def test_foursquare_no_avisa_si_queda_margen(db, logs, caplog):
    """Foursquare no avisa si queda margen sobre el límite mensual."""
    with caplog.at_level(logging.WARNING):
        fs.run_once(db, ClienteFalso(_pois_fsq(1)))
    assert "Se superó" not in caplog.text


def test_foursquare_heartbeat_no_rompe_si_no_puede_escribir(tmp_path, monkeypatch, caplog):
    """El heartbeat de Foursquare no rompe el ciclo si no puede escribirse; deja un aviso en el log."""
    monkeypatch.setattr(fs, "LOG_DIR", tmp_path / "no_existe")
    with caplog.at_level(logging.WARNING):
        fs._write_heartbeat()
    assert "heartbeat" in caplog.text.lower()


# ---------------------------------------------------------------------------
# Foursquare: main
# ---------------------------------------------------------------------------


@pytest.fixture
def main_foursquare(monkeypatch):
    estado = {"cliente": ClienteFalso(), "ciclos": [], "claves": [], "esperas": []}

    def crear_cliente(api_key):
        estado["claves"].append(api_key)
        return estado["cliente"]

    monkeypatch.setattr(fs, "RouteDatabase", lambda *a, **k: "bd")
    monkeypatch.setattr(fs, "FoursquareClient", crear_cliente)
    monkeypatch.setattr(fs, "run_once", lambda db, cl: estado["ciclos"].append((db, cl)) or 0)
    return estado


def test_foursquare_main_sin_clave_sale_con_1_sin_crear_el_cliente(main_foursquare, monkeypatch, caplog):
    """Sin `FOURSQUARE_API_KEY`, `main` de Foursquare sale con código 1 sin crear el cliente."""
    monkeypatch.delenv("FOURSQUARE_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["poi_extraction_foursquare"])
    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as salida:
            fs.main()
    assert salida.value.code == 1
    assert main_foursquare["claves"] == []
    assert "FOURSQUARE_API_KEY" in caplog.text


def test_foursquare_main_con_clave_hace_un_ciclo_y_cierra_el_cliente(main_foursquare, monkeypatch):
    """Con clave, `main` de Foursquare hace un único ciclo y cierra el cliente."""
    monkeypatch.setenv("FOURSQUARE_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(sys, "argv", ["poi_extraction_foursquare"])
    fs.main()
    assert main_foursquare["claves"] == ["clave-de-prueba"]
    assert main_foursquare["ciclos"] == [("bd", main_foursquare["cliente"])]
    assert main_foursquare["cliente"].cerrado == 1


def test_foursquare_main_con_intervalo_repite_y_ctrl_c_sale_con_0(main_foursquare, monkeypatch):
    """`main` de Foursquare con intervalo repite los ciclos esperando el intervalo en horas, y Ctrl+C sale con código 0."""
    monkeypatch.setenv("FOURSQUARE_API_KEY", "k")

    def dormir(segundos):
        main_foursquare["esperas"].append(segundos)
        if len(main_foursquare["esperas"]) == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(fs.time, "sleep", dormir)
    monkeypatch.setattr(sys, "argv", ["poi_extraction_foursquare", "--interval-hours", "168"])
    with pytest.raises(SystemExit) as salida:
        fs.main()
    assert salida.value.code == 0
    assert main_foursquare["esperas"] == [168 * 3600] * 2
    assert main_foursquare["cliente"].cerrado == 1


def test_foursquare_main_un_error_fatal_sale_con_1_y_cierra_el_cliente(main_foursquare, monkeypatch):
    """Un error fatal en `main` de Foursquare sale con código 1 y cierra el cliente."""
    monkeypatch.setenv("FOURSQUARE_API_KEY", "k")

    def romper(*args):
        raise RuntimeError("fallo")

    monkeypatch.setattr(fs, "run_once", romper)
    monkeypatch.setattr(sys, "argv", ["poi_extraction_foursquare"])
    with pytest.raises(SystemExit) as salida:
        fs.main()
    assert salida.value.code == 1
    assert main_foursquare["cliente"].cerrado == 1
