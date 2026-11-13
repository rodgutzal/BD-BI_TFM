"""Modelado Predictivo reproducido de forma interactiva.

Reproduce sobre los datos EN VIVO de la base de datos (misma tabla y esquema
que el CSV exportado y usado en notebooks/Asignatura7_Modelado_Predictivo.Rmd)
la misma metodología validada en ese notebook:

    EDA -> preprocesamiento -> clasificación (mobility_level) ->
    regresión (travel_time_min) -> forecasting horario -> clustering de corredores

Las cifras exactas pueden diferir levemente de las del .Rmd (el dataset vivo
sigue creciendo y aquí se usa scikit-learn en vez de caret/randomForest/xgboost),
pero la metodología -features, exclusión de fuga de datos, umbral de 20 min- es
la misma, para que el resultado sea trazable frente al entregable académico.
Una diferencia deliberada: el .Rmd divide train/test al azar y aquí la división
es CRONOLÓGICA (el 80 % más antiguo entrena, el 20 % más reciente evalúa), porque
al azar se evalúa con mediciones vecinas en el tiempo de las que se entrenó y se
sobrestima la calidad con datos futuros.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    mean_absolute_error,
    r2_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.tree import plot_tree

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src import forecasting  # noqa: E402
from src.database import RouteDatabase  # noqa: E402

DATE_CUTOFF = "2026-08-01"  # excluye las pruebas iniciales del pipeline (mayo 2026)
NUM_COLS = [
    "distance_km",
    "origin_temperature",
    "origin_humidity",
    "destination_temperature",
    "destination_humidity",
]
WEATHER_GROUPS = {
    "clear sky": "despejado",
    "few clouds": "parcialmente_nublado",
    "scattered clouds": "parcialmente_nublado",
    "broken clouds": "nublado",
    "overcast clouds": "nublado",
}
RMD_PATH = "notebooks/Asignatura7_Modelado_Predictivo.Rmd"


# --------------------------------------------------------------------------
# Carga y preparación de datos
# --------------------------------------------------------------------------


@st.cache_data(ttl=1800, show_spinner="Cargando datos en vivo desde la base de datos...")
def load_modeling_data() -> pd.DataFrame:
    db_path = ROOT_DIR / "data" / "mobility.db"
    csv_path = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"
    db = RouteDatabase(csv_path, db_path)
    df = db.query_measurements(limit=1_000_000)
    if df.empty:
        return df

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df[df["timestamp"] >= pd.Timestamp(DATE_CUTOFF, tz="utc")].copy()
    df = df.sort_values("timestamp").drop(columns=["polyline"], errors="ignore")
    return df


def _engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["hora"] = d["timestamp"].dt.hour
    d["dia_semana"] = d["timestamp"].dt.dayofweek + 1  # 1 = lunes ... 7 = domingo
    d["es_finde"] = d["dia_semana"].isin([6, 7]).astype(int)
    d["hora_sin"] = np.sin(2 * np.pi * d["hora"] / 24)
    d["hora_cos"] = np.cos(2 * np.pi * d["hora"] / 24)
    for lado in ("origin", "destination"):
        descripcion = d[f"{lado}_weather"]
        grupo = descripcion.map(WEATHER_GROUPS)
        # Una descripción que existe pero no está en WEATHER_GROUPS (rain, mist,
        # drizzle...) es "lluvia", como en el .Rmd. Pero una descripción AUSENTE
        # (OpenWeather falló en ese ciclo y el clima quedó NULL) NO es lluvia:
        # antes `.fillna("lluvia")` las convertía también, etiquetando mal esas
        # filas. Se dejan en NaN y _complete_cases() las excluye de los modelos
        # que usan el clima.
        grupo = grupo.where(~(descripcion.notna() & grupo.isna()), "lluvia")
        d[f"{lado}_weather_grp"] = grupo
    return d


# Columnas que necesitan los modelos de clasificación y regresión. Si alguna es
# NaN, LogisticRegression/StandardScaler fallan ("Input X contains NaN").
MODEL_FEATURE_COLS = NUM_COLS + ["origin_weather_grp", "destination_weather_grp"]


def _complete_cases(d: pd.DataFrame) -> pd.DataFrame:
    """Filas sin ningún dato faltante en las variables de los modelos.

    Con datos reales, unas pocas filas (OpenWeather falló en ese ciclo) traen el
    clima en NULL; una sola basta para que `LogisticRegression` lance
    `Input X contains NaN`. Esa excepción cortaba toda la vista Analyst: las
    pestañas posteriores a "Model Performance" (Data Quality, SQL Query,
    Exportar Todo) no se renderizaban. Solo clasificación y regresión usan el
    clima: el forecast temporal y el clustering conservan estas filas, porque su
    tiempo de viaje es válido.
    """
    return d.dropna(subset=MODEL_FEATURE_COLS)


FRACCION_ENTRENAMIENTO = 0.8


def _particion_cronologica(d: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Ordena por fecha y devuelve (d ordenado, máscara de entrenamiento): el 80 % más antiguo entrena y el 20 %
    más reciente evalúa.

    Una partición aleatoria mezcla en el entrenamiento mediciones de los mismos ciclos y horas que luego se
    evalúan (en una serie temporal, vecinas en el tiempo y casi iguales): sobrestima lo que el modelo acertaría
    con datos futuros. El corte es por fecha, de modo que las mediciones de un mismo ciclo (misma marca de
    tiempo, una por ruta) caen todas en el mismo lado.
    """
    d = d.sort_values("timestamp", kind="stable")
    corte = d["timestamp"].iloc[int(len(d) * FRACCION_ENTRENAMIENTO)]
    return d, (d["timestamp"] < corte).to_numpy()


