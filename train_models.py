#!/usr/bin/env python
"""Train prediction models for all routes."""

import logging
import sys
from pathlib import Path

from src.predictor import RoutePredictor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parent
DB_PATH = ROOT_DIR / "data" / "mobility.db"
MODELS_DIR = ROOT_DIR / "src" / "models" / "trained"


def main():
    """Train all route prediction models."""
    logger.info("Urban Mobility Analytics - Model Training")
    logger.info(f"Database: {DB_PATH}")
    logger.info(f"Models directory: {MODELS_DIR}")
    logger.info("")

    predictor = RoutePredictor(DB_PATH, MODELS_DIR, min_samples=30)

    logger.info("Training models for all routes...")
    results = predictor.train_all_models()

    logger.info("")
    logger.info("Training Results:")
    logger.info("-" * 50)

    success_count = 0
    for route, success in sorted(results.items()):
        status = "✓ Success" if success else "✗ Failed"
        logger.info(f"  {status}: {route}")
        if success:
            success_count += 1

    logger.info("")
    logger.info(f"Summary: {success_count}/{len(results)} models trained successfully")

    if success_count == 0:
        logger.error("No models were trained successfully")
        return 1

    logger.info("")
    logger.info("Model Status:")
    status_all = predictor.get_all_models_status()
    for route, status in sorted(status_all.items()):
        trained = "✓" if status["is_trained"] else "✗"
        logger.info(f"  {trained} {route}")
        if status["is_trained"]:
            importance = status.get("feature_importance", {})
            if importance:
                top_feature = max(importance, key=importance.get)
                top_importance = importance[top_feature]
                logger.info(f"     Top feature: {top_feature} ({top_importance})")

    logger.info("")
    logger.info("✓ Model training complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
