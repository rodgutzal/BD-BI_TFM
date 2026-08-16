"""Ensemble predictor combining multiple ML paradigms."""

import numpy as np
import pandas as pd
from pathlib import Path
import pickle
import warnings
from datetime import datetime, timedelta

from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
try:
    import xgboost as xgb
    HAS_XGBOOST = True
except (ImportError, Exception):
    HAS_XGBOOST = False

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
except ImportError:
    ExponentialSmoothing = None

try:
    from prophet import Prophet
    HAS_PROPHET = True
except ImportError:
    HAS_PROPHET = False

warnings.filterwarnings('ignore')


class EnsemblePredictor:
    """Ensemble de múltiples modelos para predicción robusta."""

    def __init__(self, route_name: str = 'default', models_dir: Path = None):
        """Inicializar ensemble."""
        self.route_name = route_name
        self.models_dir = models_dir or Path('models')
        self.models_dir.mkdir(exist_ok=True)

        self.models = {
            'xgboost': None,
            'random_forest': None,
            'gradient_boosting': None,
            'exponential_smoothing': None,
        }
        self.scaler = StandardScaler()
        self.ensemble_weights = {'xgboost': 0.4, 'random_forest': 0.25, 'gradient_boosting': 0.25, 'exponential_smoothing': 0.1}
        self.is_trained = False

    def prepare_features(self, df: pd.DataFrame) -> tuple:
        """Preparar features para entrenar."""
        df = df.copy()

        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            df['hour'] = df['timestamp'].dt.hour
            df['day_of_week'] = df['timestamp'].dt.dayofweek
            df['day_of_month'] = df['timestamp'].dt.day
            df['month'] = df['timestamp'].dt.month
        else:
            df['hour'] = 0
            df['day_of_week'] = 0
            df['day_of_month'] = 1
            df['month'] = 1

        # Features: time-based + weather
        feature_cols = ['hour', 'day_of_week', 'day_of_month', 'month']

        # Agregar weather si existe
        for col in ['origin_temperature', 'temperature', 'origin_humidity', 'humidity']:
            if col in df.columns:
                feature_cols.append(col)

        X = df[feature_cols].fillna(0).values
        y = df['travel_time_min'].values if 'travel_time_min' in df.columns else None

        return X, y, feature_cols

    def train(self, df: pd.DataFrame) -> dict:
        """Entrenar ensemble."""
        if len(df) < 50:
            return {'error': 'Insufficient data (need 50+ samples)', 'trained': False}

        X, y, feature_cols = self.prepare_features(df)

        if y is None or len(y) < 50:
            return {'error': 'Insufficient target data', 'trained': False}

        # Escalar features
        X_scaled = self.scaler.fit_transform(X)

        results = {'models_trained': []}

        # 1. XGBoost (optional)
        if HAS_XGBOOST:
            try:
                self.models['xgboost'] = xgb.XGBRegressor(
                    n_estimators=100,
                    max_depth=5,
                    learning_rate=0.1,
                    subsample=0.8,
                    random_state=42
                )
                self.models['xgboost'].fit(X_scaled, y, verbose=False)
                xgb_score = r2_score(y, self.models['xgboost'].predict(X_scaled))
                results['models_trained'].append({'model': 'xgboost', 'r2': float(xgb_score)})
            except Exception as e:
                results['models_trained'].append({'model': 'xgboost', 'error': str(e)})
        else:
            results['models_trained'].append({'model': 'xgboost', 'status': 'skipped (not installed)'})

        # 2. Random Forest
        try:
            self.models['random_forest'] = RandomForestRegressor(
                n_estimators=100,
                max_depth=15,
                min_samples_split=5,
                random_state=42,
                n_jobs=-1
            )
            self.models['random_forest'].fit(X_scaled, y)
            rf_score = r2_score(y, self.models['random_forest'].predict(X_scaled))
            results['models_trained'].append({'model': 'random_forest', 'r2': float(rf_score)})
        except Exception as e:
            results['models_trained'].append({'model': 'random_forest', 'error': str(e)})

        # 3. Gradient Boosting
        try:
            self.models['gradient_boosting'] = GradientBoostingRegressor(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
            self.models['gradient_boosting'].fit(X_scaled, y)
            gb_score = r2_score(y, self.models['gradient_boosting'].predict(X_scaled))
            results['models_trained'].append({'model': 'gradient_boosting', 'r2': float(gb_score)})
        except Exception as e:
            results['models_trained'].append({'model': 'gradient_boosting', 'error': str(e)})

        # 4. Exponential Smoothing (para series temporales)
        try:
            if ExponentialSmoothing is not None and len(y) >= 12:
                self.models['exponential_smoothing'] = ExponentialSmoothing(
                    y, seasonal_periods=12, trend='add', seasonal='add', initialization_method='estimated'
                ).fit(optimized=True, disp=False)
                results['models_trained'].append({'model': 'exponential_smoothing', 'status': 'trained'})
        except Exception as e:
            results['models_trained'].append({'model': 'exponential_smoothing', 'error': str(e)})

        self.is_trained = True
        results['status'] = 'success'
        results['samples_used'] = len(df)

        return results

    def predict(self, X: np.ndarray) -> dict:
        """Predicción ensemble con intervalos de confianza."""
        if not self.is_trained:
            return {'error': 'Model not trained'}

        X_scaled = self.scaler.transform(X)
        predictions = {}

        # Recopilar predicciones de cada modelo
        model_preds = []
        weights_list = []

        if self.models['xgboost'] is not None:
            try:
                xgb_pred = self.models['xgboost'].predict(X_scaled)
                model_preds.append(xgb_pred)
                weights_list.append(self.ensemble_weights['xgboost'])
                predictions['xgboost'] = float(xgb_pred[0]) if len(xgb_pred) > 0 else None
            except:
                pass

        if self.models['random_forest'] is not None:
            try:
                rf_pred = self.models['random_forest'].predict(X_scaled)
                model_preds.append(rf_pred)
                weights_list.append(self.ensemble_weights['random_forest'])
                predictions['random_forest'] = float(rf_pred[0]) if len(rf_pred) > 0 else None
            except:
                pass

        if self.models['gradient_boosting'] is not None:
            try:
                gb_pred = self.models['gradient_boosting'].predict(X_scaled)
                model_preds.append(gb_pred)
                weights_list.append(self.ensemble_weights['gradient_boosting'])
                predictions['gradient_boosting'] = float(gb_pred[0]) if len(gb_pred) > 0 else None
            except:
                pass

        # Predicción ponderada
        if model_preds:
            weights_array = np.array(weights_list)
            weights_array = weights_array / weights_array.sum()  # Normalizar

            ensemble_pred = np.average(model_preds, axis=0, weights=weights_array)
            ensemble_std = np.std(model_preds, axis=0)

            predictions['ensemble_prediction'] = float(ensemble_pred[0])
            predictions['confidence_interval_80'] = {
                'lower': float(ensemble_pred[0] - 1.28 * ensemble_std[0]),
                'upper': float(ensemble_pred[0] + 1.28 * ensemble_std[0])
            }
            predictions['confidence_interval_95'] = {
                'lower': float(ensemble_pred[0] - 1.96 * ensemble_std[0]),
                'upper': float(ensemble_pred[0] + 1.96 * ensemble_std[0])
            }
            predictions['prediction_std'] = float(ensemble_std[0])
            predictions['model_predictions'] = predictions

        return predictions

    def forecast_week_ahead(self, df: pd.DataFrame) -> dict:
        """Pronóstico de 7 días hacia adelante."""
        if len(df) < 50:
            return {'error': 'Insufficient data'}

        if not HAS_PROPHET:
            return {'error': 'Prophet not installed', 'fallback': 'Use ensemble predictions instead'}

        try:
            # Preparar datos para Prophet
            prophet_df = df[['timestamp', 'travel_time_min']].copy()
            prophet_df.columns = ['ds', 'y']
            prophet_df['ds'] = pd.to_datetime(prophet_df['ds'], utc=True)

            # Entrenar Prophet
            model = Prophet(yearly_seasonality=False, daily_seasonality=True, interval_width=0.95)
            model.fit(prophet_df)

            # Forecast
            future = model.make_future_dataframe(periods=7 * 24, freq='H')  # 7 días de horas
            forecast = model.predict(future)

            # Últimas predicciones (7 días)
            future_forecast = forecast.tail(7 * 24)[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].copy()

            return {
                'forecast': {
                    'dates': future_forecast['ds'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist(),
                    'predictions': future_forecast['yhat'].tolist(),
                    'lower_bound': future_forecast['yhat_lower'].tolist(),
                    'upper_bound': future_forecast['yhat_upper'].tolist(),
                },
                'model': 'Prophet (Weekly)',
                'frequency': 'hourly'
            }
        except Exception as e:
            return {'error': str(e)}

    def anomaly_detection(self, df: pd.DataFrame, threshold: float = 2.5) -> dict:
        """Detectar anomalías en tráfico."""
        if 'travel_time_min' not in df.columns:
            return {'error': 'Missing travel_time_min column'}

        try:
            # Z-score método
            mean = df['travel_time_min'].mean()
            std = df['travel_time_min'].std()

            df_anom = df.copy()
            df_anom['z_score'] = (df_anom['travel_time_min'] - mean) / std
            df_anom['is_anomaly'] = abs(df_anom['z_score']) > threshold

            anomalies = df_anom[df_anom['is_anomaly']].copy()

            return {
                'total_anomalies': int(len(anomalies)),
                'percentage': float(len(anomalies) / len(df_anom) * 100),
                'threshold': float(threshold),
                'anomalies': [
                    {
                        'timestamp': row.get('timestamp', str(i)),
                        'value': float(row['travel_time_min']),
                        'z_score': float(row['z_score']),
                        'deviation': 'High' if row['z_score'] > 0 else 'Low'
                    }
                    for i, (_, row) in enumerate(anomalies.head(20).iterrows())
                ],
                'mean': float(mean),
                'std': float(std)
            }
        except Exception as e:
            return {'error': str(e)}

    def save(self):
        """Guardar modelos."""
        try:
            model_path = self.models_dir / f'{self.route_name}_ensemble.pkl'
            with open(model_path, 'wb') as f:
                pickle.dump({
                    'models': self.models,
                    'scaler': self.scaler,
                    'weights': self.ensemble_weights,
                    'is_trained': self.is_trained
                }, f)
            return {'status': 'saved', 'path': str(model_path)}
        except Exception as e:
            return {'error': str(e)}

    def load(self):
        """Cargar modelos."""
        try:
            model_path = self.models_dir / f'{self.route_name}_ensemble.pkl'
            if model_path.exists():
                with open(model_path, 'rb') as f:
                    data = pickle.load(f)
                    self.models = data['models']
                    self.scaler = data['scaler']
                    self.ensemble_weights = data['weights']
                    self.is_trained = data['is_trained']
                return {'status': 'loaded', 'path': str(model_path)}
            else:
                return {'error': 'Model file not found'}
        except Exception as e:
            return {'error': str(e)}
