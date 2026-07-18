import os
from pathlib import Path


def _get_env_value_from_dotenv(name: str) -> str | None:
    """Read an environment variable from a local .env file if present."""
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


def _get_required_api_key(name: str) -> str:
    """Return a required API key from the environment or local .env."""
    api_key = os.getenv(name) or _get_env_value_from_dotenv(name)
    if api_key:
        return api_key

    raise RuntimeError(
        f"Missing {name} environment variable. "
        "Set it in your shell or add it to a local .env file."
    )


def get_tomtom_api_key() -> str:
    """Return the TomTom API key from the environment or local .env."""
    return _get_required_api_key("TOMTOM_API_KEY")


def get_openweather_api_key() -> str:
    """Return the OpenWeather API key from the environment or local .env."""
    return _get_required_api_key("OPENWEATHER_API_KEY")
