"""Prediction orchestrator for travel times."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from src.database import RouteDatabase
from src.models.travel_time_model import TravelTimePredictor

logger = logging.getLogger(__name__)


class RoutePredictor:
    """Manages predictions for all routes."""

    def __init__(self, db_path: Path, models_dir: Path, min_samples: int = 50):
        self.db_path = db_path
        self.models_dir = models_dir
        self.min_samples = min_samples
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.models: Dict[Tuple[str, str], TravelTimePredictor] = {}

    def _get_model_path(self, origin: str, destination: str) -> Path:
        """Retorna el path del archivo de modelo para una ruta."""
        route_key = f"{origin}_{destination}".replace(" ", "_")
        return self.models_dir / f"{route_key}_model.pkl"

    def get_or_create_model(self, origin: str, destination: str) -> TravelTimePredictor:
        """Obtiene o crea un modelo para una ruta específica."""
        key = (origin, destination)

        if key in self.models:
            return self.models[key]

        model = TravelTimePredictor(self._get_model_path(origin, destination))
        self.models[key] = model
        return model

    def train_route_model(self, origin: str, destination: str) -> bool:
        """Entrena el modelo para una ruta específica."""
        db = RouteDatabase(Path.home(), self.db_path)

        df = db.query_measurements(
            origin=origin,
            destination=destination,
            limit=10000
        )

        if len(df) < self.min_samples:
            logger.warning(
                f"Insufficient data for {origin} → {destination}: "
                f"{len(df)} samples (need {self.min_samples})"
            )
            return False

        model = self.get_or_create_model(origin, destination)
        success = model.train(df)

        if success:
            model.save(self._get_model_path(origin, destination))
            logger.info(f"Model trained for {origin} → {destination}")
        else:
            logger.error(f"Failed to train model for {origin} → {destination}")

        return success

    def train_all_models(self) -> Dict[str, bool]:
        """Entrena modelos para todas las rutas disponibles."""
        db = RouteDatabase(Path.home(), self.db_path)
        routes = db.get_available_routes()

        results = {}
        for origin, destination in routes:
            success = self.train_route_model(origin, destination)
            results[f"{origin}→{destination}"] = success

        return results

    def predict_travel_time(
        self,
        origin: str,
        destination: str,
        current_temp: float,
        current_humidity: float,
        no_traffic_time: float,
    ) -> Optional[Tuple[float, float]]:
        """
        Predice el tiempo de viaje para ahora.

        Returns:
            Tuple of (predicted_time, confidence) or None if model not available.
        """
        model = self.get_or_create_model(origin, destination)

        if not model.is_trained:
            logger.debug(f"Model not trained for {origin} → {destination}")
            return None

        now = datetime.now(timezone.utc)
        hour = now.hour
        day_of_week = now.weekday()

        db = RouteDatabase(Path.home(), self.db_path)
        recent_data = db.query_measurements(
            origin=origin,
            destination=destination,
            limit=100
        )

        historical_avg = None
        if not recent_data.empty and "travel_time_min" in recent_data.columns:
            historical_avg = recent_data["travel_time_min"].mean()

        return model.predict(
            hour=hour,
            day_of_week=day_of_week,
            temperature=current_temp,
            humidity=current_humidity,
            no_traffic_time=no_traffic_time,
            historical_avg=historical_avg,
        )

    def get_model_status(self, origin: str, destination: str) -> dict:
        """Retorna el estado del modelo para una ruta."""
        model = self.get_or_create_model(origin, destination)
        status = model.get_status()
        status["route"] = f"{origin} → {destination}"

        if model.is_trained:
            status["feature_importance"] = model.get_feature_importance()

        return status

    def get_all_models_status(self) -> dict:
        """Retorna el estado de todos los modelos."""
        db = RouteDatabase(Path.home(), self.db_path)
        routes = db.get_available_routes()

        status = {}
        for origin, destination in routes:
            route_key = f"{origin}→{destination}"
            status[route_key] = self.get_model_status(origin, destination)

        return status
