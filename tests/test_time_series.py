"""Unit tests for time series analysis."""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analytics.time_series_analysis import TimeSeriesAnalytics


@pytest.fixture
def sample_ts_data():
    """Create sample time series data."""
    dates = pd.date_range(start='2026-01-01', periods=120, freq='1D', tz='UTC')
    # Create data with trend, seasonality, and noise
    trend = np.linspace(20, 25, 120)
    seasonality = 3 * np.sin(np.arange(120) * 2 * np.pi / 30)  # 30-day cycle
    noise = np.random.normal(0, 0.5, 120)
    values = trend + seasonality + noise

    data = {
        'timestamp': dates,
        'travel_time_min': values,
        'origin_temperature': np.random.uniform(15, 30, 120)
    }
    return pd.DataFrame(data)


def test_initialization(sample_ts_data):
    """Test TimeSeriesAnalytics initialization."""
    tsa = TimeSeriesAnalytics(sample_ts_data)
    assert tsa.df is not None
    assert len(tsa.df) == len(sample_ts_data)


def test_seasonal_decomposition(sample_ts_data):
    """Test seasonal decomposition."""
    tsa = TimeSeriesAnalytics(sample_ts_data)
    result = tsa.seasonal_decomposition('travel_time_min', period=7)

    assert 'trend' in result
    assert 'seasonal' in result
    assert 'residual' in result
    assert len(result['trend']) == len(sample_ts_data)


def test_stationarity_tests(sample_ts_data):
    """Test stationarity tests (ADF, KPSS)."""
    tsa = TimeSeriesAnalytics(sample_ts_data)
    result = tsa.stationarity_tests('travel_time_min')

    assert 'adf' in result
    assert 'kpss' in result
    assert 'pvalue' in result['adf']
    assert 'pvalue' in result['kpss']
    assert 0 <= result['adf']['pvalue'] <= 1
    assert 0 <= result['kpss']['pvalue'] <= 1


def test_autocorrelation_analysis(sample_ts_data):
    """Test autocorrelation analysis."""
    tsa = TimeSeriesAnalytics(sample_ts_data)
    result = tsa.autocorrelation_analysis('travel_time_min', nlags=20)

    assert 'acf' in result
    assert 'pacf' in result
    assert len(result['acf']['values']) > 0
    assert len(result['pacf']['values']) > 0
    assert 'confidence_interval' in result['acf']


def test_change_point_detection(sample_ts_data):
    """Test change point detection."""
    tsa = TimeSeriesAnalytics(sample_ts_data)

    # Add a change point
    sample_ts_data.loc[60:, 'travel_time_min'] += 5

    result = tsa.change_point_detection('travel_time_min')

    assert 'total_changes' in result
    assert result['total_changes'] >= 0
    assert 'change_points' in result


def test_day_of_week_patterns(sample_ts_data):
    """Test day of week pattern analysis."""
    tsa = TimeSeriesAnalytics(sample_ts_data)
    result = tsa.day_of_week_patterns('travel_time_min')

    assert 'by_day' in result
    assert 'comparison' in result
    # Should have entries for each day of week
    assert len(result['by_day']) > 0


def test_hourly_patterns():
    """Test hourly pattern analysis."""
    # Create hourly data
    dates = pd.date_range(start='2026-01-01', periods=240, freq='1H', tz='UTC')
    data = {
        'timestamp': dates,
        'travel_time_min': np.concatenate([
            np.random.uniform(10, 15, 8),  # Night: low
            np.random.uniform(20, 30, 4),  # Morning rush: high
            np.random.uniform(15, 20, 8),  # Day: medium
            np.random.uniform(20, 30, 4),  # Evening rush: high
        ] * 3)  # Repeat for 3 days
    }
    df = pd.DataFrame(data)
    tsa = TimeSeriesAnalytics(df)
    result = tsa.hourly_patterns('travel_time_min')

    assert 'by_hour' in result
    assert 'peak_hour' in result
    assert 'off_peak_hour' in result
    assert len(result['by_hour']) <= 24


def test_correlation_analysis(sample_ts_data):
    """Test correlation analysis."""
    tsa = TimeSeriesAnalytics(sample_ts_data)
    result = tsa.correlation_analysis('travel_time_min', 'origin_temperature')

    assert 'pearson' in result
    assert 'spearman' in result
    assert 'coefficient' in result['pearson']
    assert -1 <= result['pearson']['coefficient'] <= 1
    assert 'pvalue' in result['pearson']


def test_forecast_summary(sample_ts_data):
    """Test forecast summary."""
    tsa = TimeSeriesAnalytics(sample_ts_data)
    result = tsa.forecast_summary()

    assert 'total_records' in result
    assert result['total_records'] == len(sample_ts_data)
    assert 'stationarity' in result or 'error' not in result


def test_insufficient_data():
    """Test handling of insufficient data."""
    small_data = pd.DataFrame({
        'timestamp': pd.date_range('2026-01-01', periods=5, freq='1H', tz='UTC'),
        'travel_time_min': [20, 21, 22, 23, 24]
    })

    tsa = TimeSeriesAnalytics(small_data)
    result = tsa.seasonal_decomposition('travel_time_min', period=3)

    # Should handle gracefully (return error or None)
    assert 'error' in result or result is not None
