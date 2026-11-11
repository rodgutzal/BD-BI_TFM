"""Pruebas de la API REST (src/api.py).

Regresión: cada endpoint envolvía todo en `except Exception -> HTTPException(400)`,
y ese `except` capturaba también el `HTTPException(404)` que el propio endpoint
lanzaba: una ruta sin datos respondía 400 con detail="404: No data available"
en vez de un 404 real.

`src.api` construye la base y GoldLayer AL IMPORTARSE (GoldLayer crea tablas), así
que se importa aquí con MOBILITY_DB_PATH apuntando a un directorio temporal: ningún
test toca data/mobility.db.
"""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.database import RouteDatabase


def _registros(n=80):
    ahora = datetime.now(timezone.utc)
    return [
        {"timestamp": (ahora - timedelta(hours=i)).isoformat(), "origin": "Msida", "destination": "Gzira",
         "data_source": "tomtom", "travel_time_min": 8.0 + (i % 7), "traffic_delay_min": 1.0,
         "average_speed_kmh": 30.0, "distance_km": 3.0, "origin_temperature": 20.0 + i % 5,
         "origin_humidity": 50.0 + i % 9}
        for i in range(n)
    ]


@pytest.fixture
def api(tmp_path, monkeypatch):
    """Módulo src.api recién importado contra una base temporal con una ruta (Msida→Gzira)."""
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("MOBILITY_DB_PATH", str(db_path))
    monkeypatch.setenv("MOBILITY_CSV_PATH", str(tmp_path / "t.csv"))
    RouteDatabase(tmp_path / "t.csv", db_path).save_records_to_sqlite(_registros())

    sys.modules.pop("src.api", None)          # forzar un import nuevo con las variables de entorno
    modulo = importlib.import_module("src.api")
    yield modulo
    sys.modules.pop("src.api", None)


@pytest.fixture
def client(api):
    return TestClient(api.app, raise_server_exceptions=False)


def test_la_api_usa_la_base_indicada_por_variable_de_entorno(api, tmp_path):
    """La API usa la base de datos que indica la variable de entorno."""
    assert api.DB_PATH == tmp_path / "t.db"


# ---------------------------------------------------------------------------
# Un recurso inexistente debe ser 404, no 400
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "/api/statistics/Nada/Nunca",
    "/api/predict/Nada/Nunca",
    "/api/anomalies/Nada/Nunca",
    "/api/forecast/Nada/Nunca",
    "/api/time-series/Nada/Nunca",
])
def test_ruta_sin_datos_responde_404_y_no_400(client, url):
    """Una ruta sin datos responde 404 (en cada URL parametrizada) y el `detail` no lleva el 404 anidado."""
    r = client.get(url)
    assert r.status_code == 404, r.text
    assert not r.json()["detail"].startswith("404:"), "el detail no debe llevar el 404 anidado"


def test_el_detail_del_404_es_el_mensaje_original(client):
    """El `detail` del 404 es el mensaje original de cada endpoint."""
    assert client.get("/api/statistics/Nada/Nunca").json()["detail"] == "No data available"
    assert client.get("/api/predict/Nada/Nunca").json()["detail"] == "No data for this route"


# ---------------------------------------------------------------------------
# Validación de parámetros (la gestiona FastAPI: 422)
# ---------------------------------------------------------------------------

def test_analisis_invalido_es_422(client):
    """Un tipo de análisis de serie temporal no válido responde 422."""
    assert client.get("/api/time-series/Msida/Gzira?analysis=invalido").status_code == 422


@pytest.mark.parametrize("url", [
    "/api/predict/Msida/Gzira?days=0",
    "/api/predict/Msida/Gzira?days=999",
    "/api/statistics/Msida/Gzira?hours=0",
])
def test_parametros_fuera_de_rango_son_422(client, url):
    """Los parámetros fuera de rango (en cada URL parametrizada) responden 422."""
    assert client.get(url).status_code == 422


# ---------------------------------------------------------------------------
# Caminos felices
# ---------------------------------------------------------------------------

def test_health(client):
    """`/api/health` responde «healthy» con el número de rutas."""
    j = client.get("/api/health").json()
    assert j["status"] == "healthy" and j["routes"] == 1


