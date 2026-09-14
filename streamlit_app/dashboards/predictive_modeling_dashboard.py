"""Modelado Predictivo reproducido de forma interactiva.

Reproduce sobre los datos EN VIVO de la base de datos (misma tabla y esquema
que el CSV exportado y usado en notebooks/Asignatura7_Modelado_Predictivo.Rmd)
la misma metodología validada en ese notebook:

    EDA -> preprocesamiento -> clasificación (mobility_level) ->
    regresión (travel_time_min) -> forecasting horario -> clustering de corredores

Las cifras exactas pueden diferir levemente de las del .Rmd (el dataset vivo
sigue creciendo y aquí se usa scikit-learn en vez de caret/randomForest/xgboost),
pero la metodología -features, exclusión de fuga de datos, división train/test,
umbral de 20 min- es la misma, para que el resultado sea trazable frente al
entregable académico.
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
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.tree import plot_tree

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.database import RouteDatabase  # noqa: E402

DATE_CUTOFF = "2026-08-01"  # excluye las pruebas iniciales del pipeline (mayo 2026)
NUM_COLS = [
    "distance_km", "origin_temperature", "origin_humidity",
    "destination_temperature", "destination_humidity",
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
    d["origin_weather_grp"] = d["origin_weather"].map(WEATHER_GROUPS).fillna("lluvia")
    d["destination_weather_grp"] = d["destination_weather"].map(WEATHER_GROUPS).fillna("lluvia")
    return d


def _design_matrix(d: pd.DataFrame) -> pd.DataFrame:
    """One-hot encoding (fullRank, como dummyVars en R) + variables numéricas/cíclicas."""
    cat_cols = ["origin", "destination", "data_source", "origin_weather_grp", "destination_weather_grp"]
    other_cols = ["hora_sin", "hora_cos", "dia_semana", "es_finde"]
    X = pd.get_dummies(d[cat_cols + NUM_COLS + other_cols], columns=cat_cols, drop_first=True)
    return X


# --------------------------------------------------------------------------
# Clasificación: mobility_level
# --------------------------------------------------------------------------

@st.cache_data(show_spinner="Entrenando clasificador (regresión logística + Random Forest)...")
def _fit_classification(d: pd.DataFrame):
    X = _design_matrix(d)
    y = (d["mobility_level"] == "Alta demora").astype(int).values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    scaler = StandardScaler()
    X_train_s, X_test_s = X_train.copy(), X_test.copy()
    X_train_s[NUM_COLS] = scaler.fit_transform(X_train[NUM_COLS])
    X_test_s[NUM_COLS] = scaler.transform(X_test[NUM_COLS])

    logit = LogisticRegression(max_iter=2000)
    logit.fit(X_train_s, y_train)
    prob_logit = logit.predict_proba(X_test_s)[:, 1]

    rf = RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1)
    grid = GridSearchCV(
        rf, {"max_features": ["sqrt", "log2", 0.3, 0.5]},
        scoring="roc_auc", cv=StratifiedKFold(5, shuffle=True, random_state=42), n_jobs=-1,
    )
    grid.fit(X_train_s, y_train)
    rf_best = grid.best_estimator_
    prob_rf = rf_best.predict_proba(X_test_s)[:, 1]

    importances = pd.Series(rf_best.feature_importances_, index=X.columns).sort_values(ascending=False)

    return {
        "y_test": y_test, "prob_logit": prob_logit, "prob_rf": prob_rf,
        "best_max_features": grid.best_params_["max_features"],
        "cv_auc": grid.best_score_, "importances": importances,
        "n_train": len(X_train), "n_test": len(X_test),
        "model": rf_best, "feature_names": list(X.columns),
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
    c3.metric("AUC — RF (CV 5-fold)", f"{res['cv_auc']:.3f}", help=f"max_features óptimo: {res['best_max_features']}")

    n_alta = int(y_test.sum())
    n_total = len(y_test)
    st.info(
        f"Test: {res['n_train']:,} train / {res['n_test']:,} test · "
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
        fig.update_layout(title="Curva ROC", xaxis_title="1 - Especificidad", yaxis_title="Sensibilidad",
                           template="plotly_dark", height=420)
        st.plotly_chart(fig, width="stretch")

    with col_imp:
        top = res["importances"].head(12).sort_values()
        fig = go.Figure(go.Bar(x=top.values, y=top.index, orientation="h", marker_color="#2c7fb8"))
        fig.update_layout(title="Importancia de variables — Random Forest", template="plotly_dark", height=420)
        st.plotly_chart(fig, width="stretch")

    with st.expander("Matriz de confusión — Random Forest"):
        pred_rf = (res["prob_rf"] >= 0.5).astype(int)
        cm = confusion_matrix(y_test, pred_rf, labels=[0, 1])
        cm_df = pd.DataFrame(cm, index=["Real: Movilidad normal", "Real: Alta demora"],
                              columns=["Pred: Movilidad normal", "Pred: Alta demora"])
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
            "Profundidad a mostrar", 2, 5, 3, key="pm_tree_depth",
            help="Solo limita lo que se dibuja; el árbol entrenado internamente es más profundo.",
        )
        fig_tree = _plot_tree_figure(res["model"], res["feature_names"], max_depth_view)
        st.pyplot(fig_tree)


# --------------------------------------------------------------------------
# Regresión: travel_time_min
# --------------------------------------------------------------------------

@st.cache_data(show_spinner="Entrenando regresores (lineal + Gradient Boosting)...")
def _fit_regression(d: pd.DataFrame):
    X = _design_matrix(d)
    y = d["travel_time_min"].values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

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
        "y_test": y_test, "pred_lm": pred_lm, "pred_gbr": pred_gbr,
        "metrics_lm": metrics(pred_lm), "metrics_gbr": metrics(pred_gbr),
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
        fig = go.Figure(go.Scatter(
            x=res["y_test"], y=res["pred_gbr"], mode="markers",
            marker=dict(color="#2c7fb8", opacity=0.25, size=5), name="Predicciones",
        ))
        lims = [float(min(res["y_test"])), float(max(res["y_test"]))]
        fig.add_trace(go.Scatter(x=lims, y=lims, mode="lines", line=dict(color="red", dash="dash"), name="Ideal"))
        fig.update_layout(title="Gradient Boosting: real vs. predicho", xaxis_title="Real (min)",
                           yaxis_title="Predicho (min)", template="plotly_dark", height=420)
        st.plotly_chart(fig, width="stretch")

    with col_imp:
        top = res["importances"].head(12).sort_values()
        fig = go.Figure(go.Bar(x=top.values, y=top.index, orientation="h", marker_color="#d95f02"))
        fig.update_layout(title="Importancia de variables — Gradient Boosting", template="plotly_dark", height=420)
        st.plotly_chart(fig, width="stretch")


# --------------------------------------------------------------------------
# Forecasting horario (extensión temporal)
# --------------------------------------------------------------------------

@st.cache_data(show_spinner="Ajustando el modelo de series temporales...")
def _fit_temporal(d: pd.DataFrame, max_gap_hours: int = 3):
    from statsmodels.tsa.arima.model import ARIMA

    s = (
        d.assign(alta=(d["mobility_level"] == "Alta demora").astype(int))
        .set_index("timestamp")["alta"]
        .resample("1h").mean()
    )

    # A diferencia del fill(down) del .Rmd (que arrastra el valor plano sobre
    # huecos de varios días), aquí se identifica el bloque contiguo más
    # reciente sin huecos > max_gap_hours y se modela solo ese tramo, evitando
    # el artefacto de un tramo plano artificial en la serie.
    gap = s.index.to_series().diff().dt.total_seconds() / 3600
    block_id = (gap > max_gap_hours).cumsum()
    last_block = block_id.iloc[-1]
    s_block = s[block_id == last_block].interpolate(limit=max_gap_hours)

    order_candidates = [(1, 0, 0), (2, 1, 1), (1, 1, 1), (2, 0, 2)]
    best_aic, best_fit, best_order = np.inf, None, None
    for order in order_candidates:
        try:
            fit = ARIMA(s_block, order=order, seasonal_order=(1, 0, 1, 24)).fit()
            if fit.aic < best_aic:
                best_aic, best_fit, best_order = fit.aic, fit, order
        except Exception:
            continue

    forecast = best_fit.get_forecast(steps=24)
    fc_mean = forecast.predicted_mean
    fc_ci = forecast.conf_int(alpha=0.2)

    return {
        "series": s_block, "order": best_order, "aic": best_aic,
        "forecast_mean": fc_mean, "forecast_ci": fc_ci,
        "gap_excluded_hours": int((s.index[-1] - s_block.index[0]).total_seconds() / 3600) - len(s_block) + 1,
    }


def render_temporal(d: pd.DataFrame) -> None:
    st.subheader("📈 Forecasting horario de congestión (extensión)")
    st.caption(
        "Serie horaria de % 'Alta demora'. Se ajusta ARIMA estacional (24h) sobre el bloque "
        "continuo más reciente, sin arrastrar huecos largos de captura del scheduler."
    )

    res = _fit_temporal(d)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=res["series"].index, y=res["series"].values, mode="lines",
                              name="Observado", line=dict(color="#2c7fb8")))
    fig.add_trace(go.Scatter(x=res["forecast_mean"].index, y=res["forecast_mean"].values, mode="lines",
                              name="Forecast 24h", line=dict(color="#1b9e77")))
    fig.add_trace(go.Scatter(
        x=list(res["forecast_ci"].index) + list(res["forecast_ci"].index[::-1]),
        y=list(res["forecast_ci"].iloc[:, 1]) + list(res["forecast_ci"].iloc[:, 0][::-1]),
        fill="toself", fillcolor="rgba(27,158,119,0.2)", line=dict(color="rgba(0,0,0,0)"),
        name="IC 80%", showlegend=True,
    ))
    fig.update_layout(title=f"ARIMA{res['order']} estacional (24h) — AIC={res['aic']:.1f}",
                       xaxis_title=None, yaxis_title="% Alta demora", template="plotly_dark", height=450)
    st.plotly_chart(fig, width="stretch")
    st.caption(f"Modelado sobre {len(res['series'])} horas continuas más recientes (ver nota sobre huecos en el .Rmd).")


# --------------------------------------------------------------------------
# Clustering de corredores
# --------------------------------------------------------------------------

@st.cache_data(show_spinner="Ejecutando k-means sobre corredores...")
def _fit_clustering(d: pd.DataFrame, k: int):
    agg = (
        d.assign(alta=(d["mobility_level"] == "Alta demora").astype(int))
        .groupby(["origin", "destination"])
        .agg(distancia_media=("distance_km", "mean"),
             duracion_media=("travel_time_min", "mean"),
             velocidad_media=("average_speed_kmh", "mean"),
             pct_alta_demora=("alta", "mean"),
             n=("alta", "size"))
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
        fig.update_layout(title="Método del codo", xaxis_title="k", yaxis_title="WSS",
                           template="plotly_dark", height=380)
        st.plotly_chart(fig, width="stretch")

    with col_scatter:
        fig = go.Figure()
        for c in sorted(agg["cluster"].unique()):
            sub = agg[agg["cluster"] == c]
            fig.add_trace(go.Scatter(
                x=sub["pc1"], y=sub["pc2"], mode="markers+text", text=sub["ruta"],
                textposition="top center", marker=dict(size=14), name=f"Cluster {c}",
            ))
        fig.update_layout(title="Corredores en espacio PCA (2D)", xaxis_title="PC1", yaxis_title="PC2",
                           template="plotly_dark", height=380)
        st.plotly_chart(fig, width="stretch")

    display_cols = ["ruta", "distancia_media", "duracion_media", "pct_alta_demora", "n", "cluster"]
    st.dataframe(
        agg[display_cols].sort_values("cluster").style.format(
            {"distancia_media": "{:.2f}", "duracion_media": "{:.1f}", "pct_alta_demora": "{:.1%}"}
        ),
        width="stretch", hide_index=True,
    )


# --------------------------------------------------------------------------
# Entrada principal del tab
# --------------------------------------------------------------------------

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

    tab_clf, tab_reg, tab_temporal, tab_cluster = st.tabs([
        "Clasificación", "Regresión", "Forecast temporal", "Clustering",
    ])

    with tab_clf:
        render_classification(d)
    with tab_reg:
        render_regression(d)
    with tab_temporal:
        render_temporal(d)
    with tab_cluster:
        render_clustering(d)


if __name__ == "__main__":
    st.set_page_config(page_title="Modelado Predictivo", layout="wide")
    render()
