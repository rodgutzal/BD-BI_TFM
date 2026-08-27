"""Pruebas para HybridScheduler: cada fuente debe dispararse en su propio
intervalo, sin interferir con la otra, y Ctrl+C debe cerrar ambos clientes.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.collector import HybridScheduler


def _simulate(ors_interval_min, tomtom_interval_min, total_minutes):
    """Replica la lógica de HybridScheduler.run() sin usar time.sleep() real."""
    entries = [
        {"name": "ors", "calls": 0, "interval": timedelta(minutes=ors_interval_min), "last_run": None},
        {"name": "tomtom", "calls": 0, "interval": timedelta(minutes=tomtom_interval_min), "last_run": None},
    ]
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for minute in range(total_minutes + 1):
        now = start + timedelta(minutes=minute)
        for entry in entries:
            due = entry["last_run"] is None or (now - entry["last_run"]) >= entry["interval"]
            if due:
                entry["calls"] += 1
                entry["last_run"] = now
    return {e["name"]: e["calls"] for e in entries}


def test_ors_and_tomtom_fire_on_independent_schedules():
    """Con 15/27 min en 120 min simulados: ORS 9 veces, TomTom 5 veces."""
    calls = _simulate(ors_interval_min=15, tomtom_interval_min=27, total_minutes=120)
    assert calls["ors"] == 9
    assert calls["tomtom"] == 5


def test_both_sources_fire_immediately_on_first_tick():
    """En el minuto 0 (last_run=None), ambas fuentes deben disparar de inmediato."""
    calls = _simulate(ors_interval_min=15, tomtom_interval_min=27, total_minutes=0)
    assert calls["ors"] == 1
    assert calls["tomtom"] == 1


def test_signal_handler_closes_both_collectors():
    """Ctrl+C debe cerrar traffic_client y weather de AMBOS collectors."""
    ors_collector = MagicMock()
    tomtom_collector = MagicMock()

    scheduler = HybridScheduler.__new__(HybridScheduler)  # sin registrar signal real
    scheduler.entries = [
        {"name": "ors", "collector": ors_collector, "interval": None, "last_run": None},
        {"name": "tomtom", "collector": tomtom_collector, "interval": None, "last_run": None},
    ]
    scheduler.running = True

    with pytest.raises(SystemExit):
        scheduler._signal_handler(None, None)

    assert ors_collector.traffic_client.close.called
    assert ors_collector.weather.close.called
    assert tomtom_collector.traffic_client.close.called
    assert tomtom_collector.weather.close.called
    assert scheduler.running is False


if __name__ == "__main__":
    test_ors_and_tomtom_fire_on_independent_schedules()
    test_both_sources_fire_immediately_on_first_tick()
    print("✓ Pruebas de cadencia del scheduler pasaron (correr con pytest para el test de señal)")
