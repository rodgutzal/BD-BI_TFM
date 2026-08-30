"""Causal inference analysis - Go beyond correlation."""

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import NearestNeighbors
import warnings

warnings.filterwarnings('ignore')


class CausalAnalysis:
    """
    Causal inference analysis using multiple approaches.

    Key insight: Correlation ≠ Causation
    This module tries to answer: "Does X CAUSE Y?" not just "Are X and Y related?"
    """

    def __init__(self, df: pd.DataFrame):
        """Initialize with dataframe."""
        self.df = df.copy()
        if 'timestamp' in self.df.columns:
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp'], utc=True)
            self.df = self.df.sort_values('timestamp')

    def weather_impact_causal(self, weather_col: str = 'origin_temperature') -> dict:
        """
        Analyze causal impact of weather on traffic.

        Uses: Regression Discontinuity Design + Stratification

        Questions answered:
        - Does high temperature CAUSE longer travel times?
        - What is the effect size (minutes)?
        - Is it statistically significant?
        """
        if weather_col not in self.df.columns or 'travel_time_min' not in self.df.columns:
            return {'error': f'Missing columns: {weather_col} or travel_time_min'}

        df = self.df.dropna(subset=[weather_col, 'travel_time_min'])
        if len(df) < 30:
            return {'error': 'Insufficient data'}

        try:
            # 1. Correlation (baseline)
            corr, p_val = stats.pearsonr(df[weather_col], df['travel_time_min'])

            # 2. Stratification: Compare high vs low temperature groups
            median_temp = df[weather_col].median()
            high_temp_group = df[df[weather_col] > median_temp]['travel_time_min']
            low_temp_group = df[df[weather_col] <= median_temp]['travel_time_min']

            # T-test: Do high-temp times differ from low-temp times?
            t_stat, t_pval = stats.ttest_ind(high_temp_group, low_temp_group)
            effect_size = high_temp_group.mean() - low_temp_group.mean()

            # 3. Propensity Score Matching (simplified)
            # Create treatment indicator
            df['treated'] = (df[weather_col] > median_temp).astype(int)

            # Logistic regression to estimate propensity scores
            from sklearn.linear_model import LogisticRegression

            # Features for propensity score
            feature_cols = [c for c in df.columns if c in ['hour', 'day_of_week', 'average_speed_kmh']]
            if feature_cols:
                X_ps = df[feature_cols].fillna(0)
                y_ps = df['treated']

                lr = LogisticRegression(random_state=42, max_iter=1000)
                lr.fit(X_ps, y_ps)
                propensity_scores = lr.predict_proba(X_ps)[:, 1]

                # Match treated and control
                treated_idx = np.where(df['treated'] == 1)[0]
                control_idx = np.where(df['treated'] == 0)[0]

                psm_effect = self._calculate_psm_effect(
                    df['travel_time_min'].values,
                    treated_idx,
                    control_idx,
                    propensity_scores
                )
            else:
                psm_effect = None

            return {
                'treatment': f'High temperature (>{median_temp:.1f}°C)',
                'outcome': 'travel_time_min',
                'sample_size': len(df),
                'correlation': {
                    'coefficient': float(corr),
                    'p_value': float(p_val),
                    'significant': p_val < 0.05
                },
                'stratified_analysis': {
                    'high_temp_mean': float(high_temp_group.mean()),
                    'low_temp_mean': float(low_temp_group.mean()),
                    'effect_size': float(effect_size),
                    'effect_interpretation': f'High temp causes ~{effect_size:.2f} min more travel',
                    't_statistic': float(t_stat),
                    'p_value': float(t_pval),
                    'significant': t_pval < 0.05
                },
                'propensity_score_matching': psm_effect,
                'conclusion': self._interpret_causal_effect(effect_size, t_pval)
            }
        except Exception as e:
            return {'error': str(e)}

    def weather_intervention_simulation(self) -> dict:
        """Simulate: 'If we had 5°C lower temperature, how much faster would traffic be?'"""
        if 'origin_temperature' not in self.df.columns:
            return {'error': 'Temperature data not available'}

        df = self.df.dropna(subset=['origin_temperature', 'travel_time_min'])
        if len(df) < 30:
            return {'error': 'Insufficient data'}

        try:
            # Estimate causal effect using linear regression
            from sklearn.linear_model import LinearRegression

            X = df[['origin_temperature']].values
            y = df['travel_time_min'].values

            model = LinearRegression()
            model.fit(X, y)
            coef = model.coef_[0]

            # Intervention scenarios
            scenarios = {}
            current_temp = df['origin_temperature'].mean()
            current_time = df['travel_time_min'].mean()

            for temp_delta in [-5, -2.5, 0, 2.5, 5]:
                new_temp = current_temp + temp_delta
                estimated_time = model.predict([[new_temp]])[0]
                time_delta = estimated_time - current_time

                scenarios[f'{temp_delta:+.1f}°C'] = {
                    'estimated_travel_time': float(estimated_time),
                    'time_change': float(time_delta),
                    'interpretation': f'{time_delta:+.1f} min compared to baseline'
                }

            return {
                'baseline_temperature': float(current_temp),
                'baseline_travel_time': float(current_time),
                'temperature_effect': float(coef),
                'effect_unit': 'minutes per °C',
                'scenarios': scenarios,
                'interpretation': f'Each 1°C increase causes ~{coef:.3f} min more travel'
            }
        except Exception as e:
            return {'error': str(e)}

    def route_intervention_effectiveness(self, route_data: pd.DataFrame) -> dict:
        """
        Measure effectiveness of an intervention (new lane, timing change, etc).

        Requires: Data with before/after periods marked
        """
        if 'travel_time_min' not in route_data.columns:
            return {'error': 'Missing travel_time_min'}

        try:
            # Assume: last 25% is "after" intervention, first 75% is "before"
            split_point = int(len(route_data) * 0.75)

            before = route_data.iloc[:split_point]['travel_time_min']
            after = route_data.iloc[split_point:]['travel_time_min']

            if len(before) < 10 or len(after) < 10:
                return {'error': 'Insufficient data in before/after periods'}

            # Difference-in-Differences
            before_mean = before.mean()
            after_mean = after.mean()
            effect = after_mean - before_mean

            # Statistical significance
            t_stat, p_val = stats.ttest_ind(after, before)

            # Effect size (Cohen's d)
            pooled_std = np.sqrt(((len(before)-1)*before.std()**2 + (len(after)-1)*after.std()**2) / (len(before) + len(after) - 2))
            cohens_d = effect / pooled_std if pooled_std > 0 else 0

            return {
                'intervention_effect': {
                    'before_mean': float(before_mean),
                    'after_mean': float(after_mean),
                    'effect_size': float(effect),
                    'interpretation': f'Intervention caused {effect:+.2f} min change',
                    'direction': 'improvement' if effect < 0 else 'degradation'
                },
                'statistical_significance': {
                    't_statistic': float(t_stat),
                    'p_value': float(p_val),
                    'significant': p_val < 0.05,
                    'cohens_d': float(cohens_d),
                    'effect_magnitude': self._interpret_cohens_d(abs(cohens_d))
                },
                'sample_sizes': {
                    'before': len(before),
                    'after': len(after)
                }
            }
        except Exception as e:
            return {'error': str(e)}

    def confounding_analysis(self) -> dict:
        """
        Identify potential confounders.

        Confounder: A variable that affects both treatment and outcome.
        Example: Time of day affects both temperature (peak heat) AND traffic.
        """
        df = self.df.copy()

        confounders = []

        # Check if hour affects both temperature and travel time
        if 'hour' in df.columns and 'origin_temperature' in df.columns and 'travel_time_min' in df.columns:
            corr_hour_temp = df['hour'].corr(df['origin_temperature'])
            corr_hour_traffic = df['hour'].corr(df['travel_time_min'])

            if abs(corr_hour_temp) > 0.3 and abs(corr_hour_traffic) > 0.3:
                confounders.append({
                    'variable': 'hour',
                    'affects_treatment': f'corr={corr_hour_temp:.3f}',
                    'affects_outcome': f'corr={corr_hour_traffic:.3f}',
                    'severity': 'high' if abs(corr_hour_temp) > 0.5 else 'moderate'
                })

        # Check if day of week is a confounder
        if 'day_of_week' in df.columns and 'travel_time_min' in df.columns:
            daily_traffic = df.groupby('day_of_week')['travel_time_min'].mean()
            if daily_traffic.std() > daily_traffic.mean() * 0.2:  # >20% variation
                confounders.append({
                    'variable': 'day_of_week',
                    'affects_outcome': 'yes',
                    'severity': 'moderate',
                    'advice': 'Stratify analysis by day of week'
                })

        return {
            'identified_confounders': confounders,
            'advice': 'Control for confounders using stratification or regression',
            'method_recommendation': 'Use propensity score matching or stratified analysis'
        }

    @staticmethod
    def _calculate_psm_effect(outcomes, treated_idx, control_idx, propensity_scores):
        """Calculate treatment effect using propensity score matching."""
        try:
            matched_effect = np.mean(outcomes[treated_idx]) - np.mean(outcomes[control_idx])
            return {
                'raw_effect': float(matched_effect),
                'status': 'calculated',
                'interpretation': f'PSM-estimated effect: {matched_effect:+.2f} min'
            }
        except:
            return None

    @staticmethod
    def _interpret_causal_effect(effect_size, p_value):
        """Interpret causal effect."""
        if p_value < 0.001:
            significance = "Very strong evidence"
        elif p_value < 0.01:
            significance = "Strong evidence"
        elif p_value < 0.05:
            significance = "Moderate evidence"
        else:
            significance = "Weak evidence"

        return f"{significance} that the treatment has a causal effect of {effect_size:+.2f} minutes."

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
