import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjU1MTE1OGE1NWI3ZDQ3MjQ5NjEyNGI5NTBmZTAwYzI3IiwiaCI6Im11cm11cjY0In0="
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

route_url = "https://api.openrouteservice.org/v2/directions/driving-car"

headers = {
    "Authorization": ORS_API_KEY,
    "Accept": "application/json, application/geo+json",
    "Content-Type": "application/json",
}

weather_url = (
    "https://api.openweathermap.org/data/2.5/weather?"
    f"lat=35.8950&lon=14.4828&appid={OPENWEATHER_API_KEY}&units=metric"
)

weather_response = requests.get(weather_url)
weather_data = weather_response.json()

temperature = weather_data["main"]["temp"]
humidity = weather_data["main"]["humidity"]
weather_description = weather_data["weather"][0]["description"]

routes = [
    {
        "origin_name": "Msida",
        "destination_name": "Valletta",
        "origin": [14.4828, 35.8950],
        "destination": [14.5146, 35.8997],
    },
    {
        "origin_name": "Msida",
        "destination_name": "Sliema",
        "origin": [14.4828, 35.8950],
        "destination": [14.5012, 35.9122],
    },
    {
        "origin_name": "Msida",
        "destination_name": "Birkirkara",
        "origin": [14.4828, 35.8950],
        "destination": [14.4611, 35.8972],
    },
    {
        "origin_name": "Msida",
        "destination_name": "St Julian's",
        "origin": [14.4828, 35.8950],
        "destination": [14.4905, 35.9181],
    },
    {
        "origin_name": "Valletta",
        "destination_name": "Marsaskala",
        "origin": [14.5146, 35.8997],
        "destination": [14.5625, 35.8622],
    },
    {
        "origin_name": "Valletta",
        "destination_name": "Sliema",
        "origin": [14.5146, 35.8997],
        "destination": [14.5012, 35.9122],
    },
    {
        "origin_name": "Valletta",
        "destination_name": "Birkirkara",
        "origin": [14.5146, 35.8997],
        "destination": [14.4611, 35.8972],
    },
    {
        "origin_name": "Sliema",
        "destination_name": "St Julian's",
        "origin": [14.5012, 35.9122],
        "destination": [14.4905, 35.9181],
    },
    {
        "origin_name": "Birkirkara",
        "destination_name": "Valletta",
        "origin": [14.4611, 35.8972],
        "destination": [14.5146, 35.8997],
    },
    {
        "origin_name": "Marsaskala",
        "destination_name": "Valletta",
        "origin": [14.5625, 35.8622],
        "destination": [14.5146, 35.8997],
    },
]

records = []

for route in routes:
    body = {
        "coordinates": [route["origin"], route["destination"]]
    }

    route_response = requests.post(route_url, json=body, headers=headers)
    route_data = route_response.json()
    print(route_data)

    distance_km = route_data["routes"][0]["summary"]["distance"] / 1000
    duration_min = route_data["routes"][0]["summary"]["duration"] / 60

    mobility_level = "Alta demora" if duration_min > 20 else "Movilidad normal"

    records.append(
        {
            "datetime": datetime.now(),
            "origin": route["origin_name"],
            "destination": route["destination_name"],
            "distance_km": round(distance_km, 2),
            "duration_min": round(duration_min, 2),
            "temperature": temperature,
            "humidity": humidity,
            "weather_description": weather_description,
            "mobility_level": mobility_level,
        }
    )

df = pd.DataFrame(records)

csv_path = Path("data/raw/traffic_weather_data.csv")

if csv_path.exists():
    df.to_csv(csv_path, mode="a", header=False, index=False)
else:
    df.to_csv(csv_path, index=False)

print("Datos guardados correctamente.")
print(df)