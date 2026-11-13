"""Unit tests for ensemble predictor."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.models.ensemble_predictor import EnsemblePredictor


@pytest.fixture
def sample_data():
    """Create sample traffic data for testing."""
    dates = pd.date_range(start="2026-01-01", periods=100, freq="1h", tz="UTC")
    data = {
        "timestamp": dates,
        "origin": ["Msida"] * 100,
        "destination": ["Marsaskala"] * 100,
        "travel_time_min": np.random.uniform(15, 25, 100) + np.sin(np.arange(100) / 24) * 5,
        "no_traffic_time_min": np.random.uniform(10, 15, 100),
        "average_speed_kmh": np.random.uniform(40, 60, 100),
        "origin_temperature": np.random.uniform(15, 30, 100),
        "origin_humidity": np.random.uniform(40, 80, 100),
    }
    return pd.DataFrame(data)


def test_ensemble_initialization(tmp_path):
    """Test ensemble predictor initialization."""
    predictor = EnsemblePredictor("test_route", tmp_path)
    assert predictor.route_name == "test_route"
    assert not predictor.is_trained
    assert "random_forest" in predictor.models


def test_feature_preparation(sample_data, tmp_path):
    """Test feature preparation."""
    predictor = EnsemblePredictor("test", tmp_path)
    X, y, cols = predictor.prepare_features(sample_data)

    assert X is not None
    assert y is not None
    assert X.shape[0] == len(sample_data)
    assert X.shape[1] > 0
    assert len(y) == len(sample_data)


def test_model_training(sample_data, tmp_path):
    """Test ensemble model training."""
    predictor = EnsemblePredictor("test", tmp_path)
    result = predictor.train(sample_data)

    assert result.get("status") == "success"
    assert result.get("samples_used") == len(sample_data)
    assert len(result.get("models_trained", [])) > 0
    assert predictor.is_trained


def test_prediction_output(sample_data, tmp_path):
    """Test prediction output format."""
    predictor = EnsemblePredictor("test", tmp_path)
    predictor.train(sample_data)

    X, _, _ = predictor.prepare_features(sample_data)
    predictions = predictor.predict(X[0:1])

    assert "ensemble_prediction" in predictions
    assert predictions["ensemble_prediction"] > 0
    assert "confidence_interval_95" in predictions
    assert "confidence_interval_80" in predictions
    assert predictions["confidence_interval_95"]["lower"] < predictions["ensemble_prediction"]
    assert predictions["ensemble_prediction"] < predictions["confidence_interval_95"]["upper"]


def test_anomaly_detection(sample_data, tmp_path):
    """Test anomaly detection."""
    predictor = EnsemblePredictor("test", tmp_path)

    # Add anomaly
    sample_data.loc[50, "travel_time_min"] = 100  # Outlier

    result = predictor.anomaly_detection(sample_data, threshold=2.5)

    assert "total_anomalies" in result
    assert result["total_anomalies"] >= 1
    assert "anomalies" in result


def test_insufficient_data(tmp_path):
    """Test handling of insufficient data."""
    small_data = pd.DataFrame(
        {"timestamp": pd.date_range("2026-01-01", periods=10, freq="1h", tz="UTC"), "travel_time_min": [20] * 10}
    )

    predictor = EnsemblePredictor("test", tmp_path)
    result = predictor.train(small_data)

    assert "error" in result or result.get("status") == "success"  # Should handle gracefully


def _serie(n=400, seed=0, fuente="tomtom"):
    """Serie de ruido puro alrededor de 12 min, sin relación con las variables: nada la predice."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-09-01", periods=n, freq="30min", tz="UTC"),
            "data_source": fuente,
            "travel_time_min": 12 + rng.normal(0, 3, n),
            "no_traffic_time_min": rng.uniform(10, 15, n),
            "origin_temperature": rng.uniform(15, 30, n),
            "origin_humidity": rng.uniform(40, 80, n),
        }
    )


