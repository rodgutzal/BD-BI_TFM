"""Pruebas de la lógica pura de demografía (reconciliado a un año común).

No usan la API de Data Commons ni requieren `datacommons-client`.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import RouteDatabase
from src.demographics_client import DemographicsClient, _clean
from src.demographics_extraction import (
    latest_observation_per_zone,
    reconcile_to_common_year,
    summarize_history,
)


def _obs(year, population, source="censo"):
    return {"date": str(year), "year": year, "population": population, "source": source}


NACIONAL = [
    {"year": 2014, "population": 400_000},
    {"year": 2019, "population": 500_000},
    {"year": 2021, "population": 520_000},
    {"year": 2024, "population": 560_000},
]


def test_latest_observation_usa_el_anio_mas_alto_de_la_serie_completa():
    """Regresión: date='latest' de la API devolvió 2014 para Valletta cuando su
    propia serie ya tenía 2021."""
    out = latest_observation_per_zone({"Valletta": [_obs(2014, 100), _obs(2021, 150), _obs(2019, 120)]})
    assert out["Valletta"]["year"] == 2021


def test_latest_observation_ignora_zonas_sin_observaciones():
    assert latest_observation_per_zone({"A": [], "B": [_obs(2020, 1)]}).keys() == {"B"}


def test_latest_observation_prefiere_la_fecha_mas_reciente_en_el_mismo_anio():
    a = {"date": "2020-01-01", "year": 2020, "population": 1, "source": "x"}
    b = {"date": "2020-12-31", "year": 2020, "population": 2, "source": "y"}
    assert latest_observation_per_zone({"Z": [a, b]})["Z"]["population"] == 2


def test_summarize_history_encuentra_anios_comunes():
    hist = {"A": [_obs(2014, 1), _obs(2021, 1)], "B": [_obs(2014, 1)]}
    s = summarize_history(hist, ["A", "B"])
    assert s["common_years"] == [2014]


def test_summarize_history_sin_anio_comun_o_con_zona_sin_datos():
    hist = {"A": [_obs(2014, 1)], "B": [_obs(2021, 1)]}
    assert summarize_history(hist, ["A", "B"])["common_years"] == []
    # una zona sin ninguna observación deja la intersección vacía, a la vista
    assert summarize_history({"A": [_obs(2014, 1)]}, ["A", "C"])["common_years"] == []


def test_reconcile_proyecta_con_la_tasa_nacional():
    zonas = {"Msida": _obs(2014, 10_000)}
    recs, anio = reconcile_to_common_year(zonas, NACIONAL)
    assert anio == 2024
    r = recs[0]
    assert r["method"] == "national_growth_adjustment"
    assert r["population"] == round(10_000 * 560_000 / 400_000)  # 14.000
    # queda trazable qué parte es dato real y cuál es proyección
    assert r["basis_year"] == 2014 and r["basis_population"] == 10_000
    assert r["observation_date"] == "2024"


def test_reconcile_no_toca_un_dato_igual_o_mas_nuevo_que_el_objetivo():
    recs, _ = reconcile_to_common_year({"Marsaskala": _obs(2024, 17_000)}, NACIONAL)
    assert recs[0]["method"] == "observed"
    assert recs[0]["population"] == 17_000


def test_reconcile_respeta_un_anio_objetivo_explicito():
    recs, anio = reconcile_to_common_year({"Msida": _obs(2014, 10_000)}, NACIONAL, target_year=2019)
    assert anio == 2019
    assert recs[0]["population"] == round(10_000 * 500_000 / 400_000)


def test_reconcile_omite_zonas_sin_tasa_nacional_para_su_anio():
    recs, _ = reconcile_to_common_year({"X": _obs(2016, 5_000)}, NACIONAL)  # 2016 no está en la serie nacional
    assert recs == []


def test_reconcile_sin_serie_nacional():
    assert reconcile_to_common_year({"X": _obs(2014, 1)}, []) == ([], None)


def test_reconcile_se_guarda_y_se_recupera_de_la_base(tmp_path):
    db = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    recs, _ = reconcile_to_common_year({"Msida": _obs(2014, 10_000)}, NACIONAL)
    db.save_demographics(recs)
    fila = db.get_demographics().set_index("zone_name").loc["Msida"]
    assert fila["population"] == 14_000
    assert fila["method"] == "national_growth_adjustment"
    assert fila["basis_year"] == 2014


def test_guardar_solo_el_dcid_no_borra_la_poblacion_ya_guardada(tmp_path):
    """El upsert usa COALESCE: resolver un dcid no debe pisar datos existentes."""
    db = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    db.save_demographics([{"zone_name": "Msida", "population": 11_740}])
    db.save_demographics([{"zone_name": "Msida", "dcid": "wikidataId/Q1"}])
    fila = db.get_demographics().set_index("zone_name").loc["Msida"]
    assert fila["population"] == 11_740 and fila["dcid"] == "wikidataId/Q1"


def test_historial_de_poblacion_es_upsert(tmp_path):
    db = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    fila = {"zone_name": "Msida", "observation_date": "2014", "year": 2014, "population": 10_000, "source": "x"}
    db.save_population_history([fila])
    db.save_population_history([{**fila, "population": 10_500}])
    h = db.get_population_history()
    assert len(h) == 1 and h.iloc[0]["population"] == 10_500


def test_clean_normaliza_nulos():
    assert _clean(None) == ""
    assert _clean(float("nan")) == ""
    assert _clean("  hola ") == "hola"
    assert _clean(2021) == "2021"


def test_el_cliente_exige_api_key():
    with pytest.raises(ValueError):
        DemographicsClient(api_key="")
    with pytest.raises(ValueError):
        DemographicsClient(api_key='  ""  ')
