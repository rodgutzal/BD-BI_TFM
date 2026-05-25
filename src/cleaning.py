import pandas as pd

# Leer datos
df = pd.read_csv("data/raw/traffic_weather_data.csv")

# Limpiar valores vacíos
df = df.ffill()

# Eliminar duplicados
df = df.drop_duplicates()

# Guardar datos limpios
df.to_csv("data/processed/clean_traffic_weather_data.csv", index=False)

print("Limpieza completada.")
print(df.head())