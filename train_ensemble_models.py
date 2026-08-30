#!/usr/bin/env python3
"""Train ensemble predictive models for all routes."""

import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from src.database import RouteDatabase
from src.models.ensemble_predictor import EnsemblePredictor


def train_all_routes():
    """Train ensemble models for all routes."""
    db_path = ROOT_DIR / "data" / "mobility.db"
    csv_path = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"

    db = RouteDatabase(csv_path, db_path)
    routes = db.get_available_routes()

    print("=" * 60)
    print("ENSEMBLE MODEL TRAINING")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Total routes: {len(routes)}")
    print()

    trained_count = 0
    failed_count = 0

    for origin, destination in routes:
        route_name = f"{origin}_{destination}"
        print(f"Training model for: {origin} → {destination}")

        # Get route data
        df = db.query_measurements(
            origin=origin,
            destination=destination,
            limit=10000
        )

        if df.empty:
            print(f"  ❌ No data available")
            failed_count += 1
            continue

        print(f"  📊 Data points: {len(df)}")

        # Create and train ensemble
        predictor = EnsemblePredictor(route_name, ROOT_DIR / "models")

        result = predictor.train(df)

        if result.get('status') == 'success':
            print(f"  ✅ Training successful")
            for model_info in result.get('models_trained', []):
                if 'r2' in model_info:
                    print(f"    - {model_info['model']}: R² = {model_info['r2']:.3f}")
                else:
                    print(f"    - {model_info['model']}: {model_info.get('status', 'trained')}")

            # Save model
            save_result = predictor.save()
            print(f"  💾 Model saved: {save_result.get('path')}")

            # Test predictions
            X, y, _ = predictor.prepare_features(df)
            if X is not None and len(X) > 0:
                pred = predictor.predict(X[0:1])
                if 'ensemble_prediction' in pred:
                    print(f"  🎯 Sample prediction: {pred['ensemble_prediction']:.1f} min")
                    print(f"     Confidence (95%): [{pred['confidence_interval_95']['lower']:.1f}, {pred['confidence_interval_95']['upper']:.1f}]")

            trained_count += 1
        else:
            print(f"  ❌ Training failed: {result.get('error')}")
            failed_count += 1

        print()

    print("=" * 60)
    print("TRAINING SUMMARY")
    print("=" * 60)
    print(f"Successfully trained: {trained_count}/{len(routes)}")
    print(f"Failed: {failed_count}/{len(routes)}")
    print(f"Completion rate: {(trained_count / len(routes) * 100):.1f}%")
    print()

    if trained_count > 0:
        print("✅ Ensemble models ready for production!")
        print("   Use ensemble_predictor.EnsemblePredictor to load and make predictions.")
    else:
        print("⚠️  No models were successfully trained.")
        print("   Ensure you have at least 50 data points per route.")

    print("=" * 60)


if __name__ == "__main__":
    train_all_routes()
