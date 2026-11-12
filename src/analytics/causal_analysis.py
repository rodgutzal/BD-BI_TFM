"""Adjusted-association analysis: goes beyond raw correlation, but is NOT proof of causality.

The data are OBSERVATIONAL (nobody assigned the weather at random). Every estimate here is an association, adjusted only
for the confounders that are measured and listed in the result. What is NOT controlled (rain, events, roadworks...) can
still explain it. The matching estimator is a real propensity-score matching: see
CausalAnalysis.propensity_score_matching.
"""

import warnings
from typing import List, Optional

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression

warnings.filterwarnings("ignore")

DEFAULT_CALIPER_SD = 0.2  # caliper = 0.2 desviaciones típicas del logit del propensity score (convención habitual)
N_BOOTSTRAP = 300
SMD_THRESHOLD = 0.1  # |diferencia media estandarizada| por debajo de la cual el equilibrio es bueno
SMD_ACCEPTABLE = 0.25  # por debajo de este valor, aceptable (Rubin); por encima, pobre
MAX_CATEGORIES_AS_NUMERIC = 30  # una variable numérica con ≤ 30 valores distintos (hora, día) se trata como categórica


def _smd(treated: np.ndarray, control: np.ndarray, control_weights: Optional[np.ndarray]) -> np.ndarray:
    """Diferencia media estandarizada de cada columna: (media tratada − media control) / √((var_t + var_c) / 2).

    `control_weights` pondera a los controles (los que se usan varias veces al emparejar con reemplazo). Una columna
    sin varianza en ambos grupos da 0."""
    mt, vt = treated.mean(axis=0), treated.var(axis=0)
    if control_weights is None:
        mc, vc = control.mean(axis=0), control.var(axis=0)
    else:
        mc = control_weights @ control
        vc = control_weights @ (control - mc) ** 2
    denom = np.sqrt((vt + vc) / 2)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(denom > 0, (mt - mc) / denom, 0.0)


def _nearest_control(treated_logit: np.ndarray, control_logit_sorted: np.ndarray) -> np.ndarray:
    """Posición, dentro de `control_logit_sorted` (ordenado de menor a mayor), del control más cercano a cada tratada:
    el mayor-igual y el menor más próximos, y de los dos el que queda a menos distancia."""
    pos = np.searchsorted(control_logit_sorted, treated_logit)
    izq = np.clip(pos - 1, 0, len(control_logit_sorted) - 1)
    der = np.clip(pos, 0, len(control_logit_sorted) - 1)
    elige_der = np.abs(control_logit_sorted[der] - treated_logit) < np.abs(control_logit_sorted[izq] - treated_logit)
    return np.where(elige_der, der, izq)


def _matched_smd(Xv: np.ndarray, treated_rows: np.ndarray, control_matches: np.ndarray) -> np.ndarray:
    """SMD después de emparejar: tratadas emparejadas frente a los controles ELEGIDOS, ponderando cada control por las
    veces que se usó (el emparejamiento es con reemplazo: un mismo control puede servir a varias tratadas)."""
    usos = np.bincount(control_matches, minlength=len(Xv)).astype(float)
    usados = np.where(usos > 0)[0]
    return _smd(Xv[treated_rows], Xv[usados], usos[usados] / usos[usados].sum())