def _design_matrix(d: pd.DataFrame) -> pd.DataFrame:
    """One-hot encoding (fullRank, como dummyVars en R) + variables numéricas/cíclicas."""
    cat_cols = ["origin", "destination", "data_source", "origin_weather_grp", "destination_weather_grp"]
    other_cols = ["hora_sin", "hora_cos", "dia_semana", "es_finde"]
    X = pd.get_dummies(d[cat_cols + NUM_COLS + other_cols], columns=cat_cols, drop_first=True)
    return X


# --------------------------------------------------------------------------
# Clasificación: mobility_level
# --------------------------------------------------------------------------

# Los modelos ajustados se guardan con cache_resource (el objeto tal cual) y no con
# cache_data (que guarda una copia serializada de lo que devuelve: con un Random Forest de
# 300 árboles eso duplicaba cientos de MB). max_entries=1: si los datos cambian, la entrada
# nueva REEMPLAZA a la anterior en vez de acumularse. Las funciones _fit_* no modifican su
# resultado y las render_* solo lo leen, así que compartir el objeto es seguro.
_CACHE_MODELO = dict(max_entries=1)


@st.cache_resource(show_spinner="Entrenando clasificador (regresión logística + Random Forest)...", **_CACHE_MODELO)
def _fit_classification(d: pd.DataFrame):
    d, es_entrenamiento = _particion_cronologica(_complete_cases(d))
    X = _design_matrix(d)
    y = (d["mobility_level"] == "Alta demora").astype(int).values

    X_train, X_test = X[es_entrenamiento], X[~es_entrenamiento]
    y_train, y_test = y[es_entrenamiento], y[~es_entrenamiento]

    scaler = StandardScaler()
    X_train_s, X_test_s = X_train.copy(), X_test.copy()
    X_train_s[NUM_COLS] = scaler.fit_transform(X_train[NUM_COLS])
    X_test_s[NUM_COLS] = scaler.transform(X_test[NUM_COLS])

    logit = LogisticRegression(max_iter=2000)
    logit.fit(X_train_s, y_train)
    prob_logit = logit.predict_proba(X_test_s)[:, 1]

    rf = RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1)
    grid = GridSearchCV(
        rf,
        {"max_features": ["sqrt", "log2", 0.3, 0.5]},
        scoring="roc_auc",
        cv=TimeSeriesSplit(
            5
        ),  # pliegues en orden de filas: validan con filas posteriores (como mucho un ciclo compartido)
        n_jobs=-1,
    )
    grid.fit(X_train_s, y_train)
    rf_best = grid.best_estimator_
    prob_rf = rf_best.predict_proba(X_test_s)[:, 1]

    importances = pd.Series(rf_best.feature_importances_, index=X.columns).sort_values(ascending=False)

    return {
        "y_test": y_test,
        "prob_logit": prob_logit,
        "prob_rf": prob_rf,
        "best_max_features": grid.best_params_["max_features"],
        "cv_auc": grid.best_score_,
        "importances": importances,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "model": rf_best,
        "feature_names": list(X.columns),
    }


