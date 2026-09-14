"""Análisis histórico de datos de movilidad."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from src.database import RouteDatabase
from src.locations import ROUTES, get_all_unique_locations

logger = logging.getLogger(__name__)


class MobilityAnalytics:
    """Analizador de datos históricos de movilidad."""

    def __init__(self, db_path: Path):
        self.db = RouteDatabase(Path.home(), db_path)

    def get_peak_hours(self, origin: str, destination: str, metric: str = "traffic_delay_min") -> pd.DataFrame:
        """Identifica las horas de mayor congestión."""
        return self.db.get_hourly_statistics(origin, destination, days=7)

    def compare_routes(self, hours: int = 24) -> pd.DataFrame:
        """Compara el desempeño de todas las rutas."""
        return self.db.get_all_routes_statistics(hours)

    def get_route_trend(self, origin: str, destination: str, hours: int = 24) -> dict:
        """Analiza la tendencia de tiempo de viaje en una ruta."""
        df = self.db.get_time_series(
            origin, destination,
            metric="travel_time_min",
            hours=hours
        )

        if df.empty:
            return {"status": "no_data"}

        first_third = df["value"].iloc[:len(df)//3].mean()
        last_third = df["value"].iloc[-len(df)//3:].mean()

        if last_third > first_third * 1.1:
            trend = "increasing"
            change_pct = round(((last_third - first_third) / first_third) * 100, 1)
        elif last_third < first_third * 0.9:
            trend = "decreasing"
            change_pct = round(((first_third - last_third) / first_third) * 100, 1)
        else:
            trend = "stable"
            change_pct = 0

        return {
            "trend": trend,
            "change_percent": change_pct,
            "current_avg": round(df["value"].iloc[-10:].mean(), 2),
            "historical_avg": round(df["value"].mean(), 2),
        }

    def get_weather_impact(self, origin: str, destination: str) -> dict:
        """Analiza el impacto del clima en los tiempos de viaje."""
        df = self.db.query_measurements(origin, destination, limit=1000)

        if df.empty:
            return {"status": "no_data"}

        # BD_BI_TFM: el esquema guarda el clima por separado en origen y
        # destino (origin_temperature / destination_temperature); se usa
        # origin_temperature como referencia, con fallback a "temperature"
        # por si se consulta un CSV/DataFrame con el esquema antiguo.
        temp_col = "origin_temperature" if "origin_temperature" in df.columns else "temperature"
        if temp_col not in df.columns:
            return {"status": "no_weather_data"}

        # Dividir en rangos de temperatura
        cold = df[df[temp_col] < 15]["travel_time_min"]
        mild = df[(df[temp_col] >= 15) & (df[temp_col] < 25)]["travel_time_min"]
        warm = df[df[temp_col] >= 25]["travel_time_min"]

        return {
            "cold_avg": round(cold.mean(), 2) if len(cold) > 0 else None,
            "mild_avg": round(mild.mean(), 2) if len(mild) > 0 else None,
            "warm_avg": round(warm.mean(), 2) if len(warm) > 0 else None,
            "cold_count": len(cold),
            "mild_count": len(mild),
            "warm_count": len(warm),
        }

    def get_consistency_score(self, origin: str, destination: str, hours: int = 24) -> float:
        """Calcula un score de consistencia (0-100) para una ruta."""
        stats = self.db.get_route_statistics(origin, destination, hours)

        if not stats or stats["count"] < 5:
            return 0.0

        avg_time = stats["avg_travel_time"]
        min_time = stats["min_travel_time"]
        max_time = stats["max_travel_time"]

        if avg_time == 0:
            return 0.0

        variance = ((max_time - min_time) / avg_time) * 100

        if variance < 10:
            score = 100.0
        elif variance < 20:
            score = 85.0
        elif variance < 30:
            score = 70.0
        elif variance < 50:
            score = 50.0
        else:
            score = 25.0

        return round(score, 1)

    def generate_summary_report(self) -> str:
        """Genera un reporte textual completo de todas las rutas."""
        summary = self.db.get_database_summary()
        routes_stats = self.db.get_all_routes_statistics(hours=24)

        report = []
        report.append("=" * 60)
        report.append("URBAN MOBILITY ANALYTICS - SUMMARY REPORT")
        report.append("=" * 60)
        report.append("")

        report.append(f"Database Status:")
        report.append(f"  Total Records: {summary['total_records']}")
        report.append(f"  Unique Routes: {summary['unique_routes']}")
        report.append(f"  Data Range: {summary['first_timestamp']} to {summary['last_timestamp']}")
        report.append("")

        if not routes_stats.empty:
            report.append("Routes Summary (Last 24h):")
            report.append("")

            for _, route in routes_stats.iterrows():
                consistency = self.get_consistency_score(route["origin"], route["destination"], hours=24)
                report.append(f"  {route['origin']} → {route['destination']}")
                report.append(f"    Measurements: {route['measurements']}")
                report.append(f"    Travel Time: {route['avg_travel_time']}min (range: {route['min_travel_time']}-{route['max_travel_time']}min)")
                report.append(f"    Traffic Delay: {route['avg_delay']}min")
                report.append(f"    Average Speed: {route['avg_speed']} km/h")
                report.append(f"    Consistency Score: {consistency}%")
                report.append("")

        report.append("=" * 60)

        return "\n".join(report)


def main():
    """CLI para análisis histórico."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Urban Mobility Analytics - Historical Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.analytics summary          # Print summary report
  python -m src.analytics trend Msida Gzira      # Show travel time trend
  python -m src.analytics weather Msida Sliema   # Analyze weather impact
  python -m src.analytics consistency Msida Valletta  # Check reliability
        """,
    )

    parser.add_argument(
        "command",
        nargs="?",
        choices=["summary", "trend", "weather", "consistency", "compare"],
        default="summary",
        help="Analysis command",
    )

    parser.add_argument("origin", nargs="?", help="Route origin")
    parser.add_argument("destination", nargs="?", help="Route destination")

    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Hours of historical data to analyze (default: 24)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_dir = Path(__file__).resolve().parents[2]
    db_path = root_dir / "data" / "mobility.db"

    analytics = MobilityAnalytics(db_path)

    if args.command == "summary":
        print(analytics.generate_summary_report())

    elif args.command == "trend":
        if not args.origin or not args.destination:
            print("Error: trend command requires origin and destination")
            return 1
        trend = analytics.get_route_trend(args.origin, args.destination, args.hours)
        print(f"\nRoute: {args.origin} → {args.destination}")
        print(f"Trend: {trend.get('trend', 'unknown').upper()}")
        if trend.get("change_percent"):
            print(f"Change: {trend['change_percent']}%")
        print(f"Current Avg: {trend.get('current_avg')}min")
        print(f"Historical Avg: {trend.get('historical_avg')}min")

    elif args.command == "weather":
        if not args.origin or not args.destination:
            print("Error: weather command requires origin and destination")
            return 1
        impact = analytics.get_weather_impact(args.origin, args.destination)
        print(f"\nRoute: {args.origin} → {args.destination}")
        print(f"Cold Weather (<15°C): {impact.get('cold_avg')}min ({impact.get('cold_count')} records)")
        print(f"Mild Weather (15-25°C): {impact.get('mild_avg')}min ({impact.get('mild_count')} records)")
        print(f"Warm Weather (>25°C): {impact.get('warm_avg')}min ({impact.get('warm_count')} records)")

    elif args.command == "consistency":
        if not args.origin or not args.destination:
            print("Error: consistency command requires origin and destination")
            return 1
        score = analytics.get_consistency_score(args.origin, args.destination, args.hours)
        print(f"\nRoute: {args.origin} → {args.destination}")
        print(f"Consistency Score: {score}%")
        if score >= 85:
            print("Rating: Excellent - Very reliable route")
        elif score >= 70:
            print("Rating: Good - Mostly reliable")
        elif score >= 50:
            print("Rating: Fair - Variable conditions")
        else:
            print("Rating: Poor - Highly variable")

    elif args.command == "compare":
        stats = analytics.compare_routes(args.hours)
        if stats.empty:
            print("No data available for comparison")
            return 1
        print(f"\nAll Routes Comparison (Last {args.hours}h):")
        print(stats.to_string(index=False))

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
