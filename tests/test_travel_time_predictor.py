"""Tests del modelo simple por ruta: src/models/travel_time_model.py (TravelTimePredictor) y src/predictor.py
(RoutePredictor, el orquestador que usa train_models.py)."""

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import RouteDatabase  # noqa: E402
from src.models.travel_time_model import TravelTimePredictor  # noqa: E402
from src.predictor import RoutePredictor  # noqa: E402

FEATURES = ["hour_of_day", "day_of_week", "temperature", "humidity", "no_traffic_time_min", "travel_time_min_lag"]


def _df(n=120, seed=0, sin_tiempo_sin_trafico=False):
    rng = np.random.default_rng(seed)
    sin_trafico = rng.uniform(8, 12, n)
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-01", periods=n, freq="1h", tz="UTC"),
        "origin_temperature": rng.uniform(15, 30, n), "origin_humidity": rng.uniform(40, 80, n),
        "no_traffic_time_min": sin_trafico, "travel_time_min": sin_trafico + rng.uniform(0, 4, n),
    })
    return df.drop(columns="no_traffic_time_min") if sin_tiempo_sin_trafico else df


@pytest.fixture
def entrenado():
    m = TravelTimePredictor()
    assert m.train(_df())
    return m


# ---------------------------------------------------------------------------
# TravelTimePredictor
# ---------------------------------------------------------------------------

def test_prepare_features_devuelve_las_seis_variables_y_el_objetivo():
    """`prepare_features` devuelve las seis variables esperadas y el objetivo, con la hora entre 0 y 23 y el día de la semana entre 0 y 6."""
    X, y = TravelTimePredictor().prepare_features(_df(30))
    assert list(X.columns) == FEATURES and len(X) == len(y) == 30
    assert X["hour_of_day"].between(0, 23).all() and X["day_of_week"].between(0, 6).all()


def test_prepare_features_acepta_columnas_sin_prefijo_origin():
    """`prepare_features` acepta columnas de clima sin el prefijo `origin_`."""
    df = _df(30).rename(columns={"origin_temperature": "temperature", "origin_humidity": "humidity"})
    X, _ = TravelTimePredictor().prepare_features(df)
    assert list(X.columns) == FEATURES


def test_prepare_features_rellena_nulos_con_cero():
    """`prepare_features` rellena los nulos con 0."""
    df = _df(30)
    df.loc[3, "origin_temperature"] = np.nan
    X, _ = TravelTimePredictor().prepare_features(df)
    assert X.loc[3, "temperature"] == 0 and not X.isna().any().any()


@pytest.mark.parametrize("quitar", ["timestamp", "origin_temperature", "origin_humidity", "no_traffic_time_min"])
def test_prepare_features_sin_una_columna_necesaria_devuelve_vacio(quitar):
    """Si falta una columna necesaria (parametrizado), `prepare_features` devuelve tablas vacías."""
    X, y = TravelTimePredictor().prepare_features(_df(30).drop(columns=quitar))
    assert X.empty and y.empty


def test_prepare_features_con_dataframe_vacio():
    """`prepare_features` con un DataFrame vacío devuelve tablas vacías."""
    X, y = TravelTimePredictor().prepare_features(pd.DataFrame())
    assert X.empty and y.empty


def test_entrena_y_registra_las_features(entrenado):
    """El modelo entrena, registra sus variables y su estado, y las importancias suman 1."""
    assert entrenado.is_trained and entrenado.feature_names == FEATURES
    assert entrenado.get_status() == {"is_trained": True, "min_samples_required": 50, "feature_count": 6,
                                      "features": FEATURES}
    imp = entrenado.get_feature_importance()
    assert list(imp) == FEATURES and sum(imp.values()) == pytest.approx(1.0, abs=0.01)


def test_no_entrena_con_pocas_muestras_ni_sin_columnas():
    """No entrena con menos muestras que el mínimo ni si faltan columnas, y lo indica devolviendo `False`."""
    m = TravelTimePredictor(min_samples=50)
    assert m.train(_df(49)) is False and not m.is_trained
    assert m.train(_df(120, sin_tiempo_sin_trafico=True)) is False and not m.is_trained


def test_no_entrena_si_el_objetivo_tiene_nulos():
    """RandomForest no admite NaN en el objetivo: el error se captura y train() devuelve False."""
    df = _df(120)
    df.loc[5, "travel_time_min"] = np.nan
    assert TravelTimePredictor().train(df) is False


def test_predict_devuelve_tiempo_y_confianza_razonables(entrenado):
    """Regresión: predict() devolvía SIEMPRE None, porque se le pasaban al escalador columnas con otro nombre
    (origin_temperature/origin_humidity) que las del ajuste (temperature/humidity) y sklearn lo rechazaba;
    el except lo ocultaba. El modelo por ruta que documenta el README no producía ninguna predicción."""
    resultado = entrenado.predict(hour=10, day_of_week=2, temperature=20, humidity=60, no_traffic_time=10)
    assert resultado is not None
    tiempo, confianza = resultado
    assert 8 < tiempo < 16 and 50 <= confianza <= 100