def _plot_tree_figure(rf_model, feature_names: list[str], max_depth_view: int):
    """Dibuja el primer árbol del Random Forest, truncado a max_depth_view niveles."""
    fig, ax = plt.subplots(figsize=(20, 10))
    plot_tree(
        rf_model.estimators_[0],
        max_depth=max_depth_view,
        feature_names=feature_names,
        class_names=["Movilidad normal", "Alta demora"],
        filled=True,
        rounded=True,
        proportion=True,
        fontsize=9,
        ax=ax,
    )
    fig.tight_layout()
    return fig


def render_classification(d: pd.DataFrame) -> None:
    st.subheader("🚦 Clasificación: `mobility_level`")
    st.caption(
        "`travel_time_min` se excluye de los predictores (fuga de datos: el umbral de "
        "20 min sobre esa variable define la etiqueta). Igual metodología que "
        f"`{RMD_PATH}`."
    )

    res = _fit_classification(d)
    y_test = res["y_test"]

    def summarize(prob, thr=0.5):
        pred = (prob >= thr).astype(int)
        return {
            "Accuracy": accuracy_score(y_test, pred),
            "Balanced Accuracy": balanced_accuracy_score(y_test, pred),
            "AUC": roc_auc_score(y_test, prob),
        }

    m_logit = summarize(res["prob_logit"])
    m_rf = summarize(res["prob_rf"])

    c1, c2, c3 = st.columns(3)
    c1.metric("Accuracy — Random Forest", f"{m_rf['Accuracy']:.1%}", f"vs {m_logit['Accuracy']:.1%} logística")
    c2.metric("Balanced Accuracy — RF", f"{m_rf['Balanced Accuracy']:.1%}")
    c3.metric(
        "AUC — RF (CV temporal 5 pliegues)",
        f"{res['cv_auc']:.3f}",
        help=f"max_features óptimo: {res['best_max_features']}",
    )

    n_alta = int(y_test.sum())
    n_total = len(y_test)
    st.info(
        f"Partición cronológica: {res['n_train']:,} train (las más antiguas) / {res['n_test']:,} test (las más recientes) · "
        f"{n_alta}/{n_total} ({n_alta/n_total:.1%}) en 'Alta demora'.",
        icon="ℹ️",
    )

    col_roc, col_imp = st.columns(2)

    with col_roc:
        fig = go.Figure()
        for name, prob in [("Random Forest", res["prob_rf"]), ("Regresión logística", res["prob_logit"])]:
            fpr, tpr, _ = roc_curve(y_test, prob)
            auc = roc_auc_score(y_test, prob)
            fig.add_trace(go.Scatter(x=fpr, y=tpr, mode="lines", name=f"{name} (AUC={auc:.3f})"))
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(dash="dash", color="gray"), name="Azar"))
        fig.update_layout(
            title="Curva ROC",
            xaxis_title="1 - Especificidad",
            yaxis_title="Sensibilidad",
            template="plotly_dark",
            height=420,
        )
        st.plotly_chart(fig, width="stretch")

    with col_imp:
        top = res["importances"].head(12).sort_values()
        fig = go.Figure(go.Bar(x=top.values, y=top.index, orientation="h", marker_color="#2c7fb8"))
        fig.update_layout(title="Importancia de variables — Random Forest", template="plotly_dark", height=420)
        st.plotly_chart(fig, width="stretch")

    with st.expander("Matriz de confusión — Random Forest"):
        pred_rf = (res["prob_rf"] >= 0.5).astype(int)
        cm = confusion_matrix(y_test, pred_rf, labels=[0, 1])
        cm_df = pd.DataFrame(
            cm,
            index=["Real: Movilidad normal", "Real: Alta demora"],
            columns=["Pred: Movilidad normal", "Pred: Alta demora"],
        )
        st.dataframe(cm_df, width="stretch")

    top_routes = res["importances"][res["importances"].index.str.startswith(("origin_", "destination_"))].head(3)
    if not top_routes.empty:
        st.caption(
            "⚠️ El AUC casi perfecto refleja que varios corredores caen sistemáticamente en un "
            "solo lado del umbral de 20 min (ver EDA del .Rmd): la identidad del corredor "
            f"(p. ej. {', '.join(top_routes.index[:2])}) ya es muy informativa por sí sola."
        )

    with st.expander("🌳 Expresión gráfica del Random Forest (árbol de ejemplo)"):
        st.caption(
            "El bosque entrena 300 árboles; mostrar los 300 no aporta lectura. Aquí se dibuja "
            "el primer árbol del ensemble, truncado a la profundidad elegida, solo para "
            "ilustrar la forma de las reglas de decisión que aprende el modelo."
        )
        max_depth_view = st.slider(
            "Profundidad a mostrar",
            2,
            5,
            3,
            key="pm_tree_depth",
            help="Solo limita lo que se dibuja; el árbol entrenado internamente es más profundo.",
        )
        fig_tree = _plot_tree_figure(res["model"], res["feature_names"], max_depth_view)
        st.pyplot(fig_tree)


