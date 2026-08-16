"""FastAPI REST endpoint for predictions and analytics."""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.database import RouteDatabase
from src.models.ensemble_predictor import EnsemblePredictor
from src.analytics.time_series_analysis import TimeSeriesAnalytics
from src.data_warehouse.gold_layer import GoldLayer

# Initialize FastAPI
app = FastAPI(
    title="Urban Mobility Analytics API",
    description="Predicciones y análisis de movilidad urbana",
    version="1.0.0"
)

# Initialize resources
DB_PATH = ROOT_DIR / "data" / "mobility.db"
CSV_PATH = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"

db = RouteDatabase(CSV_PATH, DB_PATH)
gold = GoldLayer(DB_PATH)


@app.get("/api/health")
async def health_check():
    """System health check."""
    try:
        routes = db.get_available_routes()
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "routes": len(routes),
            "database": "connected"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/predict/{origin}/{destination}")
async def predict_route(
    origin: str,
    destination: str,
    days: int = Query(30, ge=1, le=90)
):
    """
    Predict travel time with confidence intervals.

    Example: /api/predict/Msida/Marsaskala
    """
    try:
        # Load route data
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        df = db.query_measurements(
            origin=origin,
            destination=destination,
            start_timestamp=start_date.isoformat(),
            end_timestamp=end_date.isoformat(),
            limit=10000
        )

        if df.empty:
            raise HTTPException(status_code=404, detail="No data for this route")

        # Load trained model
        predictor = EnsemblePredictor(f"{origin}_{destination}", ROOT_DIR / "models")
        predictor.load()

        if not predictor.is_trained:
            # Train if not loaded
            predictor.train(df)

        # Make prediction on latest data
        X, _, _ = predictor.prepare_features(df)
        if X is None or len(X) == 0:
            raise HTTPException(status_code=400, detail="Cannot prepare features")

        prediction = predictor.predict(X[-1:])

        return {
            "route": f"{origin} → {destination}",
            "prediction": {
                "value": prediction.get('ensemble_prediction'),
                "unit": "minutes",
                "confidence_interval_80": prediction.get('confidence_interval_80'),
                "confidence_interval_95": prediction.get('confidence_interval_95'),
                "std": prediction.get('prediction_std')
            },
            "timestamp": end_date.isoformat(),
            "models_used": list(predictor.models.keys())
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/routes/rankings")
async def get_route_rankings(days: int = Query(30, ge=1, le=90)):
    """Get route rankings by reliability."""
    try:
        summary = gold.get_executive_summary(days=days)

        best_routes = summary.get('best_routes', [])
        worst_routes = summary.get('worst_routes', [])

        return {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "period_days": days,
            "best_routes": best_routes,
            "worst_routes": worst_routes,
            "system_metrics": {
                "avg_travel_time": summary.get('system_avg_travel_time'),
                "reliability_score": summary.get('system_reliability')
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/forecast/{origin}/{destination}")
async def forecast_week_ahead(origin: str, destination: str):
    """Forecast next 7 days of travel time."""
    try:
        # Get historical data
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=60)

        df = db.query_measurements(
            origin=origin,
            destination=destination,
            start_timestamp=start_date.isoformat(),
            end_timestamp=end_date.isoformat(),
            limit=10000
        )

        if df.empty or len(df) < 50:
            raise HTTPException(status_code=404, detail="Insufficient data for forecast")

        # Make forecast
        predictor = EnsemblePredictor(f"{origin}_{destination}", ROOT_DIR / "models")
        if predictor.load().get('status') == 'loaded' or predictor.is_trained:
            forecast = predictor.forecast_week_ahead(df)
        else:
            forecast = {"error": "Model not trained", "fallback": "Use /api/predict instead"}

        return {
            "route": f"{origin} → {destination}",
            "forecast": forecast,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/anomalies/{origin}/{destination}")
async def detect_anomalies(
    origin: str,
    destination: str,
    days: int = Query(30, ge=1, le=90),
    threshold: float = Query(2.5, ge=1, le=5)
):
    """Detect traffic anomalies."""
    try:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        df = db.query_measurements(
            origin=origin,
            destination=destination,
            start_timestamp=start_date.isoformat(),
            end_timestamp=end_date.isoformat(),
            limit=10000
        )

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        predictor = EnsemblePredictor(f"{origin}_{destination}", ROOT_DIR / "models")
        anomalies = predictor.anomaly_detection(df, threshold=threshold)

        return {
            "route": f"{origin} → {destination}",
            "period_days": days,
            "anomalies": anomalies
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/statistics/{origin}/{destination}")
async def get_route_statistics(
    origin: str,
    destination: str,
    hours: int = Query(24, ge=1, le=720)
):
    """Get route statistics."""
    try:
        stats = db.get_route_statistics(origin, destination, hours=hours)

        if not stats:
            raise HTTPException(status_code=404, detail="No data available")

        return {
            "route": f"{origin} → {destination}",
            "period_hours": hours,
            "statistics": stats
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/time-series/{origin}/{destination}")
async def time_series_analysis(
    origin: str,
    destination: str,
    days: int = Query(30, ge=7, le=90),
    analysis: str = Query("patterns", regex="^(patterns|stationarity|anomalies)$")
):
    """Advanced time series analysis."""
    try:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        df = db.query_measurements(
            origin=origin,
            destination=destination,
            start_timestamp=start_date.isoformat(),
            end_timestamp=end_date.isoformat(),
            limit=10000
        )

        if df.empty or len(df) < 20:
            raise HTTPException(status_code=404, detail="Insufficient data")

        tsa = TimeSeriesAnalytics(df)

        if analysis == "patterns":
            result = tsa.day_of_week_patterns('travel_time_min')
        elif analysis == "stationarity":
            result = tsa.stationarity_tests('travel_time_min')
        elif analysis == "anomalies":
            result = tsa.change_point_detection('travel_time_min')
        else:
            raise HTTPException(status_code=400, detail="Invalid analysis type")

        return {
            "route": f"{origin} → {destination}",
            "analysis_type": analysis,
            "period_days": days,
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/routes")
async def list_routes():
    """List all available routes."""
    try:
        routes = db.get_available_routes()
        return {
            "total_routes": len(routes),
            "routes": [{"origin": r[0], "destination": r[1]} for r in routes]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
