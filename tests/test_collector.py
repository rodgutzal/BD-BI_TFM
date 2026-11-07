"""Tests del orquestador de recolección (src/collector.py): DataCollector de punta a punta y el bucle real de
HybridScheduler.

Sin red ni esperas: los clientes TomTom/ORS/OpenWeather se sustituyen por falsos, `time.sleep` por un contador y
`signal.signal` por un registro (para no tocar el manejador de Ctrl+C de pytest). La base es temporal y el
heartbeat se redirige (el real vive en logs/heartbeat y lo lee el HEALTHCHECK de Docker).
"""

import signal
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import collector  # noqa: E402
from src.locations import ROUTES, get_all_unique_locations  # noqa: E402

N_RUTAS = len(ROUTES)
UBICACIONES = get_all_unique_locations()


class TraficoFalso:
    """Cliente de tráfico falso: tiempo de viaje configurable por ruta (destino), con fallos opcionales."""

    def __init__(self, *_args, **_kwargs):
        self.llamadas, self.cerrado = [], False
        self.minutos = 12.0
        self.tiempos = {}                       # (lat_destino) -> minutos
        self.falla_en = set()                   # latitudes de destino que lanzan error

    def calculate_route(self, o_lat, o_lon, d_lat, d_lon):
        self.llamadas.append((o_lat, o_lon, d_lat, d_lon))
        if d_lat in self.falla_en:
            raise RuntimeError("API caída")
        t = self.tiempos.get(d_lat, self.minutos)
        return {"distance_km": 5.0, "travel_time_min": t, "no_traffic_time_min": t - 1, "traffic_delay_min": 1.0,
                "traffic_length_km": 0.5, "average_speed_kmh": 25.0, "departure_time": None, "arrival_time": None,
                "polyline": None}

    def close(self):
        self.cerrado = True