def test_train_informa_la_r2_fuera_de_muestra_ademas_de_la_de_entrenamiento(tmp_path):
    """Cada modelo trae `r2_entrenamiento` (en muestra) y `r2` y `mae` fuera de muestra; el resumen va en `holdout`."""
    result = EnsemblePredictor("t", tmp_path).train(_serie())
    modelos = [m for m in result["models_trained"] if "r2" in m]
    assert modelos and all({"r2_entrenamiento", "r2", "mae"} <= set(m) for m in modelos)
    h = result["holdout"]
    assert h["n_entrenamiento"] == 320 and h["n_prueba"] == 80  # 400 filas: 80 % / 20 %
    assert {"ensemble", "modelos", "referencias", "supera_a_ultimo_valor"} <= set(h)


def test_con_ruido_puro_la_r2_en_muestra_engana_y_la_de_fuera_de_muestra_no(tmp_path):
    """Los bosques profundos se aprenden de memoria los datos de entrenamiento: con ruido puro la R² en muestra sale
    alta (lo que se informaba antes) y fuera de muestra no pasa de ~0. Es la razón de medir fuera de muestra."""
    modelos = [m for m in EnsemblePredictor("t", tmp_path).train(_serie())["models_trained"] if "r2" in m]
    rf = next(m for m in modelos if m["model"] == "random_forest")
    assert rf["r2_entrenamiento"] > 0.5
    assert rf["r2"] < 0.1


def test_el_corte_es_cronologico_aunque_las_filas_lleguen_de_la_mas_reciente_a_la_mas_antigua(tmp_path):
    """La base entrega las filas de la más reciente a la más antigua: el corte debe ordenarlas antes, y el tramo de
    prueba es el 20 % más reciente por fecha."""
    datos = _serie()
    esperado = EnsemblePredictor("a", tmp_path).train(datos)["holdout"]
    al_reves = EnsemblePredictor("b", tmp_path).train(datos.iloc[::-1])["holdout"]
    assert pd.Timestamp(al_reves["corte"]) == datos["timestamp"].iloc[320]
    assert al_reves["corte"] == esperado["corte"] and al_reves["n_prueba"] == esperado["n_prueba"]
    assert al_reves["referencias"]["ultimo_valor"]["mae"] == pytest.approx(
        esperado["referencias"]["ultimo_valor"]["mae"]
    )


def test_la_referencia_de_ultimo_valor_se_calcula_con_la_medicion_anterior_de_la_misma_fuente(tmp_path):
    """Con dos fuentes alternando, el «último valor» de cada fila es el de la misma fuente, no el de la fila contigua."""
    datos = _serie(n=400)
    datos["data_source"] = ["ors", "tomtom"] * 200
    datos["travel_time_min"] = np.where(datos["data_source"] == "ors", 10.0, 30.0) + np.arange(400) * 0.0
    h = EnsemblePredictor("t", tmp_path).train(datos)["holdout"]
    assert h["referencias"]["ultimo_valor"]["mae"] == pytest.approx(0.0)  # cada fuente es constante
    assert h["referencias"]["media_entrenamiento"]["mae"] > 5  # la media mezcla las dos fuentes


def test_el_tramo_de_prueba_es_el_mas_reciente_y_la_media_de_referencia_sale_del_entrenamiento(tmp_path):
    """Con un cambio de nivel al final (10 min las primeras 320 filas, 30 las últimas 80), el tramo de prueba tiene que
    ser el final: la media del entrenamiento (10) se equivoca en ~20 min sobre él. Si se midiera con el tramo antiguo, o
    la media se calculara con el de prueba, ese error sería muy distinto."""
    datos = _serie()
    datos["travel_time_min"] = np.where(np.arange(400) < 320, 10.0, 30.0)
    h = EnsemblePredictor("t", tmp_path).train(datos)["holdout"]
    assert h["referencias"]["media_entrenamiento"]["mae"] == pytest.approx(20.0)
    assert h["referencias"]["ultimo_valor"]["mae"] == pytest.approx(
        0.25
    )  # solo falla la 1.ª fila de prueba: 20 min / 80 filas
    assert h["supera_a_ultimo_valor"] is False  # el ensemble nunca vio el nivel de 30: no puede ganar


