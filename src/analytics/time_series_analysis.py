"""Advanced time series analysis for traffic patterns."""

import numpy as np
import pandas as pd
from scipy import signal, stats
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.stattools import adfuller, kpss, acf, pacf
import warnings

warnings.filterwarnings('ignore')


class TimeSeriesAnalytics:
    """Análisis avanzado de series temporales."""

    def __init__(self, df: pd.DataFrame):
        """Inicializar con datos de viajes."""
        self.df = df.copy()
        if 'timestamp' in self.df.columns:
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp'], utc=True)
            self.df = self.df.sort_values('timestamp')

    def seasonal_decomposition(self, column: str = 'travel_time_min', period: int = 12) -> dict:
        """Descomponer en trend, seasonality, residuals."""
        if column not in self.df.columns or len(self.df) < 2 * period:
            return {'error': 'Insufficient data or missing column'}

        try:
            series = self.df[column].dropna()
            if len(series) < 2 * period:
                return {'error': 'Insufficient data'}

            decomposition = seasonal_decompose(series, model='additive', period=period, extrapolate='fill_ea')

            return {
                'trend': decomposition.trend.tolist(),
                'seasonal': decomposition.seasonal.tolist(),
                'residual': decomposition.resid.tolist(),
                'observed': decomposition.observed.tolist(),
                'timestamps': self.df['timestamp'].tolist()[:len(series)],
            }
        except Exception as e:
            return {'error': str(e)}

    def stationarity_tests(self, column: str = 'travel_time_min') -> dict:
        """ADF test y KPSS test para estacionariedad."""
        if column not in self.df.columns:
            return {'error': 'Column not found'}

        series = self.df[column].dropna()
        if len(series) < 3:
            return {'error': 'Insufficient data'}

        results = {}

        # ADF test
        try:
            adf_result = adfuller(series, autolag='AIC')
            results['adf'] = {
                'statistic': float(adf_result[0]),
                'pvalue': float(adf_result[1]),
                'critical_values': {str(k): float(v) for k, v in adf_result[4].items()},
                'is_stationary': adf_result[1] < 0.05,
                'interpretation': 'Estacionaria' if adf_result[1] < 0.05 else 'No estacionaria'
            }
        except Exception as e:
            results['adf'] = {'error': str(e)}

        # KPSS test
        try:
            kpss_result = kpss(series, regression='c', nlags='auto')
            results['kpss'] = {
                'statistic': float(kpss_result[0]),
                'pvalue': float(kpss_result[1]),
                'critical_values': {str(k): float(v) for k, v in kpss_result[3].items()},
                'is_stationary': kpss_result[1] > 0.05,
                'interpretation': 'Estacionaria' if kpss_result[1] > 0.05 else 'No estacionaria'
            }
        except Exception as e:
            results['kpss'] = {'error': str(e)}

        return results

    def autocorrelation_analysis(self, column: str = 'travel_time_min', nlags: int = 20) -> dict:
        """ACF y PACF para identificar patrones."""
        if column not in self.df.columns:
            return {'error': 'Column not found'}

        series = self.df[column].dropna()
        if len(series) < nlags + 1:
            return {'error': 'Insufficient data'}

        try:
            acf_values = acf(series, nlags=nlags, fft=False)
            pacf_values = pacf(series, nlags=nlags, method='ywm')

            # Confidence intervals (95%)
            confidence_interval = 1.96 / np.sqrt(len(series))

            return {
                'acf': {
                    'values': acf_values.tolist(),
                    'confidence_interval': float(confidence_interval),
                    'lags': list(range(len(acf_values)))
                },
                'pacf': {
                    'values': pacf_values.tolist(),
                    'confidence_interval': float(confidence_interval),
                    'lags': list(range(len(pacf_values)))
                },
                'significant_lags': {
                    'acf': [i for i, val in enumerate(acf_values) if abs(val) > confidence_interval],
                    'pacf': [i for i, val in enumerate(pacf_values) if abs(val) > confidence_interval],
                }
            }
        except Exception as e:
            return {'error': str(e)}

    def change_point_detection(self, column: str = 'travel_time_min', threshold: float = 2.0) -> dict:
        """PELT algorithm para detectar cambios significativos."""
        if column not in self.df.columns:
            return {'error': 'Column not found'}

        series = self.df[column].dropna().values
        if len(series) < 10:
            return {'error': 'Insufficient data'}

        try:
            # Detección de cambios usando derivada suavizada
            if len(series) < 4:
                return {'error': 'Not enough data points'}

            # Suavizar con media móvil
            window = min(5, len(series) // 3)
            smoothed = pd.Series(series).rolling(window=window, center=True).mean().fillna(method='bfill').fillna(method='ffill')

            # Calcular derivada (cambio)
            derivatives = np.diff(smoothed)
            std_dev = np.std(derivatives)

            # Detectar cambios significativos
            change_points = []
            for i, deriv in enumerate(derivatives):
                if abs(deriv) > threshold * std_dev:
                    change_points.append({
                        'index': int(i),
                        'timestamp': self.df['timestamp'].iloc[i].isoformat() if i < len(self.df) else None,
                        'value': float(series[i]),
                        'change_magnitude': float(deriv)
                    })

            return {
                'change_points': change_points,
                'threshold': float(threshold * std_dev),
                'std_dev': float(std_dev),
                'total_changes': len(change_points)
            }
        except Exception as e:
            return {'error': str(e)}

    def day_of_week_patterns(self, column: str = 'travel_time_min') -> dict:
        """Patrones por día de semana."""
        if column not in self.df.columns or 'timestamp' not in self.df.columns:
            return {'error': 'Missing required columns'}

        try:
            df = self.df.copy()
            df['day_of_week'] = df['timestamp'].dt.day_name()
            df['hour'] = df['timestamp'].dt.hour

            patterns = {}
            for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
                day_data = df[df['day_of_week'] == day][column]
                if len(day_data) > 0:
                    patterns[day] = {
                        'mean': float(day_data.mean()),
                        'median': float(day_data.median()),
                        'std': float(day_data.std()),
                        'min': float(day_data.min()),
                        'max': float(day_data.max()),
                        'count': int(len(day_data))
                    }

            # Comparar laborales vs fin de semana
            weekday_data = df[df['day_of_week'].isin(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'])][column]
            weekend_data = df[df['day_of_week'].isin(['Saturday', 'Sunday'])][column]

            comparison = {}
            if len(weekday_data) > 0:
                comparison['weekday_mean'] = float(weekday_data.mean())
            if len(weekend_data) > 0:
                comparison['weekend_mean'] = float(weekend_data.mean())

            # T-test
            if len(weekday_data) > 1 and len(weekend_data) > 1:
                t_stat, p_value = stats.ttest_ind(weekday_data, weekend_data)
                comparison['ttest_pvalue'] = float(p_value)
                comparison['significantly_different'] = p_value < 0.05

            return {
                'by_day': patterns,
                'comparison': comparison
            }
        except Exception as e:
            return {'error': str(e)}

    def hourly_patterns(self, column: str = 'travel_time_min') -> dict:
        """Patrones por hora del día."""
        if column not in self.df.columns or 'timestamp' not in self.df.columns:
            return {'error': 'Missing required columns'}

        try:
            df = self.df.copy()
            df['hour'] = df['timestamp'].dt.hour

            patterns = {}
            for hour in range(24):
                hour_data = df[df['hour'] == hour][column]
                if len(hour_data) > 0:
                    patterns[str(hour).zfill(2)] = {
                        'mean': float(hour_data.mean()),
                        'median': float(hour_data.median()),
                        'std': float(hour_data.std()),
                        'count': int(len(hour_data))
                    }

            # Identificar picos
            if patterns:
                means = {h: p['mean'] for h, p in patterns.items()}
                peak_hour = max(means, key=means.get)
                off_peak_hour = min(means, key=means.get)

                return {
                    'by_hour': patterns,
                    'peak_hour': peak_hour,
                    'peak_travel_time': float(means[peak_hour]),
                    'off_peak_hour': off_peak_hour,
                    'off_peak_travel_time': float(means[off_peak_hour])
                }

            return {'error': 'No data'}
        except Exception as e:
            return {'error': str(e)}

    def correlation_analysis(self, col1: str, col2: str) -> dict:
        """Análisis de correlación entre variables."""
        if col1 not in self.df.columns or col2 not in self.df.columns:
            return {'error': 'Columns not found'}

        series1 = self.df[col1].dropna()
        series2 = self.df[col2].dropna()

        # Alinear series
        common_idx = series1.index.intersection(series2.index)
        if len(common_idx) < 3:
            return {'error': 'Insufficient common data'}

        s1 = series1[common_idx]
        s2 = series2[common_idx]

        try:
            pearson_r, pearson_p = stats.pearsonr(s1, s2)
            spearman_r, spearman_p = stats.spearmanr(s1, s2)

            return {
                'pearson': {
                    'coefficient': float(pearson_r),
                    'pvalue': float(pearson_p),
                    'significant': pearson_p < 0.05
                },
                'spearman': {
                    'coefficient': float(spearman_r),
                    'pvalue': float(spearman_p),
                    'significant': spearman_p < 0.05
                },
                'n_observations': len(common_idx)
            }
        except Exception as e:
            return {'error': str(e)}

    def forecast_summary(self) -> dict:
        """Resumen para pronósticos."""
        try:
            summary = {
                'total_records': len(self.df),
                'date_range': {
                    'start': self.df['timestamp'].min().isoformat() if 'timestamp' in self.df.columns else None,
                    'end': self.df['timestamp'].max().isoformat() if 'timestamp' in self.df.columns else None,
                },
                'stationarity': self.stationarity_tests(),
                'patterns': self.hourly_patterns(),
                'day_patterns': self.day_of_week_patterns(),
            }
            return summary
        except Exception as e:
            return {'error': str(e)}