# --------------------------------------------------------------------------
# Regresión: travel_time_min
# --------------------------------------------------------------------------


@st.cache_resource(show_spinner="Entrenando regresores (lineal + Gradient Boosting)...", **_CACHE_MODELO)
def _fit_regression(d: pd.DataFrame):
    d, es_entrenamiento = _particion_cronologica(_complete_cases(d))
    X = _design_matrix(d)
    y = d["travel_time_min"].values

    X_train, X_test = X[es_entrenamiento], X[~es_entrenamiento]
    y_train, y_test = y[es_entrenamiento], y[~es_entrenamiento]

    scaler = StandardScaler()
    X_train_s, X_test_s = X_train.copy(), X_test.copy()
    X_train_s[NUM_COLS] = scaler.fit_transform(X_train[NUM_COLS])
    X_test_s[NUM_COLS] = scaler.transform(X_test[NUM_COLS])

    lm = LinearRegression()
    lm.fit(X_train_s, y_train)
    pred_lm = lm.predict(X_test_s)

    gbr = GradientBoostingRegressor(n_estimators=250, max_depth=4, learning_rate=0.08, random_state=42)
    gbr.fit(X_train_s, y_train)
    pred_gbr = gbr.predict(X_test_s)

    importances = pd.Series(gbr.feature_importances_, index=X.columns).sort_values(ascending=False)

    def metrics(pred):
        return {
            "RMSE": float(np.sqrt(np.mean((pred - y_test) ** 2))),
            "MAE": float(mean_absolute_error(y_test, pred)),
            "R2": float(r2_score(y_test, pred)),
        }

    return {
        "y_test": y_test,
        "pred_lm": pred_lm,
        "pred_gbr": pred_gbr,
        "metrics_lm": metrics(pred_lm),
        "metrics_gbr": metrics(pred_gbr),
        "importances": importances,
    }


def render_regression(d: pd.DataFrame) -> None:
    st.subheader("⏱️ Regresión: `travel_time_min`")
    st.caption("`mobility_level` se excluye de los predictores (es función determinista del propio target).")

    res = _fit_regression(d)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Regresión lineal (línea base)**")
        m = res["metrics_lm"]
        st.write(f"RMSE: `{m['RMSE']:.2f}` · MAE: `{m['MAE']:.2f}` · R²: `{m['R2']:.3f}`")
    with c2:
        st.markdown("**Gradient Boosting**")
        m = res["metrics_gbr"]
        st.write(f"RMSE: `{m['RMSE']:.2f}` · MAE: `{m['MAE']:.2f}` · R²: `{m['R2']:.3f}`")

    col_scatter, col_imp = st.columns(2)

    with col_scatter:
        fig = go.Figure(
            go.Scatter(
                x=res["y_test"],
                y=res["pred_gbr"],
                mode="markers",
                marker=dict(color="#2c7fb8", opacity=0.25, size=5),
                name="Predicciones",
            )
        )
        lims = [float(min(res["y_test"])), float(max(res["y_test"]))]
        fig.add_trace(go.Scatter(x=lims, y=lims, mode="lines", line=dict(color="red", dash="dash"), name="Ideal"))
        fig.update_layout(
            title="Gradient Boosting: real vs. predicho",
            xaxis_title="Real (min)",
            yaxis_title="Predicho (min)",
            template="plotly_dark",
            height=420,
        )
        st.plotly_chart(fig, width="stretch")

    with col_imp:
        top = res["importances"].head(12).sort_values()
        fig = go.Figure(go.Bar(x=top.values, y=top.index, orientation="h", marker_color="#d95f02"))
        fig.update_layout(title="Importancia de variables — Gradient Boosting", template="plotly_dark", height=420)
        st.plotly_chart(fig, width="stretch")