def test_supera_a_ultimo_valor_es_verdadero_cuando_las_variables_si_predicen(tmp_path):
    """Si el tiempo de viaje depende de la hora (par o impar) y la fila anterior siempre es de la otra paridad, repetir la
    última medición se equivoca en 10 min y el ensemble, que ve la hora, casi no: tiene que ganar."""
    datos = _serie()
    datos["timestamp"] = pd.date_range("2026-09-01", periods=400, freq="1h", tz="UTC")
    datos["travel_time_min"] = 10.0 + 10.0 * (datos["timestamp"].dt.hour % 2)
    h = EnsemblePredictor("t", tmp_path).train(datos)["holdout"]
    assert h["referencias"]["ultimo_valor"]["mae"] == pytest.approx(10.0)
    assert h["ensemble"]["mae"] < 0.5 * h["referencias"]["ultimo_valor"]["mae"] and h["supera_a_ultimo_valor"] is True


def test_el_ensemble_pondera_los_modelos_y_normaliza_los_pesos_sobre_los_que_hay(tmp_path):
    """La predicción del ensemble es el promedio ponderado de los modelos disponibles, con los pesos normalizados: sin
    xgboost instalado, los pesos de los otros dos se reescalan para sumar 1."""
    p = EnsemblePredictor("t", tmp_path)
    p.ensemble_weights = {"xgboost": 0.4, "random_forest": 0.9, "gradient_boosting": 0.1}
    pred = p._weighted({"random_forest": np.array([10.0, 10.0]), "gradient_boosting": np.array([20.0, 30.0])})
    assert pred == pytest.approx([11.0, 12.0])  # 0,9·10 + 0,1·20 y 0,9·10 + 0,1·30 (los pesos suman 1 tras normalizar)


def test_con_pocas_filas_no_se_mide_fuera_de_muestra_y_solo_queda_la_r2_en_muestra(tmp_path):
    """Con menos de 100 filas no hay tramo de prueba fiable: se entrena igualmente, pero sin `r2`, y se dice por qué."""
    result = EnsemblePredictor("t", tmp_path).train(_serie(n=70))
    assert result["status"] == "success" and "error" in result["holdout"]
    assert all("r2" not in m for m in result["models_trained"])
    assert any("r2_entrenamiento" in m for m in result["models_trained"])


def test_sin_timestamp_no_hay_corte_cronologico(tmp_path):
    """Sin columna de fecha no se puede ordenar el tiempo: no se inventa un corte."""
    result = EnsemblePredictor("t", tmp_path).train(_serie().drop(columns="timestamp"))
    assert result["status"] == "success" and "timestamp" in result["holdout"]["error"]
    assert all("r2" not in m for m in result["models_trained"])


def test_el_modelo_definitivo_se_reajusta_con_todos_los_datos(tmp_path):
    """Tras medir con el 80 %, el modelo que se guarda y se usa para predecir se ajusta con las 400 filas."""
    predictor = EnsemblePredictor("t", tmp_path)
    result = predictor.train(_serie())
    assert result["samples_used"] == 400 and predictor.is_trained
    assert predictor.models["random_forest"].n_features_in_ == 6
    X, _, _ = predictor.prepare_features(_serie())
    assert "ensemble_prediction" in predictor.predict(X[:1])


def test_model_save_load(sample_data, tmp_path):
    """Test model saving and loading."""
    predictor = EnsemblePredictor("test_model", tmp_path)
    predictor.train(sample_data)

    # Save
    save_result = predictor.save()
    assert save_result.get("status") == "saved"

    # Load into new instance
    new_predictor = EnsemblePredictor("test_model", tmp_path)
    load_result = new_predictor.load()

    # Verify it loaded correctly
    if load_result.get("status") == "loaded":
        assert new_predictor.is_trained
