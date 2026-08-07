# BD-BI_TFM — Plataforma de Análisis de Movilidad Urbana

TFM · Máster en Big Data & Business Intelligence
Stack: **TimescaleDB · PostGIS · Streamlit · pgAdmin**

---

## Estructura del proyecto

```
BD-BI_TFM/
├── data/
│   ├── raw/
│   │   └── traffic_weather_data.csv          ← CSV generado por api_extraction.py
│   └── processed/
│       └── clean_traffic_weather_data.csv     ← generado por cleaning.py
├── init/
│   └── 01_init.sql                            ← se ejecuta al primer arranque de DB
├── src/
│   ├── api_extraction.py                      ← extrae datos de ORS + OpenWeather
│   ├── cleaning.py                            ← limpia y normaliza el CSV
│   └── scheduler.py                           ← ejecuta api_extraction cada 2 min
├── streamlit_app/
│   └── app.py                                 ← dashboard de visualización
├── docker-compose.yml
└── README.md
```

---

## Dataset: `data/raw/traffic_weather_data.csv`

Generado automáticamente por `src/api_extraction.py` usando
OpenRouteService (rutas) y OpenWeatherMap (clima). Columnas:

| Columna               | Tipo      | Descripción                                         |
|-----------------------|-----------|-----------------------------------------------------|
| `datetime`            | TIMESTAMP | Marca de tiempo del viaje (local)                   |
| `origin`              | TEXT      | Zona de origen (Msida, Valletta, Sliema…)           |
| `destination`         | TEXT      | Zona de destino                                     |
| `distance_km`         | NUMERIC   | Distancia del trayecto en kilómetros                |
| `duration_min`        | NUMERIC   | Duración estimada en minutos                        |
| `temperature`         | NUMERIC   | Temperatura en °C                                   |
| `humidity`            | INTEGER   | Humedad relativa (%)                                |
| `weather_description` | TEXT      | Descripción del clima (few clouds, clear sky…)      |
| `mobility_level`      | TEXT      | Nivel de movilidad (Movilidad normal / Alta demora) |

---

## Requisitos