def test_routes(client):
    """`/api/routes` lista el total y cada ruta con origen y destino."""
    j = client.get("/api/routes").json()
    assert j == {"total_routes": 1, "routes": [{"origin": "Msida", "destination": "Gzira"}]}


def test_rankings_con_gold_vacio_no_falla(client):
    """`/api/routes/rankings` responde 200 con listas vacías cuando la capa Gold no tiene datos."""
    r = client.get("/api/routes/rankings")
    assert r.status_code == 200
    assert r.json()["best_routes"] == []


def test_statistics(client):
    """`/api/statistics` devuelve la ruta y las estadísticas con el recuento de mediciones."""
    j = client.get("/api/statistics/Msida/Gzira?hours=720").json()
    assert j["route"] == "Msida → Gzira"
    assert j["statistics"]["count"] == 80


def test_anomalies(client):
    """`/api/anomalies` responde 200 con la ruta y la lista de anomalías."""
    r = client.get("/api/anomalies/Msida/Gzira")
    assert r.status_code == 200
    assert r.json()["route"] == "Msida → Gzira" and "anomalies" in r.json()


def test_json_safe_sustituye_nan_e_infinito_por_none(api):
    """JSON no admite NaN/inf: se convierten en None, también dentro de dicts y listas anidados.
    Los escalares de numpy (np.bool_, np.float64) pasan a tipos nativos de Python."""
    entrada = {"a": float("nan"), "b": [1.0, float("inf"), {"c": -float("inf")}], "d": 2, "e": "x"}
    assert api._json_safe(entrada) == {"a": None, "b": [1.0, None, {"c": None}], "d": 2, "e": "x"}
    salida = api._json_safe({"s": np.bool_(True), "f": np.float64("nan"), "g": np.float64(1.5)})
    assert salida == {"s": True, "f": None, "g": 1.5}
    assert type(salida["s"]) is bool and type(salida["g"]) is float


def test_time_series_patrones_con_un_dia_de_una_sola_muestra(tmp_path, monkeypatch):
    """Regresión: un día con 1 muestra tiene desviación típica NaN y el endpoint devolvía 500
    (dependía de la hora a la que se ejecutaba: justo tras la medianoche UTC)."""
    # 80 horas terminando a las 00:30 de ayer (UTC): ese último día queda con exactamente 1 muestra.
    fin =datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0) - timedelta(days=1)
    registros = [{**r, "timestamp": (fin - timedelta(hours=i)).isoformat()} for i, r in enumerate(_registros(80))]
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("MOBILITY_DB_PATH", str(db_path))
    monkeypatch.setenv("MOBILITY_CSV_PATH", str(tmp_path / "t.csv"))
    RouteDatabase(tmp_path / "t.csv", db_path).save_records_to_sqlite(registros)
    sys.modules.pop("src.api", None)
    try:
        modulo = importlib.import_module("src.api")
        r = TestClient(modulo.app, raise_server_exceptions=False).get("/api/time-series/Msida/Gzira?analysis=patterns")
    finally:
        sys.modules.pop("src.api", None)
    assert r.status_code == 200
    por_dia = r.json()["result"]["by_day"]
    assert any(v["std"] is None and v["count"] == 1 for v in por_dia.values())


def test_time_series_patrones(client):
    """`/api/time-series` con `analysis=patterns` responde 200 con ese tipo de análisis."""
    r = client.get("/api/time-series/Msida/Gzira?analysis=patterns")
    assert r.status_code == 200
    assert r.json()["analysis_type"] == "patterns"


def test_predict_devuelve_json_serializable_y_modelos_entrenados(client):
    """De punta a punta: entrena el ensemble con los datos y responde. Cubre también que el
    resultado se serialice (antes `model_predictions` se apuntaba a sí mismo)."""
    r = client.get("/api/predict/Msida/Gzira?days=30")
    assert r.status_code == 200, r.text
    j = r.json()
    assert isinstance(j["prediction"]["value"], float)
    assert j["prediction"]["confidence_interval_95"]["lower"] <= j["prediction"]["value"] \
        <= j["prediction"]["confidence_interval_95"]["upper"]
    assert "random_forest" in j["models_used"]      # solo los modelos realmente entrenados
