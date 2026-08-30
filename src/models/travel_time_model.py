"""Travel time prediction model using historical data."""

import logging
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class TravelTimePredictor:
    """Predicts travel time based on historical data and current conditions."""

    def __init__(self, model_path: Optional[Path] = None, min_samples: int = 50):
        self.model_path = model_path
        self.min_samples = min_samples
        self.model = None
        self.scaler = None
        self.feature_names = None
        self.is_trained = False

        if model_path and model_path.exists():
            self.load(model_path)

    def prepare_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Prepara features para el modelo.

        Features:
        - hour_of_day (0-23)
        - day_of_week (0-6)
        - temperature (usa origin_temperature o temperature)
        - humidity (usa origin_humidity o humidity)
        - no_traffic_time_min
        - historical_avg_travel_time
        """
        if df.empty:
            return pd.DataFrame(), pd.Series()

        df_feat = df.copy()

        if "timestamp" in df_feat.columns:
            df_feat["timestamp"] = pd.to_datetime(df_feat["timestamp"], utc=True)
            df_feat["hour_of_day"] = df_feat["timestamp"].dt.hour
            df_feat["day_of_week"] = df_feat["timestamp"].dt.dayofweek
        else:
            logger.warning("timestamp column not found")
            return pd.DataFrame(), pd.Series()

        temp_col = "origin_temperature" if "origin_temperature" in df_feat.columns else "temperature"
        humid_col = "origin_humidity" if "origin_humidity" in df_feat.columns else "humidity"

        if temp_col not in df_feat.columns:
            logger.warning(f"Temperature column not found")
            return pd.DataFrame(), pd.Series()

        if humid_col not in df_feat.columns:
            logger.warning(f"Humidity column not found")
            return pd.DataFrame(), pd.Series()

        if "no_traffic_time_min" not in df_feat.columns:
            logger.warning("no_traffic_time_min column not found")
            return pd.DataFrame(), pd.Series()

        df_feat["travel_time_min_lag"] = df_feat["travel_time_min"].rolling(
            window=5, min_periods=1
        ).mean()

        features_df = df_feat[[
            "hour_of_day", "day_of_week", temp_col,
            humid_col, "no_traffic_time_min", "travel_time_min_lag"
        ]].copy()

        features_df.columns = [
            "hour_of_day", "day_of_week", "temperature",
            "humidity", "no_traffic_time_min", "travel_time_min_lag"
        ]

        features_df = features_df.fillna(0)

        target = df_feat["travel_time_min"]

        return features_df, target

    def train(self, df: pd.DataFrame) -> bool:
        """
        Entrena el modelo con datos históricos.

        Returns:
            True si el entrenamiento fue exitoso, False en caso contrario.
        """
        if len(df) < self.min_samples:
            logger.warning(
                f"Insufficient data for training: {len(df)} samples "
                f"(minimum: {self.min_samples})"
            )
            return False

        try:
            X, y = self.prepare_features(df)

            if X.empty:
                logger.error("Could not prepare features")
                return False

            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)

            self.model = RandomForestRegressor(
                n_estimators=50,
                max_depth=10,
                random_state=42,
                n_jobs=-1,
            )

            self.model.fit(X_scaled, y)
            self.feature_names = X.columns.tolist()
            self.is_trained = True

            logger.info(f"Model trained successfully on {len(df)} samples")
            return True

        except Exception as e:
            logger.error(f"Error training model: {e}")
            return False

    def predict(
        self,
        hour: int,
        day_of_week: int,
        temperature: float,
        humidity: float,
        no_traffic_time: float,
        historical_avg: Optional[float] = None,
    ) -> Optional[Tuple[float, float]]:
        """
        Predice el tiempo de viaje.

        Returns:
            Tuple of (predicted_time, confidence) or None if model not trained.
        """
        if not self.is_trained or self.model is None:
            return None

        try:
            X = pd.DataFrame([{
                "hour_of_day": hour,
                "day_of_week": day_of_week,
                "origin_temperature": temperature,
                "origin_humidity": humidity,
                "no_traffic_time_min": no_traffic_time,
                "travel_time_min_lag": historical_avg or no_traffic_time,
            }])

            X_scaled = self.scaler.transform(X)
            prediction = self.model.predict(X_scaled)[0]

            confidence = min(100, 50 + (no_traffic_time / prediction * 50))

            return round(prediction, 2), round(confidence, 1)

        except Exception as e:
            logger.error(f"Error making prediction: {e}")
            return None

    def get_feature_importance(self) -> dict:
        """Retorna la importancia de cada feature."""
        if not self.is_trained or self.model is None:
            return {}

        importance_dict = {}
        for name, importance in zip(self.feature_names, self.model.feature_importances_):
            importance_dict[name] = round(float(importance), 3)

        return importance_dict

    def save(self, path: Path) -> bool:
        """Guarda el modelo entrenado."""
        if not self.is_trained:
            logger.warning("Model not trained, cannot save")
            return False

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                pickle.dump({
                    "model": self.model,
                    "scaler": self.scaler,
                    "feature_names": self.feature_names,
                }, f)
            logger.info(f"Model saved to {path}")
            return True
        except Exception as e:
            logger.error(f"Error saving model: {e}")
            return False

    def load(self, path: Path) -> bool:
        """Carga un modelo previamente entrenado."""
        if not path.exists():
            logger.warning(f"Model file not found: {path}")
            return False

        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            self.model = data["model"]
            self.scaler = data["scaler"]
            self.feature_names = data["feature_names"]
            self.is_trained = True
            logger.info(f"Model loaded from {path}")
            return True
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False

    def get_status(self) -> dict:
        """Retorna el estado del modelo."""
        return {
            "is_trained": self.is_trained,
            "min_samples_required": self.min_samples,
            "feature_count": len(self.feature_names) if self.feature_names else 0,
            "features": self.feature_names or [],
        }