def test_predict_responde_a_los_datos_de_entrada():
    """El modelo aprende la relación: con un tiempo sin tráfico mayor, predice más."""
    rng = np.random.default_rng(1)
    n = 200
    base = rng.uniform(5, 25, n)
    df = pd.DataFrame({"timestamp": pd.date_range("2026-09-01", periods=n, freq="1h", tz="UTC"),
                       "origin_temperature": 20.0, "origin_humidity": 50.0,
                       "no_traffic_time_min": base, "travel_time_min": base * 1.2})
    m = TravelTimePredictor()
    assert m.train(df)
    corto = m.predict(hour=8, day_of_week=1, temperature=20, humidity=50, no_traffic_time=6, historical_avg=7)
    largo = m.predict(hour=8, day_of_week=1, temperature=20, humidity=50, no_traffic_time=24, historical_avg=29)
    assert largo[0] > corto[0] + 10


def test_predict_sin_entrenar_devuelve_none():
    """Predecir sin haber entrenado devuelve `None`, y la importancia de variables queda vacía."""
    assert TravelTimePredictor().predict(10, 2, 20, 60, 10) is None
    assert TravelTimePredictor().get_feature_importance() == {}


def test_predict_usa_el_historico_como_lag_y_si_falta_el_tiempo_sin_trafico(entrenado, monkeypatch):
    """`historical_avg or no_traffic_time`: con histórico se usa como lag; con None o 0 (falsy) se usa el tiempo
    sin tráfico. Se espía la entrada que recibe el escalador."""
    recibidas = []
    original = entrenado.scaler.transform

    def espia(X):
        recibidas.append(X.copy())
        return original(X)

    monkeypatch.setattr(entrenado.scaler, "transform", espia)
    for historico in (13.5, None, 0):
        assert entrenado.predict(10, 2, 20, 60, 10, historical_avg=historico) is not None
    assert [float(x["travel_time_min_lag"].iloc[0]) for x in recibidas] == [13.5, 10.0, 10.0]
    assert list(recibidas[0].columns) == FEATURES


def test_el_lag_es_la_media_movil_de_5_valores_del_tiempo_de_viaje():
    """Documenta cómo se construye hoy `travel_time_min_lag`: media móvil de 5 filas que INCLUYE la fila actual
    (y las filas llegan de la base ordenadas de más reciente a más antigua). Ver README, limitaciones."""
    df = _df(10)
    df["travel_time_min"] = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    X, _ = TravelTimePredictor().prepare_features(df)
    assert X["travel_time_min_lag"].tolist()[:5] == [10.0, 15.0, 20.0, 25.0, 30.0]    # min_periods=1
    assert X["travel_time_min_lag"].iloc[9] == 80.0                                    # media de 60..100


def test_guardar_y_cargar_reproduce_las_predicciones(entrenado, tmp_path):
    """Un modelo guardado y vuelto a cargar da las mismas predicciones."""
    ruta = tmp_path / "sub" / "m.pkl"
    assert entrenado.save(ruta) and ruta.exists()
    otro = TravelTimePredictor(ruta)                       # el constructor carga el archivo si existe
    assert otro.is_trained and otro.feature_names == FEATURES
    args = dict(hour=10, day_of_week=2, temperature=20, humidity=60, no_traffic_time=10)
    assert otro.predict(**args) == entrenado.predict(**args)


def test_no_guarda_un_modelo_sin_entrenar_y_carga_falla_con_gracia(tmp_path):
    """No guarda un modelo sin entrenar y cargar un archivo inexistente, corrupto o incompleto devuelve `False` sin lanzar excepción."""
    m = TravelTimePredictor()
    assert m.save(tmp_path / "x.pkl") is False and not (tmp_path / "x.pkl").exists()
    assert m.load(tmp_path / "no_existe.pkl") is False
    corrupto = tmp_path / "corrupto.pkl"
    corrupto.write_bytes(b"no es un pickle")
    assert m.load(corrupto) is False and not m.is_trained
    incompleto = tmp_path / "incompleto.pkl"
    incompleto.write_bytes(pickle.dumps({"model": None}))
    assert m.load(incompleto) is False


# ---------------------------------------------------------------------------
# RoutePredictor (orquestador)
# ---------------------------------------------------------------------------

def _registros(origen, destino, n, base=10.0):
    ahora = pd.Timestamp.now(tz="UTC").floor("h")
    return [{"timestamp": (ahora - pd.Timedelta(hours=i)).isoformat(), "origin": origen, "destination": destino,
             "data_source": "tomtom", "travel_time_min": base + (i % 5), "no_traffic_time_min": base,
             "traffic_delay_min": 1.0, "average_speed_kmh": 30.0, "distance_km": 3.0,
             "origin_temperature": 20.0 + i % 4, "origin_humidity": 50.0 + i % 7} for i in range(n)]