class CausalAnalysis:
    """
    Adjusted-association analysis using several approaches.

    Key insight: Correlation ≠ Causation, and adjusting for measured confounders does not make it so.
    This module asks "is X associated with Y once comparable situations are compared?", not "does X CAUSE Y?".
    """

    def __init__(self, df: pd.DataFrame):
        """Initialize with dataframe."""
        self.df = df.copy()
        if "timestamp" in self.df.columns:
            self.df["timestamp"] = pd.to_datetime(self.df["timestamp"], utc=True)
            self.df = self.df.sort_values("timestamp")

    def _adjustment_matrix(self, df: pd.DataFrame, covariates: Optional[List[str]] = None) -> Optional[pd.DataFrame]:
        """Matriz de covariables PRE-tratamiento para el propensity score (variables categóricas en indicadores).

        Por defecto, lo que se puede derivar de los datos: hora del día, día de la semana y semana del año (esta última
        recoge la tendencia lenta: el tiempo y el tráfico cambian a lo largo de los meses), ruta y fuente de datos.
        NUNCA se ajusta por variables que son CONSECUENCIA del tráfico (velocidad media, retraso, nivel de movilidad):
        condicionar por una consecuencia del resultado sesga la estimación."""
        if covariates is None:
            partes = {}
            if "timestamp" in df.columns:
                ts = df["timestamp"]
                partes["hora"] = ts.dt.hour
                partes["dia_semana"] = ts.dt.dayofweek
                partes["semana"] = ts.dt.strftime("%G-%V")
            if {"origin", "destination"} <= set(df.columns):
                partes["ruta"] = df["origin"].astype(str) + ">" + df["destination"].astype(str)
            if "data_source" in df.columns:
                partes["fuente"] = df["data_source"].astype(str)
        else:
            partes = {c: df[c] for c in covariates}
        if not partes:
            return None
        columnas = []
        for nombre, serie in partes.items():
            es_numerica = pd.api.types.is_numeric_dtype(serie) and serie.nunique() > MAX_CATEGORIES_AS_NUMERIC
            if es_numerica:
                desv = serie.std()
                columnas.append(
                    ((serie - serie.mean()) / (desv if desv and desv > 0 else 1.0)).fillna(0).rename(nombre)
                )
            else:
                columnas.append(pd.get_dummies(serie.astype(str), prefix=nombre, drop_first=True, dtype=float))
        X = pd.concat(columnas, axis=1)
        return X.loc[:, X.std() > 0]

    @staticmethod
    def _assign_treatment(df: pd.DataFrame, weather_col: str, treatment: str):
        """(tratadas, descripción), o un dict con el error. Ver propensity_score_matching para el significado de
        `treatment`."""
        if treatment not in ("above_typical", "above_median"):
            return {"error": f"Unknown treatment {treatment!r}: use 'above_typical' or 'above_median'"}
        if treatment == "above_typical" and "timestamp" in df.columns:
            ts = df["timestamp"]
            referencia = df.groupby([ts.dt.hour, ts.dt.strftime("%G-%V")])[weather_col].transform("median")
            treated = (df[weather_col] > referencia).to_numpy()
            descripcion = f"{weather_col} above the median of its own hour and week"
        else:
            treated = (df[weather_col] > df[weather_col].median()).to_numpy()
            descripcion = f"{weather_col} above its median ({df[weather_col].median():.1f})"
        if treated.all() or not treated.any():
            return {"error": "No variation in treatment"}
        return treated, descripcion

    @staticmethod
    def _stratum_key(df: pd.DataFrame, columns: List[str]) -> np.ndarray:
        """Clave de estrato de cada fila: valores de `columns` unidos. Además de columnas del DataFrame valen "hour" y
        "week", derivadas del timestamp. Sin columnas, un único estrato."""
        derivadas = (
            {"hour": df["timestamp"].dt.hour, "week": df["timestamp"].dt.strftime("%G-%V")}
            if "timestamp" in df.columns
            else {}
        )
        desconocidas = [c for c in columns if c not in derivadas and c not in df.columns]
        if desconocidas:
            raise ValueError(f"Unknown stratification column(s): {desconocidas}")
        partes = [derivadas[c] if c in derivadas else df[c] for c in columns]
        if not partes:
            return np.zeros(len(df), dtype=object)
        return pd.concat(partes, axis=1).astype(str).agg("|".join, axis=1).to_numpy()

    @staticmethod
    def _cluster_bootstrap(diff: np.ndarray, df: pd.DataFrame, rows: np.ndarray, n_boot: int, seed: int):
        """IC 95 % de la media de `diff` por bootstrap de DÍAS completos (las mediciones de un mismo día no son
        independientes). `rows` son las filas de `df` a las que corresponde cada diferencia. No incluye la
        incertidumbre de estimar los controles."""
        grupos = df["timestamp"].dt.date.to_numpy()[rows] if "timestamp" in df.columns else np.arange(len(rows))
        _, inv = np.unique(grupos, return_inverse=True)
        suma = np.bincount(inv, weights=diff)
        cuenta = np.bincount(inv).astype(float)
        rng = np.random.default_rng(seed)
        medias = np.empty(n_boot)
        for b in range(n_boot):
            s = rng.integers(0, len(suma), len(suma))
            medias[b] = suma[s].sum() / cuenta[s].sum()
        return float(np.quantile(medias, 0.025)), float(np.quantile(medias, 0.975))

    def stratified_adjusted(
        self,
        weather_col: str = "origin_temperature",
        strata: Optional[List[str]] = None,
        n_boot: int = N_BOOTSTRAP,
        seed: int = 0,
        treatment: str = "above_typical",
    ) -> dict:
        """Estimación ajustada por ESTRATIFICACIÓN EXACTA: cada medición con temperatura alta se compara con la media de
        las de temperatura baja de su MISMO estrato (por defecto ruta, fuente de datos, hora y semana).

        Es el estimador principal del análisis del tiempo. Equilibra por construcción las covariables que definen los
        estratos y no depende de un modelo de propensity score, que aquí es casi constante (el tratamiento «más calor de
        lo habitual» ya está equilibrado por hora y semana) y hace que el emparejamiento por puntuación sea casi
        aleatorio y pueda DESEQUILIBRAR en vez de equilibrar (King y Nielsen, 2019).

        ATT = media, sobre las tratadas con control en su estrato, de (resultado − media de los controles del estrato).
        Las tratadas sin controles en su estrato (falta de soporte común) se descartan y se cuentan. El intervalo es por
        bootstrap de días completos. Es una asociación ajustada por lo medido, no prueba de causalidad."""
        if weather_col not in self.df.columns or "travel_time_min" not in self.df.columns:
            return {"error": f"Missing columns: {weather_col} or travel_time_min"}
        df = self.df.dropna(subset=[weather_col, "travel_time_min"]).reset_index(drop=True)
        if len(df) < 30:
            return {"error": "Insufficient data"}
        asignacion = self._assign_treatment(df, weather_col, treatment)
        if isinstance(asignacion, dict):
            return asignacion
        treated, descripcion = asignacion
        if strata is None:
            strata = [c for c in ("origin", "destination", "data_source") if c in df.columns]
            if "timestamp" in df.columns:
                strata += ["hour", "week"]
        if not strata:
            return {"error": "No stratification columns: needs a timestamp, route or source column, or `strata`"}
        try:
            clave = pd.Series(self._stratum_key(df, strata))
        except ValueError as e:
            return {"error": str(e)}
        y = df["travel_time_min"].to_numpy(dtype=float)
        media_control = pd.Series(y[~treated]).groupby(clave[~treated].to_numpy()).mean()
        t_idx = np.where(treated)[0]
        mu = clave.iloc[t_idx].map(media_control).to_numpy(dtype=float)
        con_control = ~np.isnan(mu)
        if not con_control.any():
            return {"error": "No treated unit has controls in its stratum (no common support)"}
        t_kept = t_idx[con_control]
        diff = y[t_kept] - mu[con_control]
        att = float(diff.mean())
        ic = self._cluster_bootstrap(diff, df, t_kept, n_boot, seed)
        naive = float(y[treated].mean() - y[~treated].mean())
        return {
            "status": "calculated",
            "method": "exact stratification (treated vs mean of controls in the same stratum)",
            "treatment": descripcion,
            "strata_on": list(strata),
            "att": att,
            "ci_95": ic,
            "ci_excludes_zero": bool(ic[0] > 0 or ic[1] < 0),
            "naive_difference": naive,
            "n_treated": int(treated.sum()),
            "n_used": int(len(t_kept)),
            "share_used": float(len(t_kept) / treated.sum()),
            "n_strata_used": int(clave.iloc[t_kept].nunique()),
            "interpretation": (
                f"Compared with measurements in the same {', '.join(strata)}, higher temperature is associated with "
                f"{att:+.2f} min of travel time (95% CI {ic[0]:+.2f} to {ic[1]:+.2f}); the unadjusted difference is "
                f"{naive:+.2f}. This is an association, not proof of causality."
            ),
        }

    def propensity_score_matching(
        self,
        weather_col: str = "origin_temperature",
        covariates: Optional[List[str]] = None,
        caliper_sd: float = DEFAULT_CALIPER_SD,
        n_boot: int = N_BOOTSTRAP,
        seed: int = 0,
        treatment: str = "above_typical",
        exact: Optional[List[str]] = None,
    ) -> dict:
        """Propensity-score matching real del efecto asociado a una temperatura alta.

        `treatment`:
          - "above_typical" (por defecto): temperatura por encima de la MEDIANA DE SU PROPIA hora y semana, es decir,
            «más calor de lo habitual para esa hora y esa época». Es lo que permite comparar: la hora y la estación ya no
            determinan el tratamiento, así que hay mediciones comparables con y sin él.
          - "above_median": por encima de la mediana global. Casi todo el calor cae de día y en verano, así que el
            tratamiento queda casi determinado por la hora y la semana (falta de solapamiento) y el emparejamiento no
            consigue equilibrar los grupos; se conserva para poder demostrarlo (`balance.balanced` sale False).

        1. Propensity score: probabilidad de «temperatura alta» dada la hora, el día de la semana, la semana, la ruta y la
           fuente (regresión logística). Se compara cada medición con temperatura alta con una medición comparable con
           temperatura baja, no con el promedio de todas.
        2. Emparejamiento: cada tratada con el control más cercano en el logit del propensity score (con reemplazo) dentro
           de un caliper de `caliper_sd` desviaciones típicas y EXACTO en las columnas de `exact` (por defecto ruta y fuente
           de datos, si existen; también valen "hour" y "week", derivadas del timestamp); las tratadas sin pareja cercana
           (falta de soporte común) se descartan y se cuentan. Exigir exacto más columnas (hora, semana) deja menos
           parejas y, medido con los datos reales, desequilibra otras covariables: ver tools/analyze_weather_effect.py.
        3. Efecto: media de (resultado de la tratada − resultado de su control) sobre las parejas (ATT).
        4. Intervalo de confianza: bootstrap por DÍAS (se remuestrean días completos, no mediciones sueltas, porque las
           mediciones de un mismo día no son independientes). No incluye la incertidumbre de estimar el propensity score.
        5. Equilibrio: diferencia media estandarizada (SMD) de cada covariable antes y después de emparejar. Regla de la
           literatura: máx. |SMD| < 0,1 equilibrio bueno; < 0,25 aceptable (Rubin); más, pobre: el ajuste no ha funcionado
           y el resultado no es fiable. Con muchas categorías, las de pocas mediciones inflan el máximo por ruido, por eso
           también se informa la media.

        Es una ASOCIACIÓN ajustada por lo medido: no controla lo que no está en los datos (lluvia, eventos, obras...).
        """
        if weather_col not in self.df.columns or "travel_time_min" not in self.df.columns:
            return {"error": f"Missing columns: {weather_col} or travel_time_min"}
        df = self.df.dropna(subset=[weather_col, "travel_time_min"]).reset_index(drop=True)
        if len(df) < 30:
            return {"error": "Insufficient data"}
        asignacion = self._assign_treatment(df, weather_col, treatment)
        if isinstance(asignacion, dict):
            return asignacion
        treated, descripcion = asignacion
        X = self._adjustment_matrix(df, covariates)
        if X is None or X.shape[1] == 0:
            return {"error": "No adjustment covariates: needs a timestamp column or `covariates`"}

        ps = LogisticRegression(max_iter=2000, random_state=42).fit(X, treated).predict_proba(X)[:, 1]
        logit = np.log(np.clip(ps, 1e-6, 1 - 1e-6) / (1 - np.clip(ps, 1e-6, 1 - 1e-6)))
        caliper = caliper_sd * logit.std()

        # Emparejamiento EXACTO dentro de ruta y fuente (por defecto) y por propensity score dentro de cada grupo. Cuando
        # el propensity score casi no varía (aquí ronda 0,44 para todas las mediciones) el caliper no obliga a que el
        # control sea de la misma fuente o ruta, y esas covariables quedaban desequilibradas.
        if exact is None and covariates is None:
            exact = [c for c in ("origin", "destination", "data_source") if c in df.columns]
        exact = list(exact or [])
        try:
            clave = self._stratum_key(df, exact)
        except ValueError as e:
            return {"error": str(e)}

        y = df["travel_time_min"].to_numpy(dtype=float)
        t_idx, c_idx = np.where(treated)[0], np.where(~treated)[0]
        trozos_t, trozos_c = [], []
        for grupo in np.unique(clave):
            en_grupo = clave == grupo
            t_g, c_g = np.where(treated & en_grupo)[0], np.where(~treated & en_grupo)[0]
            if len(t_g) == 0 or len(c_g) == 0:
                continue
            orden = np.argsort(logit[c_g])
            c_sorted, c_logit = c_g[orden], logit[c_g][orden]
            mejor = _nearest_control(logit[t_g], c_logit)
            dentro_g = np.abs(c_logit[mejor] - logit[t_g]) <= caliper
            trozos_t.append(t_g[dentro_g])
            trozos_c.append(c_sorted[mejor[dentro_g]])
        t_kept = np.concatenate(trozos_t) if trozos_t else np.array([], dtype=int)
        c_match = np.concatenate(trozos_c) if trozos_c else np.array([], dtype=int)
        if len(t_kept) == 0:
            return {"error": "No treated unit has a comparable control (no common support)"}
        diff = y[t_kept] - y[c_match]
        att = float(diff.mean())

        ic = self._cluster_bootstrap(diff, df, t_kept, n_boot, seed)

        # Equilibrio de covariables antes y después de emparejar.
        Xv = X.to_numpy(dtype=float)
        smd_antes = _smd(Xv[t_idx], Xv[c_idx], None)
        smd_despues = _matched_smd(Xv, t_kept, c_match)
        peor = np.argsort(-np.abs(smd_despues))[:5]
        naive = float(y[t_idx].mean() - y[c_idx].mean())
        peor_smd = float(np.abs(smd_despues).max())
        calidad = "good" if peor_smd < SMD_THRESHOLD else ("acceptable" if peor_smd < SMD_ACCEPTABLE else "poor")
        equilibrado = calidad == "good"
        return {
            "status": "calculated",
            "method": "propensity_score_matching (nearest neighbour on logit, with replacement, caliper)",
            "treatment": descripcion,
            "att": att,
            "ci_95": ic,
            "ci_excludes_zero": bool(ic[0] > 0 or ic[1] < 0),
            "naive_difference": naive,
            "n_treated": int(len(t_idx)),
            "n_matched": int(len(t_kept)),
            "share_matched": float(len(t_kept) / len(t_idx)),
            "caliper": float(caliper),
            "exact_match_on": exact,
            "covariates": sorted({c.split("_")[0] for c in X.columns}) if covariates is None else list(covariates),
            "balance": {
                "max_abs_smd_before": float(np.abs(smd_antes).max()),
                "max_abs_smd_after": peor_smd,
                "mean_abs_smd_before": float(np.abs(smd_antes).mean()),
                "mean_abs_smd_after": float(np.abs(smd_despues).mean()),
                "quality": calidad,
                "balanced": equilibrado,
                "worst_after": {X.columns[i]: float(smd_despues[i]) for i in peor},
            },
            "interpretation": (
                f"Among comparable measurements (same hour, weekday, week, route and source), higher temperature is "
                f"associated with {att:+.2f} min of travel time (95% CI {ic[0]:+.2f} to {ic[1]:+.2f}); the unadjusted "
                f"difference is {naive:+.2f}. This is an association, not proof of causality."
                + {
                    "good": "",
                    "acceptable": f" Covariate balance is acceptable but not ideal (max |SMD| {peor_smd:.2f}).",
                    "poor": f" WARNING: covariates are poorly balanced after matching (max |SMD| {peor_smd:.2f}); "
                    "do not rely on this estimate.",
                }[calidad]
            ),
        }

    def weather_impact_causal(self, weather_col: str = "origin_temperature") -> dict:
        """
        Analyze the association between weather and traffic.

        Uses: raw correlation, an UNADJUSTED comparison (high vs low temperature, which confounds weather with route and
        time of day), an exact stratification (same route, source, hour and week: the main adjusted estimate) and a real
        propensity-score matching with its balance diagnostic (a cross-check; see propensity_score_matching).

        Questions answered:
        - Are longer travel times associated with high temperature?
        - How large is the difference (minutes), raw and adjusted for confounders?
        - Is it statistically significant? Is it still there after adjusting?
        """
        if weather_col not in self.df.columns or "travel_time_min" not in self.df.columns:
            return {"error": f"Missing columns: {weather_col} or travel_time_min"}

        df = self.df.dropna(subset=[weather_col, "travel_time_min"])
        if len(df) < 30:
            return {"error": "Insufficient data"}

        try:
            # 1. Correlation (baseline)
            corr, p_val = stats.pearsonr(df[weather_col], df["travel_time_min"])

            # 2. Stratification: Compare high vs low temperature groups
            median_temp = df[weather_col].median()
            high_temp_group = df[df[weather_col] > median_temp]["travel_time_min"]
            low_temp_group = df[df[weather_col] <= median_temp]["travel_time_min"]

            # T-test: Do high-temp times differ from low-temp times?
            t_stat, t_pval = stats.ttest_ind(high_temp_group, low_temp_group)
            effect_size = high_temp_group.mean() - low_temp_group.mean()

            # 3. Propensity-score matching REAL: compara con mediciones comparables (misma hora, día, semana, ruta, fuente).
            # None si no hay con qué ajustar (sin timestamp ni covariables); el motivo de otros fallos va en el dict.
            psm_effect = self.propensity_score_matching(weather_col)
            if "error" in psm_effect and psm_effect["error"].startswith("No adjustment covariates"):
                psm_effect = None
            # 4. Estratificación exacta: el estimador ajustado PRINCIPAL (el PSM queda como contraste con su diagnóstico).
            adjusted = self.stratified_adjusted(weather_col)
            if "error" in adjusted and adjusted["error"].startswith("No stratification columns"):
                adjusted = None

            return {
                "treatment": f"High temperature (>{median_temp:.1f}°C)",
                "outcome": "travel_time_min",
                "sample_size": len(df),
                "correlation": {"coefficient": float(corr), "p_value": float(p_val), "significant": p_val < 0.05},
                "stratified_analysis": {
                    "high_temp_mean": float(high_temp_group.mean()),
                    "low_temp_mean": float(low_temp_group.mean()),
                    "effect_size": float(effect_size),
                    "effect_interpretation": f"High temp is associated with ~{effect_size:.2f} min more travel (unadjusted)",
                    "t_statistic": float(t_stat),
                    "p_value": float(t_pval),
                    "significant": t_pval < 0.05,
                },
                "propensity_score_matching": psm_effect,
                "stratified_adjusted": adjusted,
                "conclusion": self._interpret_causal_effect(effect_size, t_pval),
                "adjusted_conclusion": (
                    adjusted["interpretation"] if adjusted and "interpretation" in adjusted else None
                ),
            }
        except Exception as e:
            return {"error": str(e)}

    def weather_intervention_simulation(self) -> dict:
        """Scenarios from a simple regression: 'what travel time goes with a temperature 5°C lower?'. An association
        read off a line (unadjusted for hour of day, route or season), not the effect of changing the weather."""
        if "origin_temperature" not in self.df.columns:
            return {"error": "Temperature data not available"}

        df = self.df.dropna(subset=["origin_temperature", "travel_time_min"])
        if len(df) < 30:
            return {"error": "Insufficient data"}

        try:
            # Linear regression (association; unadjusted)
            from sklearn.linear_model import LinearRegression

            X = df[["origin_temperature"]].values
            y = df["travel_time_min"].values

            model = LinearRegression()
            model.fit(X, y)
            coef = model.coef_[0]

            # Intervention scenarios
            scenarios = {}
            current_temp = df["origin_temperature"].mean()
            current_time = df["travel_time_min"].mean()

            for temp_delta in [-5, -2.5, 0, 2.5, 5]:
                new_temp = current_temp + temp_delta
                estimated_time = model.predict([[new_temp]])[0]
                time_delta = estimated_time - current_time

                scenarios[f"{temp_delta:+.1f}°C"] = {
                    "estimated_travel_time": float(estimated_time),
                    "time_change": float(time_delta),
                    "interpretation": f"{time_delta:+.1f} min compared to baseline",
                }

            return {
                "baseline_temperature": float(current_temp),
                "baseline_travel_time": float(current_time),
                "temperature_effect": float(coef),
                "effect_unit": "minutes per °C",
                "scenarios": scenarios,
                "interpretation": f"Each 1°C increase is associated with ~{coef:.3f} min more travel (simple regression, unadjusted)",
            }
        except Exception as e:
            return {"error": str(e)}

    def route_intervention_effectiveness(self, route_data: pd.DataFrame) -> dict:
        """
        Measure effectiveness of an intervention (new lane, timing change, etc).

        Requires: Data with before/after periods marked
        """
        if "travel_time_min" not in route_data.columns:
            return {"error": "Missing travel_time_min"}

        try:
            # Assume: last 25% is "after" intervention, first 75% is "before"
            split_point = int(len(route_data) * 0.75)

            before = route_data.iloc[:split_point]["travel_time_min"]
            after = route_data.iloc[split_point:]["travel_time_min"]

            if len(before) < 10 or len(after) < 10:
                return {"error": "Insufficient data in before/after periods"}

            # Simple before/after comparison (NOT difference-in-differences: there is no control group, so anything that
            # changed over time -season, traffic growth- is attributed to the "intervention")
            before_mean = before.mean()
            after_mean = after.mean()
            effect = after_mean - before_mean

            # Statistical significance
            t_stat, p_val = stats.ttest_ind(after, before)

            # Effect size (Cohen's d)
            pooled_std = np.sqrt(
                ((len(before) - 1) * before.std() ** 2 + (len(after) - 1) * after.std() ** 2)
                / (len(before) + len(after) - 2)
            )
            cohens_d = effect / pooled_std if pooled_std > 0 else 0

            return {
                "intervention_effect": {
                    "before_mean": float(before_mean),
                    "after_mean": float(after_mean),
                    "effect_size": float(effect),
                    "interpretation": f"Observed change of {effect:+.2f} min after the split point (before/after, no control group)",
                    "direction": "improvement" if effect < 0 else "degradation",
                },
                "statistical_significance": {
                    "t_statistic": float(t_stat),
                    "p_value": float(p_val),
                    "significant": p_val < 0.05,
                    "cohens_d": float(cohens_d),
                    "effect_magnitude": self._interpret_cohens_d(abs(cohens_d)),
                },
                "sample_sizes": {"before": len(before), "after": len(after)},
            }
        except Exception as e:
            return {"error": str(e)}

    def confounding_analysis(self) -> dict:
        """
        Identify potential confounders.

        Confounder: A variable that affects both treatment and outcome.
        Example: Time of day affects both temperature (peak heat) AND traffic.
        """
        df = self.df.copy()

        confounders = []

        # Check if hour affects both temperature and travel time
        if "hour" in df.columns and "origin_temperature" in df.columns and "travel_time_min" in df.columns:
            corr_hour_temp = df["hour"].corr(df["origin_temperature"])
            corr_hour_traffic = df["hour"].corr(df["travel_time_min"])

            if abs(corr_hour_temp) > 0.3 and abs(corr_hour_traffic) > 0.3:
                confounders.append(
                    {
                        "variable": "hour",
                        "affects_treatment": f"corr={corr_hour_temp:.3f}",
                        "affects_outcome": f"corr={corr_hour_traffic:.3f}",
                        "severity": "high" if abs(corr_hour_temp) > 0.5 else "moderate",
                    }
                )

        # Check if day of week is a confounder
        if "day_of_week" in df.columns and "travel_time_min" in df.columns:
            daily_traffic = df.groupby("day_of_week")["travel_time_min"].mean()
            if daily_traffic.std() > daily_traffic.mean() * 0.2:  # >20% variation
                confounders.append(
                    {
                        "variable": "day_of_week",
                        "affects_outcome": "yes",
                        "severity": "moderate",
                        "advice": "Stratify analysis by day of week",
                    }
                )

        return {
            "identified_confounders": confounders,
            "advice": "Control for confounders using stratification or regression",
            "method_recommendation": "Use propensity score matching or stratified analysis",
        }

    @staticmethod
    def _interpret_causal_effect(effect_size, p_value):
        """Interpret an UNADJUSTED difference between groups (evidence of an association, not of causality)."""
        if p_value < 0.001:
            significance = "Very strong evidence"
        elif p_value < 0.01:
            significance = "Strong evidence"
        elif p_value < 0.05:
            significance = "Moderate evidence"
        else:
            significance = "Weak evidence"

        return f"{significance} of an unadjusted difference of {effect_size:+.2f} minutes between the groups."

    @staticmethod
    def _interpret_cohens_d(d):
        """Interpret Cohen's d effect size."""
        if d < 0.2:
            return "negligible"
        elif d < 0.5:
            return "small"
        elif d < 0.8:
            return "medium"
        else:
            return "large"