class ClimaFalso:
    def __init__(self, *_args, **_kwargs):
        self.llamadas, self.cerrado, self.falla_en = [], False, set()

    def get_current_weather(self, lat, lon):
        self.llamadas.append((lat, lon))
        if lat in self.falla_en:
            raise RuntimeError("sin clima")
        return {"temperature": 21.0, "feels_like": 22.0, "humidity": 55, "weather": "cielo claro"}

    def close(self):
        self.cerrado = True


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Sustituye clientes, señales y heartbeat. Devuelve una función para crear colectores."""
    monkeypatch.setattr(collector, "TomTomClient", TraficoFalso)
    monkeypatch.setattr(collector, "ORSClient", TraficoFalso)
    monkeypatch.setattr(collector, "WeatherClient", ClimaFalso)
    senales = []
    monkeypatch.setattr(signal, "signal", lambda sig, handler: senales.append((sig, handler)))
    latidos = []
    monkeypatch.setattr(collector.DataCollector, "_write_heartbeat", lambda self: latidos.append(1))

    def crear(fuente="tomtom", **kwargs):
        kwargs.setdefault("register_signal_handler", False)
        return collector.DataCollector(fuente, "clave", "clima", tmp_path / "d.csv", tmp_path / "d.db", **kwargs)

    crear.senales, crear.latidos, crear.tmp = senales, latidos, tmp_path
    return crear


def _tabla(db, sql, params=()):
    con = sqlite3.connect(db)
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Construcción
# ---------------------------------------------------------------------------

def test_rechaza_una_fuente_desconocida(entorno):
    with pytest.raises(ValueError, match="'ors' o 'tomtom'"):
        entorno("google")


def test_la_fuente_elige_el_cliente(entorno, monkeypatch):
    class Tom(TraficoFalso):
        pass

    class Ors(TraficoFalso):
        pass

    monkeypatch.setattr(collector, "TomTomClient", Tom)
    monkeypatch.setattr(collector, "ORSClient", Ors)
    assert isinstance(entorno("tomtom").traffic_client, Tom) and isinstance(entorno("ors").traffic_client, Ors)


def test_timescale_solo_se_activa_con_configuracion(entorno):
    assert entorno().enable_timescale is False
    assert entorno(timescale_config={"host": "x"}).enable_timescale is True
    assert entorno(timescale_config={"host": "x"}, enable_timescale=False).enable_timescale is False


def test_el_manejador_de_ctrl_c_solo_se_registra_si_se_pide(entorno):
    entorno()
    assert entorno.senales == []
    c = entorno(register_signal_handler=True)
    assert entorno.senales == [(signal.SIGINT, c._signal_handler)]


def test_ctrl_c_cierra_los_clientes_y_sale(entorno):
    c = entorno()
    with pytest.raises(SystemExit) as salida:
        c._signal_handler(signal.SIGINT, None)
    assert salida.value.code == 0 and c.running is False
    assert c.traffic_client.cerrado and c.weather.cerrado


# ---------------------------------------------------------------------------
# Un ciclo de recolección
# ---------------------------------------------------------------------------

def test_un_ciclo_guarda_todas_las_rutas_en_csv_y_sqlite(entorno):
    c = entorno()
    assert c.collect_cycle() == N_RUTAS
    csv = pd.read_csv(entorno.tmp / "d.csv")
    db = _tabla(entorno.tmp / "d.db", "SELECT * FROM route_measurements")
    assert len(csv) == len(db) == N_RUTAS
    assert set(zip(csv["origin"], csv["destination"])) == set(ROUTES)
    assert db["timestamp"].nunique() == 1                          # un único instante por ciclo
    assert set(db["data_source"]) == {"tomtom"} and entorno.latidos == [1]


def test_cada_ruta_lleva_el_clima_de_su_origen_y_destino_y_se_pide_una_vez_por_lugar(entorno):
    c = entorno()
    c.collect_cycle()
    assert len(c.weather.llamadas) == len(UBICACIONES)             # no una por ruta
    db = _tabla(entorno.tmp / "d.db", "SELECT * FROM route_measurements")
    assert (db["origin_temperature"] == 21.0).all() and (db["destination_humidity"] == 55).all()
    assert (db["origin_weather"] == "cielo claro").all()


def test_el_nivel_de_movilidad_cambia_justo_por_encima_de_20_minutos(entorno):
    """> 20 min es 'Alta demora'; 20 exactos todavía es normal (umbral estricto)."""
    c = entorno()
    destinos = list(dict.fromkeys(d for _, d in ROUTES))[:3]            # tres destinos distintos
    assert len(destinos) == 3
    tiempos = dict(zip(destinos, [20.0, 20.01, 5.0]))
    c.traffic_client.tiempos = {UBICACIONES[d].latitude: t for d, t in tiempos.items()}
    c.collect_cycle()
    db = _tabla(entorno.tmp / "d.db", "SELECT destination, mobility_level FROM route_measurements")
    nivel = {d: set(g["mobility_level"]) for d, g in db.groupby("destination")}
    assert nivel[destinos[0]] == {"Movilidad normal"}                    # 20,00 -> normal
    assert nivel[destinos[1]] == {"Alta demora"}                         # 20,01 -> alta demora
    assert nivel[destinos[2]] == {"Movilidad normal"}


def test_si_falla_el_clima_de_un_lugar_la_ruta_se_guarda_sin_clima(entorno):
    c = entorno()
    origen = ROUTES[0][0]
    c.weather.falla_en = {UBICACIONES[origen].latitude}
    assert c.collect_cycle() == N_RUTAS
    db = _tabla(entorno.tmp / "d.db", "SELECT * FROM route_measurements WHERE origin = ?", (origen,))
    assert len(db) >= 1 and db["origin_temperature"].isna().all()
    otras = _tabla(entorno.tmp / "d.db", "SELECT * FROM route_measurements WHERE origin != ?", (origen,))
    assert otras["origin_temperature"].notna().any()


def test_si_falla_una_ruta_se_siguen_guardando_las_demas(entorno):
    c = entorno()
    destino = ROUTES[0][1]
    c.traffic_client.falla_en = {UBICACIONES[destino].latitude}
    fallan = sum(1 for _, d in ROUTES if UBICACIONES[d].latitude == UBICACIONES[destino].latitude)
    assert 0 < fallan < N_RUTAS
    assert c.collect_cycle() == N_RUTAS - fallan
    assert len(_tabla(entorno.tmp / "d.db", "SELECT * FROM route_measurements")) == N_RUTAS - fallan


def test_si_fallan_todas_las_rutas_no_se_guarda_nada_ni_hay_latido(entorno):
    c = entorno()
    c.traffic_client.falla_en = {u.latitude for u in UBICACIONES.values()}
    assert c.collect_cycle() == 0
    assert not (entorno.tmp / "d.csv").exists() and entorno.latidos == []


def test_si_falla_el_guardado_devuelve_cero_y_no_hay_latido(entorno, monkeypatch):
    c = entorno()

    def revienta(records):
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(c.db, "save_records_to_sqlite", revienta)
    assert c.collect_cycle() == 0 and entorno.latidos == []


def test_con_timescale_activo_se_guarda_tambien_alli_con_su_configuracion(entorno, monkeypatch):
    config = {"host": "ts", "dbname": "x"}
    c = entorno(timescale_config=config)
    guardado = []
    monkeypatch.setattr(c.db, "save_records_to_timescale", lambda records, cfg: guardado.append((len(records), cfg)))
    c.collect_cycle()
    assert guardado == [(N_RUTAS, config)]


def test_sin_timescale_no_se_intenta_guardar_alli(entorno, monkeypatch):
    c = entorno()
    monkeypatch.setattr(c.db, "save_records_to_timescale", lambda *a: pytest.fail("no debería llamarse"))
    assert c.collect_cycle() == N_RUTAS


def test_el_heartbeat_se_escribe_en_logs_del_proyecto_con_la_hora_del_ciclo(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "__file__", str(tmp_path / "src" / "collector.py"))
    c = collector.DataCollector.__new__(collector.DataCollector)
    c._write_heartbeat()
    escrito = (tmp_path / "logs" / "heartbeat").read_text()
    assert abs((datetime.now(timezone.utc) - datetime.fromisoformat(escrito)).total_seconds()) < 5


def test_un_heartbeat_que_no_se_puede_escribir_no_rompe_el_ciclo(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "__file__", str(tmp_path / "fichero" / "src" / "collector.py"))
    (tmp_path / "fichero").write_text("esto es un archivo, no un directorio")      # mkdir fallará
    c = collector.DataCollector.__new__(collector.DataCollector)
    c._write_heartbeat()                                                          # no lanza


# ---------------------------------------------------------------------------
# Pipeline medallón incremental (Bronze → Silver → Gold)
# ---------------------------------------------------------------------------

def test_el_ciclo_alimenta_bronze_silver_y_gold_solo_con_sus_registros(entorno):
    c = entorno()
    c.collect_cycle()
    bronze = _tabla(entorno.tmp / "d.db", "SELECT * FROM bronze_measurements")
    assert len(bronze) == N_RUTAS
    tablas = set(_tabla(entorno.tmp / "d.db", "SELECT name FROM sqlite_master WHERE type='table'")["name"])
    assert {"silver_measurements", "gold_route_kpis", "gold_route_rankings"} <= tablas
    assert len(_tabla(entorno.tmp / "d.db", "SELECT * FROM silver_measurements")) == N_RUTAS
    assert len(_tabla(entorno.tmp / "d.db", "SELECT * FROM gold_route_kpis")) > 0
    assert len(_tabla(entorno.tmp / "d.db", "SELECT * FROM gold_route_rankings")) > 0


def test_cada_ciclo_procesa_solo_sus_propios_registros_en_silver(entorno):
    """El medallón es incremental: el 2º ciclo transforma únicamente las filas de Bronze de ese ciclo, no todo
    el histórico (sería lento y reprocesaría datos ya vistos)."""
    c = entorno()
    c.collect_cycle()
    c.collect_cycle()
    assert len(_tabla(entorno.tmp / "d.db", "SELECT * FROM bronze_measurements")) == 2 * N_RUTAS
    transformadas = []
    original = collector.SilverLayer.transform_bronze

    def espia(self, df):
        transformadas.append(len(df))
        return original(self, df)

    collector.SilverLayer.transform_bronze = espia
    try:
        c.collect_cycle()
    finally:
        collector.SilverLayer.transform_bronze = original
    assert transformadas == [N_RUTAS]                    # 3 ciclos en Bronze, pero solo 12 filas a Silver


def test_sin_medallon_no_se_crean_las_capas(entorno):
    entorno(enable_medallion=False).collect_cycle()
    tablas = set(_tabla(entorno.tmp / "d.db", "SELECT name FROM sqlite_master WHERE type='table'")["name"])
    assert "bronze_measurements" not in tablas


def test_un_fallo_del_medallon_no_impide_guardar_ni_cambia_el_resultado(entorno, monkeypatch):
    """Executive es una vista adicional: si Bronze revienta, CSV/SQLite ya están guardados y el ciclo cuenta."""
    monkeypatch.setattr(collector, "BronzeLayer", MagicMock(side_effect=RuntimeError("bronze roto")))
    c = entorno()
    assert c.collect_cycle() == N_RUTAS
    assert len(_tabla(entorno.tmp / "d.db", "SELECT * FROM route_measurements")) == N_RUTAS
    assert entorno.latidos == [1]


def test_si_bronze_no_responde_success_se_omite_silver_y_gold(entorno, monkeypatch):
    bronze = MagicMock()
    bronze.return_value.ingest.return_value = {"status": "error"}
    silver, gold = MagicMock(), MagicMock()
    monkeypatch.setattr(collector, "BronzeLayer", bronze)
    monkeypatch.setattr(collector, "SilverLayer", silver)
    monkeypatch.setattr(collector, "GoldLayer", gold)
    # Si se siguiera adelante, lo primero sería leer Bronze: pytest.fail no lo captura el `except Exception`.
    monkeypatch.setattr(collector.pd, "read_sql_query", lambda *a, **k: pytest.fail("no debería seguir tras Bronze"))
    assert entorno().collect_cycle() == N_RUTAS
    silver.assert_not_called()
    gold.assert_not_called()


# ---------------------------------------------------------------------------
# Bucle continuo
# ---------------------------------------------------------------------------

def test_run_once_hace_un_solo_ciclo(entorno, monkeypatch):
    c = entorno()
    ciclos = []
    monkeypatch.setattr(c, "collect_cycle", lambda: ciclos.append(1) or 0)
    c.run_once()
    assert ciclos == [1]


def test_run_continuous_espera_el_intervalo_segundo_a_segundo_y_se_detiene(entorno, monkeypatch):
    c = entorno()
    ciclos, dormidas = [], []
    monkeypatch.setattr(c, "collect_cycle", lambda: ciclos.append(1) or 0)

    def dormir(segundos):
        dormidas.append(segundos)
        if len(ciclos) == 2 and len(dormidas) == 7:             # tras el 2º ciclo y 3 s de espera: parar
            c.running = False
        assert len(dormidas) < 50, "el bucle no se detuvo: el código cambió el reparto de las esperas"

    monkeypatch.setattr(collector.time, "sleep", dormir)
    c.run_continuous(interval_seconds=4)
    assert len(ciclos) == 2 and set(dormidas) == {1}
    assert len(dormidas) == 7                                    # 4 s tras el 1er ciclo + 3 s tras el 2º


def test_run_continuous_termina_si_se_detiene_durante_el_ciclo(entorno, monkeypatch):
    c = entorno()

    def ciclo():
        c.running = False
        return 0

    monkeypatch.setattr(c, "collect_cycle", ciclo)
    monkeypatch.setattr(collector.time, "sleep", lambda s: pytest.fail("no debería esperar"))
    c.run_continuous(interval_seconds=60)


# ---------------------------------------------------------------------------
# HybridScheduler: el bucle REAL (no una réplica de su lógica)
# ---------------------------------------------------------------------------

@pytest.fixture
def hibrido(monkeypatch):
    senales = []
    monkeypatch.setattr(signal, "signal", lambda sig, handler: senales.append((sig, handler)))
    ors, tom = MagicMock(), MagicMock()
    h = collector.HybridScheduler(ors, tom, ors_interval_min=15, tomtom_interval_min=27)
    h.senales, h.ors, h.tom = senales, ors, tom
    return h


def _parar_tras(h, monkeypatch, esperas):
    cuenta = {"n": 0}

    def dormir(_s):
        cuenta["n"] += 1
        if cuenta["n"] >= esperas:
            h.running = False
        assert cuenta["n"] < esperas + 50, "el bucle no se detuvo"

    monkeypatch.setattr(collector.time, "sleep", dormir)


def test_el_hibrido_registra_un_unico_manejador_y_guarda_los_intervalos(hibrido):
    assert hibrido.senales == [(signal.SIGINT, hibrido._signal_handler)]
    assert [e["name"] for e in hibrido.entries] == ["ors", "tomtom"]
    assert [e["interval"] for e in hibrido.entries] == [timedelta(minutes=15), timedelta(minutes=27)]


def test_en_el_primer_tick_corren_las_dos_fuentes_y_despues_ninguna_hasta_su_intervalo(hibrido, monkeypatch):
    _parar_tras(hibrido, monkeypatch, esperas=3)                 # 3 ticks de 1 s
    hibrido.run(tick_seconds=1)
    assert hibrido.ors.collect_cycle.call_count == 1 and hibrido.tom.collect_cycle.call_count == 1
    assert all(e["last_run"] is not None for e in hibrido.entries)


def test_una_fuente_vencida_corre_y_la_otra_no(hibrido, monkeypatch):
    ahora = datetime.now(timezone.utc)
    hibrido.entries[0]["last_run"] = ahora - timedelta(minutes=16)     # ORS (15 min): vencida
    hibrido.entries[1]["last_run"] = ahora - timedelta(minutes=26)     # TomTom (27 min): aún no
    _parar_tras(hibrido, monkeypatch, esperas=1)
    hibrido.run(tick_seconds=1)
    assert hibrido.ors.collect_cycle.call_count == 1 and hibrido.tom.collect_cycle.call_count == 0
    assert (datetime.now(timezone.utc) - hibrido.entries[0]["last_run"]).total_seconds() < 5   # reloj reiniciado
    assert hibrido.entries[1]["last_run"] == ahora - timedelta(minutes=26)                      # el otro intacto


def test_si_se_detiene_durante_un_ciclo_no_dispara_la_otra_fuente(hibrido, monkeypatch):
    hibrido.ors.collect_cycle.side_effect = lambda: setattr(hibrido, "running", False)
    monkeypatch.setattr(collector.time, "sleep", lambda s: pytest.fail("no debería esperar"))
    hibrido.run(tick_seconds=1)
    assert hibrido.ors.collect_cycle.call_count == 1 and hibrido.tom.collect_cycle.call_count == 0


def test_un_error_en_un_ciclo_se_propaga_porque_collect_cycle_ya_captura_los_suyos(hibrido, monkeypatch):
    """Documenta el contrato: el hibrido NO captura excepciones de collect_cycle (DataCollector ya las
    maneja por dentro); si una se escapara, el bucle terminaría."""
    hibrido.ors.collect_cycle.side_effect = RuntimeError("inesperado")
    monkeypatch.setattr(collector.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="inesperado"):
        hibrido.run(tick_seconds=1)
