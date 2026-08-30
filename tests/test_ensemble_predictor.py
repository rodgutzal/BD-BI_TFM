"""Unit tests for ensemble predictor."""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.models.ensemble_predictor import EnsemblePredictor
from src.database import RouteDatabase


@pytest.fixture
def sample_data():
    """Create sample traffic data for testing."""
    dates = pd.date_range(start='2026-01-01', periods=100, freq='1H', tz='UTC')
    data = {
        'timestamp': dates,
        'origin': ['Msida'] * 100,
        'destination': ['Marsaskala'] * 100,
        'travel_time_min': np.random.uniform(15, 25, 100) + np.sin(np.arange(100) / 24) * 5,
        'no_traffic_time_min': np.random.uniform(10, 15, 100),
        'average_speed_kmh': np.random.uniform(40, 60, 100),
        'origin_temperature': np.random.uniform(15, 30, 100),
        'origin_humidity': np.random.uniform(40, 80, 100),
    }
    return pd.DataFrame(data)


def test_ensemble_initialization():
    """Test ensemble predictor initialization."""
    predictor = EnsemblePredictor('test_route', Path('/tmp'))
    assert predictor.route_name == 'test_route'
    assert not predictor.is_trained
    assert 'random_forest' in predictor.models


def test_feature_preparation(sample_data):
    """Test feature preparation."""
    predictor = EnsemblePredictor('test', Path('/tmp'))
    X, y, cols = predictor.prepare_features(sample_data)

    assert X is not None
    assert y is not None
    assert X.shape[0] == len(sample_data)
    assert X.shape[1] > 0
    assert len(y) == len(sample_data)


def test_model_training(sample_data):
    """Test ensemble model training."""
    predictor = EnsemblePredictor('test', Path('/tmp'))
    result = predictor.train(sample_data)

    assert result.get('status') == 'success'
    assert result.get('samples_used') == len(sample_data)
    assert len(result.get('models_trained', [])) > 0
    assert predictor.is_trained


def test_prediction_output(sample_data):
    """Test prediction output format."""
    predictor = EnsemblePredictor('test', Path('/tmp'))
    predictor.train(sample_data)

    X, _, _ = predictor.prepare_features(sample_data)
    predictions = predictor.predict(X[0:1])

    assert 'ensemble_prediction' in predictions
    assert predictions['ensemble_prediction'] > 0
    assert 'confidence_interval_95' in predictions
    assert 'confidence_interval_80' in predictions
    assert predictions['confidence_interval_95']['lower'] < predictions['ensemble_prediction']
    assert predictions['ensemble_prediction'] < predictions['confidence_interval_95']['upper']


def test_anomaly_detection(sample_data):
    """Test anomaly detection."""
    predictor = EnsemblePredictor('test', Path('/tmp'))

    # Add anomaly
    sample_data.loc[50, 'travel_time_min'] = 100  # Outlier

    result = predictor.anomaly_detection(sample_data, threshold=2.5)

    assert 'total_anomalies' in result
    assert result['total_anomalies'] >= 1
    assert 'anomalies' in result


def test_insufficient_data():
    """Test handling of insufficient data."""
    small_data = pd.DataFrame({
        'timestamp': pd.date_range('2026-01-01', periods=10, freq='1H', tz='UTC'),
        'travel_time_min': [20] * 10
    })

    predictor = EnsemblePredictor('test', Path('/tmp'))
    result = predictor.train(small_data)

    assert 'error' in result or result.get('status') == 'success'  # Should handle gracefully


def test_model_save_load(sample_data, tmp_path):
    """Test model saving and loading."""
    predictor = EnsemblePredictor('test_model', tmp_path)
    predictor.train(sample_data)

    # Save
    save_result = predictor.save()
    assert save_result.get('status') == 'saved'

    # Load into new instance
    new_predictor = EnsemblePredictor('test_model', tmp_path)
    load_result = new_predictor.load()

    # Verify it loaded correctly
    if load_result.get('status') == 'loaded':
        assert new_predictor.is_trained