@pytest.fixture
def predictor(tmp_path):
    db = tmp_path / "m.db"
    RouteDatabase(tmp_path / "m.csv", db).save_records_to_sqlite(
        _registros("Msida", "Gzira", 80) + _registros("Msida", "Sliema", 10) + _registros("Sliema", "Gzira", 60, 7.0))
    return RoutePredictor(db, tmp_path / "models", min_samples=50)


def test_el_nombre_del_archivo_del_modelo_no_tiene_espacios(predictor):
    """El nombre del archivo del modelo de una ruta cambia los espacios por guiones bajos y cuelga del directorio de modelos."""
    ruta = predictor._get_model_path("St Julian's", "Msida")
    assert ruta.name == "St_Julian's_Msida_model.pkl" and ruta.parent == predictor.models_dir


def test_crea_el_directorio_de_modelos_y_cachea_el_modelo_por_ruta(predictor):
    """Se crea el directorio de modelos y el modelo de cada ruta se reutiliza; la ruta inversa es otro modelo."""
    assert predictor.models_dir.is_dir()
    assert predictor.get_or_create_model("Msida", "Gzira") is predictor.get_or_create_model("Msida", "Gzira")
    assert predictor.get_or_create_model("Msida", "Gzira") is not predictor.get_or_create_model("Gzira", "Msida")


def test_entrena_una_ruta_con_suficientes_datos_y_guarda_el_modelo(predictor):
    """Una ruta con suficientes datos se entrena y su modelo queda guardado en disco."""
    assert predictor.train_route_model("Msida", "Gzira") is True
    assert predictor._get_model_path("Msida", "Gzira").exists()
    assert predictor.get_or_create_model("Msida", "Gzira").is_trained


def test_no_entrena_una_ruta_con_pocas_muestras(predictor):
    """Una ruta con pocas muestras no se entrena ni se guarda."""
    assert predictor.train_route_model("Msida", "Sliema") is False
    assert not predictor._get_model_path("Msida", "Sliema").exists()


def test_min_samples_del_predictor_llega_al_modelo(tmp_path):
    """Regresión: el predictor comprobaba su min_samples pero el modelo usaba su propio mínimo (50), así que con
    min_samples=30 (como train_models.py) una ruta de 40 muestras fallaba al entrenar."""
    db = tmp_path / "m.db"
    RouteDatabase(tmp_path / "m.csv", db).save_records_to_sqlite(_registros("Msida", "Gzira", 40))
    assert RoutePredictor(db, tmp_path / "a", min_samples=30).train_route_model("Msida", "Gzira") is True
    assert RoutePredictor(db, tmp_path / "b", min_samples=50).train_route_model("Msida", "Gzira") is False
    assert RoutePredictor(db, tmp_path / "c", min_samples=30).get_or_create_model("Msida", "Gzira").min_samples == 30


def test_train_all_models_devuelve_un_resultado_por_ruta(predictor):
    """`train_all_models` devuelve un resultado por ruta: entrenada o no."""
    assert predictor.train_all_models() == {"Msida→Gzira": True, "Msida→Sliema": False, "Sliema→Gzira": True}


def test_predice_el_tiempo_de_viaje_de_una_ruta_entrenada(predictor):
    """Una ruta entrenada predice un tiempo de viaje plausible con una confianza entre 50 y 100."""
    predictor.train_route_model("Msida", "Gzira")
    tiempo, confianza = predictor.predict_travel_time("Msida", "Gzira", current_temp=21, current_humidity=55,
                                                      no_traffic_time=10)
    assert 9 < tiempo < 16 and 50 <= confianza <= 100


def test_sin_modelo_entrenado_no_hay_prediccion(predictor):
    """Sin modelo entrenado para la ruta no hay predicción (`None`)."""
    assert predictor.predict_travel_time("Msida", "Sliema", 21, 55, 10) is None


def test_un_predictor_nuevo_reutiliza_los_modelos_guardados(predictor, tmp_path):
    """Un predictor nuevo carga los modelos ya guardados en disco."""
    predictor.train_route_model("Msida", "Gzira")
    nuevo = RoutePredictor(predictor.db_path, predictor.models_dir)
    assert nuevo.get_or_create_model("Msida", "Gzira").is_trained


def test_el_estado_de_los_modelos(predictor):
    """El estado de los modelos lista todas las rutas; las entrenadas incluyen la importancia de variables y las demás no."""
    predictor.train_route_model("Msida", "Gzira")
    estado = predictor.get_all_models_status()
    assert set(estado) == {"Msida→Gzira", "Msida→Sliema", "Sliema→Gzira"}
    entrenado, sin_entrenar = estado["Msida→Gzira"], estado["Msida→Sliema"]
    assert entrenado["is_trained"] and entrenado["route"] == "Msida → Gzira"
    assert list(entrenado["feature_importance"]) == FEATURES
    assert not sin_entrenar["is_trained"] and "feature_importance" not in sin_entrenar
