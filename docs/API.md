# Urban Mobility Analytics - REST API Documentation

## Overview

RESTful API for urban traffic prediction, analysis, and time series forecasting. All responses include structured data with error handling.

**Base URL:** `http://localhost:8000`  
**Version:** 1.0.0  
**Authentication:** None (add JWT in production)

---

## Quick Start

```bash
# 1. Install dependencies
pip install fastapi uvicorn

# 2. Run API server
python src/api.py

# 3. Visit documentation
# Swagger UI: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

---

## API Endpoints

### 1. Health Check

**GET** `/api/health`

Check system status and available routes.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-07-19T01:35:00Z",
  "routes": 6,
  "database": "connected"
}
```

---

### 2. Predict Travel Time

**GET** `/api/predict/{origin}/{destination}`

Predict travel time with confidence intervals.

**Parameters:**
- `origin` (string, required): Starting location (e.g., "Msida")
- `destination` (string, required): Ending location (e.g., "Marsaskala")
- `days` (integer, optional): Days of historical data to use (default: 30, range: 1-90)

**Example Request:**
```bash
curl "http://localhost:8000/api/predict/Msida/Marsaskala?days=30"
```

**Response:**
```json
{
  "route": "Msida → Marsaskala",
  "prediction": {
    "value": 17.5,
    "unit": "minutes",
    "confidence_interval_80": {
      "lower": 16.1,
      "upper": 18.9
    },
    "confidence_interval_95": {
      "lower": 15.2,
      "upper": 19.8
    },
    "std": 1.15
  },
  "timestamp": "2026-07-19T01:35:00Z",
  "models_used": ["random_forest", "gradient_boosting", "exponential_smoothing"]
}
```

**Interpretation:**
- Ensemble predicts **17.5 minutes**
- 95% confident actual is between **15.2 - 19.8 minutes**
- Standard deviation: **1.15 minutes**

**Error Responses:**
```json
{
  "detail": "No data for this route"
}
```

---

### 3. Route Rankings

**GET** `/api/routes/rankings`

Get routes ranked by reliability and performance.

**Parameters:**
- `days` (integer, optional): Period to analyze (default: 30, range: 1-90)

**Response:**
```json
{
  "date": "2026-07-19",
  "period_days": 30,
  "best_routes": [
    {
      "route": "Msida → Sliema",
      "avg_time": 5.8,
      "avg_reliability": 94.3
    },
    {
      "route": "Msida → Gzira",
      "avg_time": 4.6,
      "avg_reliability": 94.1
    }
  ],
  "worst_routes": [
    {
      "route": "Msida → Marsaskala",
      "avg_time": 17.5,
      "avg_reliability": 91.3
    }
  ],
  "system_metrics": {
    "avg_travel_time": 10.2,
    "reliability_score": 92.8
  }
}
```

---

### 4. Week-Ahead Forecast

**GET** `/api/forecast/{origin}/{destination}`

Forecast travel times for the next 7 days using Prophet.

**Parameters:**
- `origin` (string, required)
- `destination` (string, required)

**Response:**
```json
{
  "route": "Msida → Marsaskala",
  "forecast": {
    "forecast": {
      "dates": [
        "2026-07-19 00:00:00",
        "2026-07-19 01:00:00",
        ...
      ],
      "predictions": [17.2, 16.9, 17.1, ...],
      "lower_bound": [15.1, 14.8, ...],
      "upper_bound": [19.3, 19.0, ...]
    },
    "model": "Prophet (Weekly)",
    "frequency": "hourly"
  },
  "generated_at": "2026-07-19T01:35:00Z"
}
```

---

### 5. Anomaly Detection

**GET** `/api/anomalies/{origin}/{destination}`

Detect unusual traffic patterns.

**Parameters:**
- `origin` (string, required)
- `destination` (string, required)
- `days` (integer, optional): Period to analyze (default: 30)
- `threshold` (float, optional): Z-score threshold (default: 2.5, range: 1-5)

**Response:**
```json
{
  "route": "Msida → Marsaskala",
  "period_days": 30,
  "anomalies": {
    "total_anomalies": 2,
    "percentage": 2.5,
    "threshold": 3.2,
    "anomalies": [
      {
        "timestamp": "2026-07-15 14:30:00",
        "value": 45.2,
        "z_score": 3.8,
        "deviation": "High"
      }
    ],
    "mean": 17.5,
    "std": 2.1
  }
}
```

---

### 6. Route Statistics

**GET** `/api/statistics/{origin}/{destination}`

Get summary statistics for a route.

**Parameters:**
- `origin` (string, required)
- `destination` (string, required)
- `hours` (integer, optional): Time window (default: 24, range: 1-720)

**Response:**
```json
{
  "route": "Msida → Marsaskala",
  "period_hours": 24,
  "statistics": {
    "avg_travel_time": 17.5,
    "median_travel_time": 17.3,
    "std_travel_time": 2.1,
    "min_travel_time": 14.2,
    "max_travel_time": 23.8,
    "sample_count": 24,
    "avg_speed": 45.2
  }
}
```