- Docker Desktop (Windows / Mac) o Docker Engine + Docker Compose (Linux)
- 4 GB de RAM disponibles
- API key de OpenWeatherMap (gratuita en https://openweathermap.org/api)

### Nota: `psql` viene con pgAdimn( que ya se va a usar igual ):
#### Windows
1. Si instalas pgAdmin4 ( el cual se menciona dentro de este documento ), psql no viene incluido directamente, así que mejor instala el cliente oficial de [PostgreSQL](https://www.postgresql.org/download/windows/).
2. Ejecuta el instalador y en la pantalla de selección de componentes, desmarca "PostgreSQL Server" si solo quieres el cliente (puedes dejarlo marcado, no estorba, solo pesa más)
3. Asegúrate de marcar "Command Line Tools"
4. Al finalizar, agrega la ruta al PATH si el instalador no lo hizo automáticamente, normalmente:
```
C:\Program Files\PostgreSQL\17\bin
```
5. Abre una nueva terminal (PowerShell o CMD) y verifica:
```
psql --version
```
Alternativa más ligera ( sin instalar todo PostgresSQL ): ssi usas Scoop:
```
scoop install postgresql
```
#### MacOs
Con Homebrew( lo más simple ):
```
brew install libpq
brew link --force libpq
psql --version
```
libpq es el paquete cliente sin el servidor completo, así que es liviano.

---

## 1. Configurar la variable de entorno

Crea un archivo `.env` en la raíz del proyecto con tu API key:

```
OPENWEATHER_API_KEY=tu_clave_aqui
```

> La clave de ORS (OpenRouteService) ya está incluida en `api_extraction.py`.

---

## 2. Levantar el stack

```powershell
cd BD-BI_TFM
docker compose up -d
```

Verifica que los contenedores están corriendo:

```powershell
docker compose ps
```

| Contenedor          | Descripción                              | Estado esperado |
|---------------------|------------------------------------------|-----------------|
| movilidad-db        | TimescaleDB (base de datos)              | running         |
| movilidad-pgadmin   | Administrador web de la DB               | running         |
| movilidad-streamlit | Dashboard Streamlit                      | running         |
| movilidad-scheduler | Extrae datos cada 2 minutos              | running         |

---

## 3. Acceder a cada servicio

| Servicio    | URL                   | Usuario       | Contraseña                |
|-------------|-----------------------|---------------|---------------------------|
| TimescaleDB | localhost:5432        | postgres      | tfm_password              |
| pgAdmin     | http://localhost:8080 | admin@tfm.com | tfm_password              |
| Streamlit   | http://localhost:8501 | —             | —                         |

---

## 4. Cargar el CSV histórico a TimescaleDB

El scheduler genera datos nuevos automáticamente, pero para cargar el CSV
histórico que ya tienes en `data/raw/` ejecuta lo siguiente.

**Paso 1 — copia el CSV al contenedor:**

```powershell
docker cp data\raw\traffic_weather_data.csv movilidad-db:/tmp/traffic_weather_data.csv
```

**Paso 2 — entra a psql:**

```powershell
docker exec -it movilidad-db psql -U postgres -d movilidad_urbana
```

**Paso 3 — carga los datos (dentro del prompt psql):**

```sql
\COPY traffic_trips(datetime, origin, destination, distance_km, duration_min,
                    temperature, humidity, weather_description, mobility_level)
FROM '/tmp/traffic_weather_data.csv'
CSV HEADER;
```

---

## 5. Verificar la carga

Dentro del prompt psql:

```sql
-- Total de registros cargados
SELECT COUNT(*) FROM traffic_trips;

-- Vista previa
SELECT * FROM traffic_trips ORDER BY datetime DESC LIMIT 5;

-- Viajes por nivel de movilidad
SELECT mobility_level, COUNT(*) FROM traffic_trips GROUP BY mobility_level;

-- Rutas más frecuentes
SELECT origin, destination, COUNT(*) AS viajes
FROM traffic_trips
GROUP BY origin, destination
ORDER BY viajes DESC;

-- Aggregate por hora (continuous aggregate)
SELECT * FROM trips_hourly ORDER BY hour DESC LIMIT 10;
```

---

## 6. Ejecutar el pipeline manualmente (fuera de Docker)

Si prefieres correr los scripts directamente en tu máquina:

```bash
pip install pandas requests python-dotenv
```

**Extracción** (guarda en `data/raw/`):
```bash
python src/api_extraction.py
```

**Limpieza** (guarda en `data/processed/`):
```bash
python src/cleaning.py
```

**Scheduler** (extrae cada 2 minutos en bucle):
```bash
python src/scheduler.py
```

> El scheduler solo llama a `api_extraction.py`. Para limpiar los datos
> corre `cleaning.py` manualmente cuando lo necesites.

### Nota:
Sí al momento de correr el primer commando sale la leyenda
```pip : The term 'pip' is not recognized as the name of a cmdlet, function, script file, or operable program. Check the spelling of the name, or if a
path was included, verify that the path is correct and try again.
```
primero intenta correr los siguientes comandos
```powershell
python --version
```
```powershell
python3 --version
```
#### Solución 1 — Instalar Python (si no lo tienes)
1. Instala [python](https://www.python.org/downloads/windows/)
2. Ejecuta el instalador y antes de darle a Install Now, marca obligatoriamente esta casilla:
```
☑ Add python.exe to PATH
```
Si no marcas esa casilla, pip y python seguirán sin reconocerse aunque Python quede instalado.
3. Completa la instalación y abre una PowerShell nueva (las que ya tenías abiertas no actualizan el PATH).
4. Verifica:
```powershell
python --version
pip --version
```
#### Solución 2 — Python instalado pero pip no está en el PATH
Prueba llamarlo a través de Python directamente:
```powershell
python -m pip install pandas requests python-dotenv
```
Esto evita depender de que pip esté en el PATH — lo ejecuta como módulo de Python, que sí está registrado.
#### Solución 3 — Si ya tienes el stack Docker corriendo (la más rápida)
Como los contenedores movilidad-scheduler y movilidad-streamlit ya tienen Python y todas las dependencias instaladas dentro, no necesitas instalar nada en tu máquina para que el pipeline corra. Docker lo maneja todo internamente.
Solo necesitarías pip en tu máquina si quisieras correr los scripts fuera de Docker. Para el TFM, con Docker corriendo es suficiente.

---

## 7. Apagar / limpiar

```powershell
docker compose down      # detiene los contenedores (conserva los datos)
docker compose down -v   # detiene Y BORRA el volumen (empieza de cero)
```

---

## Tabla principal: `traffic_trips`

Creada automáticamente por `init/01_init.sql` al primer arranque:

| Elemento                          | Detalle                                          |
|-----------------------------------|--------------------------------------------------|
| Hypertable por `datetime`         | Particionado automático, consultas más rápidas   |
| Índice por `origin + destination` | Filtrado ágil por corredor de movilidad          |
| Índice por `mobility_level`       | Análisis de congestión instantáneo               |
| Continuous aggregate `trips_hourly` | Agrega viajes por hora sin recalcular cada vez |
