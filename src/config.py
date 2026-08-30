"""Configuración centralizada: claves de API, fuente de datos y conexión a TimescaleDB."""

import os
from pathlib import Path


def _get_env_value_from_dotenv(name: str) -> str | None:
    """Lee una variable de entorno desde el archivo .env local, si existe."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return None

    for line in env_path.read_text().splitlines():
        cleaned_line = line.strip()
        if not cleaned_line or cleaned_line.startswith("#"):
            continue
        if cleaned_line.startswith(f"{name}="):
            _, value = cleaned_line.split("=", 1)
            return value.strip().strip("'").strip('"')

    return None


def get_env(name: str, default: str | None = None) -> str | None:
    """Lee una variable de entorno del shell o del .env local, con default opcional."""
    return os.getenv(name) or _get_env_value_from_dotenv(name) or default


def _get_required_api_key(name: str) -> str:
    """Retorna una clave de API requerida desde el entorno o el .env local."""
    api_key = get_env(name)
    if api_key:
        return api_key

    raise RuntimeError(
        f"Missing {name} environment variable. "
        "Set it in your shell or add it to a local .env file."
    )


def get_tomtom_api_key() -> str:
    """Retorna la clave de TomTom API."""
    return _get_required_api_key("TOMTOM_API_KEY")


def get_ors_api_key() -> str:
    """Retorna la clave de OpenRouteService API."""
    return _get_required_api_key("ORS_API_KEY")


def get_openweather_api_key() -> str:
    """Retorna la clave de OpenWeather API."""
    return _get_required_api_key("OPENWEATHER_API_KEY")


def get_data_source() -> str:
    """
    Retorna la fuente de datos de tráfico activa: 'ors' o 'tomtom'.

    Configurable vía DATA_SOURCE en .env. Por defecto 'ors', ya que no
    requiere una clave adicional a las que ya usaba BD_BI_TFM.
    """
    source = (get_env("DATA_SOURCE", "ors") or "ors").strip().lower()
    if source not in ("ors", "tomtom"):
        raise RuntimeError(
            f"DATA_SOURCE inválido: '{source}'. Usa 'ors' o 'tomtom'."
        )
    return source


def get_timescale_config() -> dict:
    """Retorna la configuración de conexión a TimescaleDB (capa de producción)."""
    return {
        "host": get_env("PGHOST", "localhost"),
        "port": int(get_env("PGPORT", "5432")),
        "dbname": get_env("PGDATABASE", "movilidad_urbana"),
        "user": get_env("PGUSER", "postgres"),
        "password": get_env("PGPASSWORD", "tfm_password"),
    }