---

### 7. Time Series Analysis

**GET** `/api/time-series/{origin}/{destination}`

Advanced time series analysis.

**Parameters:**
- `origin` (string, required)
- `destination` (string, required)
- `days` (integer, optional): Period (default: 30, range: 7-90)
- `analysis` (string, required): Type of analysis
  - `patterns` - Day-of-week patterns
  - `stationarity` - ADF/KPSS tests
  - `anomalies` - Change point detection

**Example: Day-of-Week Patterns**
```bash
curl "http://localhost:8000/api/time-series/Msida/Marsaskala?analysis=patterns"
```

**Response:**
```json
{
  "route": "Msida → Marsaskala",
  "analysis_type": "patterns",
  "period_days": 30,
  "result": {
    "by_day": {
      "Monday": {
        "mean": 18.2,
        "median": 18.1,
        "std": 2.3,
        "count": 4
      },
      "Tuesday": {
        "mean": 17.8,
        "median": 17.6,
        "std": 2.1,
        "count": 4
      }
    },
    "comparison": {
      "weekday_mean": 17.9,
      "weekend_mean": 16.5,
      "ttest_pvalue": 0.032,
      "significantly_different": true
    }
  }
}
```

**Example: Stationarity Test**
```bash
curl "http://localhost:8000/api/time-series/Msida/Marsaskala?analysis=stationarity"
```

**Response:**
```json
{
  "result": {
    "adf": {
      "statistic": -3.42,
      "pvalue": 0.008,
      "critical_values": {
        "1%": -3.58,
        "5%": -2.93,
        "10%": -2.62
      },
      "is_stationary": true,
      "interpretation": "Estacionaria"
    },
    "kpss": {
      "statistic": 0.28,
      "pvalue": 0.1,
      "is_stationary": true,
      "interpretation": "Estacionaria"
    }
  }
}
```

---

### 8. List Available Routes

**GET** `/api/routes`

Get all available routes in the system.

**Response:**
```json
{
  "total_routes": 6,
  "routes": [
    {
      "origin": "Msida",
      "destination": "Birkirkara"
    },
    {
      "origin": "Msida",
      "destination": "Gzira"
    },
    {
      "origin": "Msida",
      "destination": "Marsaskala"
    },
    {
      "origin": "Msida",
      "destination": "Sliema"
    },
    {
      "origin": "Msida",
      "destination": "St Julian's"
    },
    {
      "origin": "Msida",
      "destination": "Valletta"
    }
  ]
}
```

---

## Error Handling

All errors follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common HTTP Status Codes:**

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (invalid parameters) |
| 404 | Resource not found |
| 500 | Server error |

---

## Rate Limiting

- **No rate limiting** (add in production)
- Recommended: 100 requests/minute per IP

---

## Examples

### Python Client

```python
import requests

BASE_URL = "http://localhost:8000"

# Get prediction
response = requests.get(
    f"{BASE_URL}/api/predict/Msida/Marsaskala",
    params={"days": 30}
)
data = response.json()
print(f"Predicted time: {data['prediction']['value']} minutes")
print(f"95% CI: [{data['prediction']['confidence_interval_95']['lower']}, "
      f"{data['prediction']['confidence_interval_95']['upper']}]")

# Get rankings
rankings = requests.get(f"{BASE_URL}/api/routes/rankings").json()
print("Best routes:", rankings['best_routes'])
```

### JavaScript/Node.js

```javascript
const BASE_URL = 'http://localhost:8000';

// Get prediction
fetch(`${BASE_URL}/api/predict/Msida/Marsaskala?days=30`)
  .then(r => r.json())
  .then(data => {
    console.log(`Predicted: ${data.prediction.value} min`);
    console.log(`95% CI: [${data.prediction.confidence_interval_95.lower}, ${data.prediction.confidence_interval_95.upper}]`);
  });
```

### cURL

```bash
# Get routes
curl "http://localhost:8000/api/routes"

# Get prediction
curl "http://localhost:8000/api/predict/Msida/Marsaskala?days=30"

# Get anomalies
curl "http://localhost:8000/api/anomalies/Msida/Marsaskala?threshold=2.5"

# Get time series analysis
curl "http://localhost:8000/api/time-series/Msida/Marsaskala?analysis=patterns"
```

---

## API Response Time SLA

| Endpoint | Target | Typical |
|----------|--------|---------|
| `/api/health` | <100ms | ~50ms |
| `/api/predict/*` | <500ms | ~200ms |
| `/api/routes/rankings` | <1000ms | ~400ms |
| `/api/forecast/*` | <2000ms | ~800ms |
| `/api/time-series/*` | <1500ms | ~600ms |

---

## Versioning

Current: **v1.0**

Future versions will be accessible at:
- `GET /api/v2/predict/...`
- `GET /api/v2/routes/...`

---

## Support

- **Issues:** GitHub Issues
- **Documentation:** [Full docs](../README.md)
- **Examples:** `examples/api_usage.py`