# --------------------------------------------------------------------------
# Forecasting horario (extensión temporal)
# --------------------------------------------------------------------------


@st.cache_resource(show_spinner="Ajustando el modelo de series temporales...", **_CACHE_MODELO)
def _fit_temporal(d: pd.DataFrame, max_gap_hours: int = 3):
    s = forecasting.hourly_share(
        d.assign(alta=(d["mobility_level"] == "Alta demora").astype(int)).set_index("timestamp")["alta"]
    )

    # A diferencia del fill(down) del .Rmd (que arrastra el valor plano sobre huecos de varios
    # días), las horas sin dato NO se rellenan más allá de `max_gap_hours` consecutivas: quedan
    # como NaN y el modelo de espacio de estados las trata como datos faltantes.
    #
    # La serie se modela ENTERA (con sus huecos como NaN), no "el bloque continuo más reciente":
    # `resample("1h")` crea un índice horario REGULAR, así que la diferencia entre horas consecutivas
    # es siempre 1 h y nunca se parte en bloques. Dividir por los huecos reales dejaría, con un equipo
    # que se apaga cada noche, un bloque de pocas horas, inútil para una estacionalidad de 24 h.
    gap = s.index.to_series().diff().dt.total_seconds() / 3600
    block_id = (gap > max_gap_hours).cumsum()
    last_block = block_id.iloc[-1]
    s_block = s[block_id == last_block]

    # El modelo (SARIMA con diferenciación estacional, serie en escala 0-100) vive en
    # src/forecasting.py, que también usa tools/validate_forecast.py: lo que se valida es lo que se muestra.
    fc = forecasting.forecast_sarima(s_block, steps=forecasting.HORIZON, max_gap_hours=max_gap_hours)

    return {
        "series": s_block.interpolate(limit=max_gap_hours),
        "order": forecasting.ORDER,
        "seasonal_order": forecasting.SEASONAL_ORDER,
        "forecast_mean": fc["mean"],
        "forecast_ci": fc["ci"],
        "converged": fc["converged"],
        "iterations": fc["iterations"],
        # Referencia: la media de cada hora del día. Es lo que el ARIMA tiene que mejorar.
        "baseline": forecasting.profile_forecast(s_block, fc["mean"].index),
        "gap_excluded_hours": int((s.index[-1] - s_block.index[0]).total_seconds() / 3600) - len(s_block) + 1,
    }


