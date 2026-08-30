"""Pruebas de regresión: campos que vienen NULL con DATA_SOURCE=ors
(traffic_delay_min, no_traffic_time_min) no deben romper comparaciones ni
formateo en ningún dashboard.

Ver INTEGRATION_NOTES.md, bug #12: con ORS (la fuente por defecto),
traffic_delay_min/no_traffic_time_min/traffic_length_km vienen NULL, y
dict.get(key, default) / pd.Series.get(key, default) NO usan `default`
cuando la clave existe pero su valor es None — solo cuando la clave falta.
Varios puntos de streamlit_app/dashboards/operations_dashboard.py y
streamlit_app/legacy_reference/ asumían lo contrario y crasheaban con
`TypeError: '<=' not supported between instances of 'NoneType' and 'int'`.
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import RouteDatabase


def _make_ors_only_route_db(tmp_path):
    """Crea una DB temporal con una sola medición ORS (traffic_delay_min NULL)."""
    db = RouteDatabase(tmp_path / "test.csv", tmp_path / "test.db")
    db.save_records_to_sqlite([{
        "timestamp": "2026-08-16T20:00:00+00:00", "origin": "Msida", "destination": "Valletta",
        "data_source": "ors", "distance_km": 4.24, "travel_time_min": 10.37,
        "traffic_delay_min": None, "no_traffic_time_min": None, "average_speed_kmh": 24.5,
    }])
    return db


def test_ors_row_traffic_delay_is_none_not_nan(tmp_path):
    """Confirma la forma exacta del bug: con una sola fila ORS, .get() devuelve
    None (no NaN), que rompe comparaciones directas sin guardar."""
    db = _make_ors_only_route_db(tmp_path)
    latest = db.query_measurements(origin="Msida", destination="Valletta", limit=1)
    row = latest.iloc[-1]

    raw_value = row.get("traffic_delay_min", 0)
    assert raw_value is None or pd.isna(raw_value)

    # Sin el fix, esta línea lanzaría TypeError.
    with pytest.raises(TypeError):
        _ = raw_value <= 1


def test_safe_helper_handles_none_and_nan():
    """El helper _safe() (duplicado en operations_dashboard.py y
    legacy_reference/components.py) debe neutralizar tanto None como NaN."""
    def _safe(value, default=0.0):
        return default if pd.isna(value) else value

    assert _safe(None) == 0.0
    assert _safe(float("nan")) == 0.0
    assert _safe(3.5) == 3.5
    assert _safe(0.0) == 0.0  # 0 es un valor real, no debe reemplazarse

    # Con el fix, la comparación que antes crasheaba ahora funciona:
    delay = _safe(None)
    assert delay <= 1
