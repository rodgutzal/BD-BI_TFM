"""Ensemble predictor combining multiple ML paradigms."""

import pickle
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import r2_score
from sklearn.preprocessing import StandardScaler

try:
    import xgboost as xgb

    HAS_XGBOOST = True
except (ImportError, Exception):
    HAS_XGBOOST = False

try:
    from prophet import Prophet

    HAS_PROPHET = True
except ImportError:
    HAS_PROPHET = False

warnings.filterwarnings("ignore")

# Medición fuera de muestra con un corte cronológico: entrenar con el 80 % más antiguo, medir en el 20 % más reciente.
FRACCION_ENTRENAMIENTO = 0.8
MIN_FILAS_FUERA_DE_MUESTRA = 100


class EnsemblePredictor:
    """Ensemble de modelos de regresión sobre features tabulares (hora, día,
    mes, clima): XGBoost (opcional), Random Forest y Gradient Boosting.

    Suavizado exponencial (Holt-Winters) NO forma parte del ensemble: se
    entrenaba y se guardaba, pero predict() nunca lo usaba, porque un modelo
    de serie temporal no predice a partir de una fila de features y además
    se ajustaba sobre mediciones ordenadas de la más reciente a la más
    antigua. Prophet se usa solo en forecast_week_ahead().
    """

    def __init__(self, route_name: str = "default", models_dir: Path = None):
        """Inicializar ensemble."""
        self.route_name = route_name
        self.models_dir = models_dir or Path("models")
        self.models_dir.mkdir(exist_ok=True)

        self.models = {
            "xgboost": None,
            "random_forest": None,
            "gradient_boosting": None,
        }
        self.scaler = StandardScaler()
        # Se normalizan en predict() sobre los modelos disponibles, así que
        # no hace falta que sumen 1 (p. ej. si xgboost no está instalado).
        self.ensemble_weights = {"xgboost": 0.4, "random_forest": 0.25, "gradient_boosting": 0.25}
        self.is_trained = False

    def prepare_features(self, df: pd.DataFrame) -> tuple:
        """Preparar features para entrenar."""
        df = df.copy()

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df["hour"] = df["timestamp"].dt.hour
            df["day_of_week"] = df["timestamp"].dt.dayofweek
            df["day_of_month"] = df["timestamp"].dt.day
            df["month"] = df["timestamp"].dt.month
        else:
            df["hour"] = 0
            df["day_of_week"] = 0
            df["day_of_month"] = 1
            df["month"] = 1

        # Features: time-based + weather
        feature_cols = ["hour", "day_of_week", "day_of_month", "month"]

        # Agregar weather si existe
        for col in ["origin_temperature", "temperature", "origin_humidity", "humidity"]:
            if col in df.columns:
                feature_cols.append(col)

        X = df[feature_cols].fillna(0).values
        y = df["travel_time_min"].values if "travel_time_min" in df.columns else None

        return X, y, feature_cols

    @staticmethod
    def _build_models() -> dict:
        """Modelos sin ajustar, con los hiperparámetros de siempre (xgboost solo si está instalado)."""
        modelos = {}
        if HAS_XGBOOST:
            modelos["xgboost"] = xgb.XGBRegressor(
                n_estimators=100, max_depth=5, learning_rate=0.1, subsample=0.8, random_state=42
            )
        modelos["random_forest"] = RandomForestRegressor(
            n_estimators=100, max_depth=15, min_samples_split=5, random_state=42, n_jobs=-1
        )
        modelos["gradient_boosting"] = GradientBoostingRegressor(
            n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42
        )
        return modelos

    @classmethod
    def _fit_all(cls, X_scaled, y) -> tuple:
        """Ajusta cada modelo por separado: si uno falla, los demás siguen. Devuelve (ajustados, errores)."""
        ajustados, errores = {}, {}
        for nombre, modelo in cls._build_models().items():
            try:
                if nombre == "xgboost":
                    modelo.fit(X_scaled, y, verbose=False)
                else:
                    modelo.fit(X_scaled, y)
                ajustados[nombre] = modelo
            except Exception as e:
                errores[nombre] = str(e)
        return ajustados, errores

    def _weighted(self, predicciones: dict):
        """Predicción ponderada del ensemble con los pesos normalizados sobre los modelos disponibles."""
        nombres = list(predicciones)
        pesos = np.array([self.ensemble_weights[n] for n in nombres], dtype=float)
        return np.average([predicciones[n] for n in nombres], axis=0, weights=pesos / pesos.sum())

    def _evaluar_fuera_de_muestra(self, df: pd.DataFrame, X, y) -> dict:
        """Corte CRONOLÓGICO: ajusta con el 80 % más antiguo y mide (R² y MAE) en el 20 % más reciente, que ningún
        modelo ha visto. `df` debe llegar ya ordenado de más antiguo a más reciente.

        Las referencias son las mismas que en tools/validate_travel_time_model.py: la media del tramo de entrenamiento y
        repetir la última medición de la MISMA fuente de datos (la base mezcla ORS, sin tráfico, y TomTom, con él). Todo
        se mide sobre las filas que tienen esa última medición, para que la comparación sea justa."""
        corte = int(len(df) * FRACCION_ENTRENAMIENTO)
        escalador = StandardScaler()
        X_ent = escalador.fit_transform(X[:corte])
        X_test = escalador.transform(X[corte:])
        y_ent, y_test = y[:corte], y[corte:]

        serie = pd.Series(y, index=df.index)
        if "data_source" in df.columns:
            ultimo = serie.groupby(df["data_source"]).shift(1)
        else:
            ultimo = serie.shift(1)
        ultimo_test = ultimo.to_numpy()[corte:]
        valido = ~np.isnan(ultimo_test)
        if valido.sum() < 2:
            return {"error": "Sin filas de prueba con una medición anterior de la misma fuente"}

        y_val = y_test[valido]
        ajustados, _ = self._fit_all(X_ent, y_ent)
        predicciones = {n: m.predict(X_test)[valido] for n, m in ajustados.items()}

        def _metricas(pred):
            return {"r2": float(r2_score(y_val, pred)), "mae": float(np.mean(np.abs(y_val - pred)))}

        resultado = {
            "n_entrenamiento": int(corte),
            "n_prueba": int(valido.sum()),
            "corte": str(df["timestamp"].iloc[corte]) if "timestamp" in df.columns else None,
            "modelos": {n: _metricas(p) for n, p in predicciones.items()},
            "referencias": {
                "media_entrenamiento": {"mae": float(np.mean(np.abs(y_val - np.mean(y_ent))))},
                "ultimo_valor": {"mae": float(np.mean(np.abs(y_val - ultimo_test[valido])))},
            },
        }
        if predicciones:
            resultado["ensemble"] = _metricas(self._weighted(predicciones))
            resultado["supera_a_ultimo_valor"] = bool(
                resultado["ensemble"]["mae"] < resultado["referencias"]["ultimo_valor"]["mae"]
            )
        return resultado

    def train(self, df: pd.DataFrame) -> dict:
        """Entrenar ensemble.

        Devuelve, por modelo, `r2_entrenamiento` (EN MUESTRA: mide lo bien que el modelo se aprendió los datos con los que
        se ajustó, no su capacidad de predecir) y, si hay datos suficientes, `r2` y `mae` FUERA DE MUESTRA con un corte
        cronológico, más las referencias en `holdout`. Después de medir, el modelo definitivo se reajusta con todos los
        datos. Antes solo se devolvía la R² en muestra con el nombre `r2`, que con bosques profundos sale muy alta aunque
        el modelo no sirva para predecir."""
        if len(df) < 50:
            return {"error": "Insufficient data (need 50+ samples)", "trained": False}

        # Orden cronológico: la base entrega las filas de la más reciente a la más antigua, y un corte sin ordenar mediría
        # con las mediciones más antiguas.
        if "timestamp" in df.columns:
            df = df.assign(timestamp=pd.to_datetime(df["timestamp"], utc=True)).sort_values("timestamp", kind="stable")
            df = df.reset_index(drop=True)

        X, y, feature_cols = self.prepare_features(df)

        if y is None or len(y) < 50:
            return {"error": "Insufficient target data", "trained": False}

        results = {"models_trained": []}

        if "timestamp" not in df.columns:
            results["holdout"] = {"error": "Sin columna timestamp: no se puede hacer un corte cronológico"}
        elif len(df) < MIN_FILAS_FUERA_DE_MUESTRA:
            results["holdout"] = {
                "error": f"Menos de {MIN_FILAS_FUERA_DE_MUESTRA} filas: no se mide fuera de muestra, solo en muestra"
            }
        else:
            results["holdout"] = self._evaluar_fuera_de_muestra(df, X, y)

        # Modelo definitivo: con TODOS los datos
        X_scaled = self.scaler.fit_transform(X)
        ajustados, errores = self._fit_all(X_scaled, y)
        fuera = results["holdout"].get("modelos", {})

        for nombre in ("xgboost", "random_forest", "gradient_boosting"):
            self.models[nombre] = ajustados.get(nombre)
            if nombre in ajustados:
                entrada = {
                    "model": nombre,
                    "r2_entrenamiento": float(r2_score(y, ajustados[nombre].predict(X_scaled))),
                }
                if nombre in fuera:
                    entrada.update(fuera[nombre])
                results["models_trained"].append(entrada)
            elif nombre in errores:
                results["models_trained"].append({"model": nombre, "error": errores[nombre]})
            else:
                results["models_trained"].append({"model": nombre, "status": "skipped (not installed)"})

        self.is_trained = True
        results["status"] = "success"
        results["samples_used"] = len(df)

        return results

    def predict(self, X: np.ndarray) -> dict:
        """Predicción ensemble con intervalos de confianza."""
        if not self.is_trained:
            return {"error": "Model not trained"}

        X_scaled = self.scaler.transform(X)
        predictions = {}

        # Recopilar predicciones de cada modelo
        model_preds = []
        weights_list = []

        if self.models["xgboost"] is not None:
            try:
                xgb_pred = self.models["xgboost"].predict(X_scaled)
                model_preds.append(xgb_pred)
                weights_list.append(self.ensemble_weights["xgboost"])
                predictions["xgboost"] = float(xgb_pred[0]) if len(xgb_pred) > 0 else None
            except:
                pass

        if self.models["random_forest"] is not None:
            try:
                rf_pred = self.models["random_forest"].predict(X_scaled)
                model_preds.append(rf_pred)
                weights_list.append(self.ensemble_weights["random_forest"])
                predictions["random_forest"] = float(rf_pred[0]) if len(rf_pred) > 0 else None
            except:
                pass

        if self.models["gradient_boosting"] is not None:
            try:
                gb_pred = self.models["gradient_boosting"].predict(X_scaled)
                model_preds.append(gb_pred)
                weights_list.append(self.ensemble_weights["gradient_boosting"])
                predictions["gradient_boosting"] = float(gb_pred[0]) if len(gb_pred) > 0 else None
            except:
                pass

        # Predicción ponderada
        if model_preds:
            weights_array = np.array(weights_list)
            weights_array = weights_array / weights_array.sum()  # Normalizar

            ensemble_pred = np.average(model_preds, axis=0, weights=weights_array)
            ensemble_std = np.std(model_preds, axis=0)

            predictions["ensemble_prediction"] = float(ensemble_pred[0])
            predictions["confidence_interval_80"] = {
                "lower": float(ensemble_pred[0] - 1.28 * ensemble_std[0]),
                "upper": float(ensemble_pred[0] + 1.28 * ensemble_std[0]),
            }
            predictions["confidence_interval_95"] = {
                "lower": float(ensemble_pred[0] - 1.96 * ensemble_std[0]),
                "upper": float(ensemble_pred[0] + 1.96 * ensemble_std[0]),
            }
            predictions["prediction_std"] = float(ensemble_std[0])
            # Predicción individual de cada modelo, en un dict aparte. Antes
            # se asignaba `predictions` a sí mismo (referencia circular, que
            # rompe json.dumps / la serialización de FastAPI).
            predictions["model_predictions"] = {
                name: predictions[name]
                for name in ("xgboost", "random_forest", "gradient_boosting")
                if name in predictions
            }

        return predictions

    def forecast_week_ahead(self, df: pd.DataFrame) -> dict:
        """Pronóstico de 7 días hacia adelante."""
        if len(df) < 50:
            return {"error": "Insufficient data"}

        if not HAS_PROPHET:
            return {"error": "Prophet not installed", "fallback": "Use ensemble predictions instead"}

        try:
            # Preparar datos para Prophet
            prophet_df = df[["timestamp", "travel_time_min"]].copy()
            prophet_df.columns = ["ds", "y"]
            prophet_df["ds"] = pd.to_datetime(prophet_df["ds"], utc=True)

            # Entrenar Prophet
            model = Prophet(yearly_seasonality=False, daily_seasonality=True, interval_width=0.95)
            model.fit(prophet_df)

            # Forecast
            future = model.make_future_dataframe(periods=7 * 24, freq="h")  # 7 días de horas
            forecast = model.predict(future)

            # Últimas predicciones (7 días)
            future_forecast = forecast.tail(7 * 24)[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()

            return {
                "forecast": {
                    "dates": future_forecast["ds"].dt.strftime("%Y-%m-%d %H:%M:%S").tolist(),
                    "predictions": future_forecast["yhat"].tolist(),
                    "lower_bound": future_forecast["yhat_lower"].tolist(),
                    "upper_bound": future_forecast["yhat_upper"].tolist(),
                },
                "model": "Prophet (Weekly)",
                "frequency": "hourly",
            }
        except Exception as e:
            return {"error": str(e)}

    def anomaly_detection(self, df: pd.DataFrame, threshold: float = 2.5) -> dict:
        """Detectar anomalías en tráfico."""
        if "travel_time_min" not in df.columns:
            return {"error": "Missing travel_time_min column"}

        try:
            # Z-score método
            mean = df["travel_time_min"].mean()
            std = df["travel_time_min"].std()

            df_anom = df.copy()
            df_anom["z_score"] = (df_anom["travel_time_min"] - mean) / std
            df_anom["is_anomaly"] = abs(df_anom["z_score"]) > threshold

            anomalies = df_anom[df_anom["is_anomaly"]].copy()

            return {
                "total_anomalies": int(len(anomalies)),
                "percentage": float(len(anomalies) / len(df_anom) * 100),
                "threshold": float(threshold),
                "anomalies": [
                    {
                        "timestamp": row.get("timestamp", str(i)),
                        "value": float(row["travel_time_min"]),
                        "z_score": float(row["z_score"]),
                        "deviation": "High" if row["z_score"] > 0 else "Low",
                    }
                    for i, (_, row) in enumerate(anomalies.head(20).iterrows())
                ],
                "mean": float(mean),
                "std": float(std),
            }
        except Exception as e:
            return {"error": str(e)}

    def save(self):
        """Guardar modelos."""
        try:
            model_path = self.models_dir / f"{self.route_name}_ensemble.pkl"
            with open(model_path, "wb") as f:
                pickle.dump(
                    {
                        "models": self.models,
                        "scaler": self.scaler,
                        "weights": self.ensemble_weights,
                        "is_trained": self.is_trained,
                    },
                    f,
                )
            return {"status": "saved", "path": str(model_path)}
        except Exception as e:
            return {"error": str(e)}

    def load(self):
        """Cargar modelos."""
        try:
            model_path = self.models_dir / f"{self.route_name}_ensemble.pkl"
            if model_path.exists():
                with open(model_path, "rb") as f:
                    data = pickle.load(f)
                    self.models = data["models"]
                    self.scaler = data["scaler"]
                    self.ensemble_weights = data["weights"]
                    self.is_trained = data["is_trained"]
                return {"status": "loaded", "path": str(model_path)}
            else:
                return {"error": "Model file not found"}
        except Exception as e:
            return {"error": str(e)}