def render_temporal(d: pd.DataFrame) -> None:
    st.subheader("📈 Forecasting horario de congestión (extensión)")
    st.caption(
        "Serie horaria de % 'Alta demora'. Se ajusta un SARIMA con diferenciación estacional de 24 h sobre toda "
        "la serie: las horas sin dato (equipo apagado) no se rellenan, el modelo las trata como datos faltantes."
    )

    res = _fit_temporal(d)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=res["series"].index, y=res["series"].values, mode="lines", name="Observado", line=dict(color="#2c7fb8")
        )
    )
    fig.add_trace(
        go.Scatter(
            x=res["forecast_mean"].index,
            y=res["forecast_mean"].values,
            mode="lines",
            name="Forecast 24h (SARIMA)",
            line=dict(color="#1b9e77"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=res["baseline"].index,
            y=res["baseline"].values,
            mode="lines",
            name="Referencia: media por hora del día",
            line=dict(color="#e6ab02", dash="dash"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=list(res["forecast_ci"].index) + list(res["forecast_ci"].index[::-1]),
            y=list(res["forecast_ci"].iloc[:, 1]) + list(res["forecast_ci"].iloc[:, 0][::-1]),
            fill="toself",
            fillcolor="rgba(27,158,119,0.2)",
            line=dict(color="rgba(0,0,0,0)"),
            name="IC 80%",
            showlegend=True,
        )
    )
    p, dd, q = res["order"]
    fig.update_layout(
        title=f"SARIMA{(p, dd, q)}x{res['seasonal_order']} — pronóstico a 24 h frente a la referencia",
        xaxis_title=None,
        yaxis_title="% Alta demora",
        template="plotly_dark",
        height=450,
    )
    st.plotly_chart(fig, width="stretch")
    n_total = len(res["series"])
    n_con_dato = int(res["series"].notna().sum())
    iteraciones = res["iterations"]
    estado = "convergió" if res["converged"] else "**NO convergió**"
    detalle = f" en {iteraciones} iteraciones" if iteraciones else ""
    st.caption(
        f"Modelado sobre {n_total:,} horas de calendario, de las cuales {n_con_dato:,} tienen dato "
        f"({n_con_dato / n_total:.0%}); el resto son huecos de la recolección que el modelo trata como datos "
        f"faltantes, sin rellenarlos. El ajuste {estado}{detalle}."
    )
    if not res["converged"]:
        st.warning("El optimizador no convergió en este ajuste: tómese el pronóstico como orientativo.")
    st.info(forecasting.VALIDATION_NOTE)


# --------------------------------------------------------------------------
# Clustering de corredores
# --------------------------------------------------------------------------


@st.cache_data(show_spinner="Ejecutando k-means sobre corredores...")
def _fit_clustering(d: pd.DataFrame, k: int):
    agg = (
        d.assign(alta=(d["mobility_level"] == "Alta demora").astype(int))
        .groupby(["origin", "destination"])
        .agg(
            distancia_media=("distance_km", "mean"),
            duracion_media=("travel_time_min", "mean"),
            velocidad_media=("average_speed_kmh", "mean"),
            pct_alta_demora=("alta", "mean"),
            n=("alta", "size"),
        )
        .reset_index()
    )
    agg["ruta"] = agg["origin"] + " → " + agg["destination"]

    feats = ["distancia_media", "duracion_media", "velocidad_media", "pct_alta_demora"]
    Xs = StandardScaler().fit_transform(agg[feats])

    wss = []
    max_k = min(10, len(agg) - 1)
    for kk in range(1, max_k + 1):
        wss.append(KMeans(n_clusters=kk, n_init=10, random_state=42).fit(Xs).inertia_)

    km = KMeans(n_clusters=k, n_init=25, random_state=42).fit(Xs)
    agg["cluster"] = km.labels_.astype(str)

    coords = PCA(n_components=2, random_state=42).fit_transform(Xs)
    agg["pc1"], agg["pc2"] = coords[:, 0], coords[:, 1]

    return {"agg": agg, "wss": wss, "max_k": max_k}


def render_clustering(d: pd.DataFrame) -> None:
    st.subheader("🧭 Clustering de corredores urbanos")

    k = st.slider("Número de clusters (k)", 2, 6, 3, key="pm_cluster_k")
    res = _fit_clustering(d, k)
    agg = res["agg"]

    col_elbow, col_scatter = st.columns(2)

    with col_elbow:
        fig = go.Figure(go.Scatter(x=list(range(1, res["max_k"] + 1)), y=res["wss"], mode="lines+markers"))
        fig.add_vline(x=k, line_dash="dash", line_color="#d95f02")
        fig.update_layout(
            title="Método del codo", xaxis_title="k", yaxis_title="WSS", template="plotly_dark", height=380
        )
        st.plotly_chart(fig, width="stretch")

    with col_scatter:
        fig = go.Figure()
        for c in sorted(agg["cluster"].unique()):
            sub = agg[agg["cluster"] == c]
            fig.add_trace(
                go.Scatter(
                    x=sub["pc1"],
                    y=sub["pc2"],
                    mode="markers+text",
                    text=sub["ruta"],
                    textposition="top center",
                    marker=dict(size=14),
                    name=f"Cluster {c}",
                )
            )
        fig.update_layout(
            title="Corredores en espacio PCA (2D)",
            xaxis_title="PC1",
            yaxis_title="PC2",
            template="plotly_dark",
            height=380,
        )
        st.plotly_chart(fig, width="stretch")

    display_cols = ["ruta", "distancia_media", "duracion_media", "pct_alta_demora", "n", "cluster"]
    st.dataframe(
        agg[display_cols]
        .sort_values("cluster")
        .style.format({"distancia_media": "{:.2f}", "duracion_media": "{:.1f}", "pct_alta_demora": "{:.1%}"}),
        width="stretch",
        hide_index=True,
    )


# --------------------------------------------------------------------------
# Entrada principal del tab
# --------------------------------------------------------------------------

# Secciones que se entrenan bajo demanda: clave -> (nombre, qué hace, coste aproximado).
SECCIONES = {
    "clf": (
        "Clasificación",
        "regresión logística + Random Forest (300 árboles, búsqueda en rejilla con validación cruzada)",
        "~25 s con 16 CPUs",
    ),
    "reg": ("Regresión", "regresión lineal + Gradient Boosting", "~20 s con 16 CPUs"),
    "temporal": ("Forecast temporal", "SARIMA con diferenciación estacional de 24 h", "unos segundos"),
    "cluster": ("Clustering", "k-means sobre los corredores", "~3 s"),
}


def _flag(key: str) -> str:
    return f"pm_run_{key}"


def _solicitado(key: str) -> bool:
    """True si el usuario ya pidió esta sección en esta sesión. Si no, muestra el botón que la
    pide y devuelve False, para que NO se entrene nada hasta entonces."""
    if st.session_state.get(_flag(key)):
        return True
    nombre, detalle, coste = SECCIONES[key]
    st.caption(f"{detalle}. Coste aproximado: {coste}.")
    if st.button(f"▶ Entrenar y mostrar: {nombre}", key=f"pm_btn_{key}", type="primary"):
        st.session_state[_flag(key)] = True
        st.rerun()
    return False


def render() -> None:
    st.markdown("## 🧠 Modelado Predictivo")
    st.caption(
        "Reproduce en vivo, sobre la base de datos actual, la metodología validada en "
        f"`{RMD_PATH}` (clasificación, regresión, forecasting horario y clustering). "
        "Las cifras pueden variar levemente frente al informe .Rmd congelado: aquí se "
        "usa scikit-learn/statsmodels sobre datos que siguen creciendo; la metodología "
        "(features, exclusión de fuga de datos, partición train/test) es la misma."
    )

    df_raw = load_modeling_data()
    if df_raw.empty:
        st.warning("No hay datos disponibles en la base de datos para modelar.")
        return

    d = _engineer_features(df_raw)

    n_days = (d["timestamp"].max() - d["timestamp"].min()).days
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros modelados", f"{len(d):,}")
    c2.metric("Corredores", d[["origin", "destination"]].drop_duplicates().shape[0])
    c3.metric("Rango temporal", f"{n_days} días")
    c4.metric("% Alta demora", f"{(d['mobility_level'] == 'Alta demora').mean():.1%}")

    n_sin_clima = len(d) - len(_complete_cases(d))
    if n_sin_clima:
        st.caption(
            f"ℹ️ {n_sin_clima:,} registros sin dato de clima (OpenWeather no respondió en ese ciclo) "
            "se excluyen de **Clasificación** y **Regresión**, que usan el clima; "
            "el forecast temporal y el clustering sí los conservan."
        )

    # Streamlit ejecuta el contenido de TODAS las pestañas en cada rerun (no solo la visible).
    # Antes los cuatro modelos se entrenaban de golpe al abrir Analyst: con la base real
    # (78,5 mil filas) ~75 s en un equipo de 16 CPUs y ~9 min dentro del contenedor del
    # dashboard (1 CPU, 1 GiB, donde además rozaba el límite de memoria). Ahora cada modelo
    # se entrena cuando se pide; el resultado queda en caché y, a partir de ahí, es inmediato.
    st.info(
        "Los modelos **no se entrenan al abrir esta pantalla**: pulsa el botón de cada pestaña "
        "(o el de abajo para los cuatro). Con los datos actuales tarda del orden de **1 minuto en un "
        "equipo con varios núcleos y varios minutos con 1 CPU** (p. ej. dentro de Docker); después "
        "queda en caché."
    )
    if st.button("▶ Entrenar y mostrar los cuatro modelos", key="pm_btn_all"):
        for key in SECCIONES:
            st.session_state[_flag(key)] = True
        st.rerun()

    tab_clf, tab_reg, tab_temporal, tab_cluster = st.tabs(
        [
            "Clasificación",
            "Regresión",
            "Forecast temporal",
            "Clustering",
        ]
    )

    with tab_clf:
        if _solicitado("clf"):
            render_classification(d)
    with tab_reg:
        if _solicitado("reg"):
            render_regression(d)
    with tab_temporal:
        if _solicitado("temporal"):
            render_temporal(d)
    with tab_cluster:
        if _solicitado("cluster"):
            render_clustering(d)


if __name__ == "__main__":
    st.set_page_config(page_title="Modelado Predictivo", layout="wide")
    render()
