# BD_BI_TFM — Plataforma de Análisis de Movilidad Urbana

TFM · Máster en Big Data & Business Intelligence
Fusión de **BD-BI_TFM** (base: TimescaleDB · PostGIS · Streamlit · pgAdmin) +
**urban-mobility-analytics1** (analytics avanzado · ML · tests · CI/CD)

Stack: **TimescaleDB · PostGIS · SQLite · Streamlit · pgAdmin · Docker · scikit-learn/XGBoost**

---

## Qué es esto

Este repo integra dos proyectos que analizaban movilidad urbana en Malta por separado:

- **BD_BI_TFM**: recolectaba datos con OpenRouteService (ORS) + OpenWeather y los guardaba en TimescaleDB/PostGIS (Docker), con un dashboard Streamlit simple.
- **urban-mobility-analytics1**: recolectaba con TomTom + OpenWeather y los guardaba en SQLite, con analítica avanzada (tendencias, impacto del clima, consistencia), modelos de Machine Learning (Random Forest, ensemble XGBoost/Gradient Boosting), arquitectura de data warehouse (Bronze/Silver/Gold), tests, y CI/CD.

**BD_BI_TFM** no elige entre ambos: los combina.

- **Dos fuentes de tráfico intercambiables** (`DATA_SOURCE=ors` o `tomtom` en `.env`)
- **Dos capas de almacenamiento en paralelo**: TimescaleDB (producción/BI) + SQLite (local, analítica y ML)
- **Pipeline Bronze → Silver → Gold automático** en cada ciclo de recolección, alimentando un dashboard Executive con KPIs reales
- **2.761 registros históricos ya fusionados** (97 de BD_BI_TFM + 2.664 de urban-mobility-analytics1), con varios bugs de los repos originales corregidos en el proceso (ver `INTEGRATION_NOTES.md`)

---

## Arquitectura

```
                    ┌───────────────┐        ┌───────────────┐
                    │  ORSClient    │  ó     │  TomTomClient │   (DATA_SOURCE en .env)
                    └───────┬───────┘        └───────┬───────┘
                            └───────────┬────────────┘
                                        ▼
                              WeatherClient (OpenWeather)
                                        │
                                        ▼
                              src/collector.py (DataCollector)
                                        │
              ┌─────────────────────────┼─────────────────────────┐
              ▼                         ▼                         ▼
   data/raw/route_weather_    data/mobility.db          TimescaleDB (traffic_trips)
   data.csv (histórico crudo)  (route_measurements)      ← capa de PRODUCCIÓN / BI
              │                         │
              │                         ▼
              │              ┌─────────────────────┐
              │              │  Bronze → Silver →   │  (automático cada ciclo,
              │              │  Gold (medallion)    │   src/data_warehouse/*)
              │              └──────────┬───────────┘
              │                         ▼
              │              gold_route_kpis / gold_route_rankings
              │                         │
              ▼                         ▼
   src/analytics.py, src/models/*   streamlit_app/app.py
   (tendencias, ML, predicción)     (Executive / Operations / Analyst)
```

---

## Estructura del proyecto

```
BD_BI_TFM/
├── data/
│   ├── raw/
│   │   ├── route_weather_data.csv              ← histórico fusionado (esquema unificado)
│   │   ├── legacy_ors_traffic_weather_data.csv  ← CSV original de BD_BI_TFM, sin tocar
│   │   └── legacy_tomtom_route_weather_data.csv ← CSV original de urban-mobility, sin tocar
│   ├── processed/                               ← salidas de limpieza (BD_BI_TFM)
│   └── mobility.db                              ← SQLite: route_measurements + bronze/silver/gold
├── init/
│   └── 01_init.sql               ← esquema de TimescaleDB (tabla traffic_trips + continuous aggregate)
├── src/
│   ├── config.py                 ← claves de API, DATA_SOURCE, config de TimescaleDB
│   ├── locations.py              ← ubicaciones y las 12 rutas fusionadas
│   ├── ors_client.py             ← cliente OpenRouteService (nuevo, extraído del script original)
│   ├── tomtom_client.py          ← cliente TomTom
│   ├── weather_client.py         ← cliente OpenWeather (con cache)
│   ├── database.py               ← capa CSV + SQLite + TimescaleDB (esquema con bug de clima corregido)
│   ├── collector.py              ← orquestador: recolecta y guarda en las 3 capas + dispara medallion
│   ├── route_extraction.py       ← CLI del collector (--interval, --source, --no-timescale, --no-medallion)
│   ├── migration.py              ← migra CSV → SQLite
│   ├── timescale_migration.py    ← backfill de CSV histórico → TimescaleDB
│   ├── run_medallion_pipeline.py ← backfill manual de Bronze/Silver/Gold sobre todo el histórico
│   ├── analytics/                ← paquete: tendencias, impacto del clima, consistencia, series de tiempo, causal
│   ├── data_warehouse/           ← Bronze / Silver / Gold (arquitectura medallion)
│   ├── models/                   ← RandomForest + Ensemble (XGBoost/GradientBoosting/Exp. Smoothing)
│   ├── predictor.py              ← orquesta entrenamiento/predicción por ruta
│   └── api.py                    ← API REST opcional (FastAPI) sobre analytics/predicciones
├── streamlit_app/
│   ├── app.py                    ← entrypoint activo: selector Executive / Operations / Analyst
│   ├── dashboards/                ← las 3 vistas por rol
│   └── legacy_reference/          ← dashboards de los repos originales, NO activos (ver más abajo)
├── tests/                        ← pytest (locations, database, config, analytics, ensemble, time series)
├── tools/
│   └── merge_legacy_data.py      ← script (ya ejecutado) que generó el histórico fusionado
├── docs/                         ← documentación heredada de urban-mobility-analytics1 (API, research paper)
├── .github/workflows/tests.yml   ← CI: tests + lint + validación de docker-compose.yml
├── docker-compose.yml            ← TimescaleDB + pgAdmin + collector + dashboard
├── Dockerfile                    ← imagen compartida por collector y dashboard
├── requirements.txt / requirements-dev.txt
├── .env / .env.example
├── INTEGRATION_NOTES.md          ← qué se fusionó, qué bugs se encontraron y cómo se corrigieron
└── README.md                     ← este archivo
```

---

## Inicio rápido (Docker — recomendado)

```bash
# 1. Las claves de API reales ya están en .env (migradas de ambos repos).
#    Si quieres usar las tuyas propias, edítalo, o copia .env.example.

# 2. Levantar todo el stack
docker compose up -d

# 3. Verificar que los contenedores están corriendo
docker compose ps
```

| Contenedor | Descripción | URL |
|---|---|---|
| `movilidad-db` | TimescaleDB (capa de producción) | `127.0.0.1:5433` (solo local — puerto interno sigue siendo 5432) |
| `movilidad-pgadmin` | Administrador web de la DB | http://localhost:8080 (`admin@tfm.com` / ver `.env` → `PGADMIN_PASSWORD`) |
| `movilidad-collector` | Recolecta cada 120s (ORS o TomTom según `.env`) | — |
| `movilidad-streamlit` | Dashboard (Executive / Operations / Analyst) | http://localhost:8501 (único expuesto a la red) |
| `movilidad-sqlite-web` | Visualizador SQL para `data/mobility.db` (SQLite) | http://localhost:8082 (solo local, ver `.env` → `SQLITE_WEB_PASSWORD`) |

Desde la versión endurecida para servidor real (ver `PRODUCTION.md`), `timescaledb`/`pgadmin`/`sqlite-web` solo escuchan en `127.0.0.1` — alcanzables desde tu propia máquina, no desde el resto de la red. Solo `dashboard` se expone hacia afuera.

El histórico (2.761 registros) ya viene cargado en `data/mobility.db`, así que el dashboard muestra datos reales desde el primer arranque — no hace falta esperar a que el collector junte datos nuevos.

Para cargar también el histórico en TimescaleDB (opcional, la tabla `traffic_trips` empieza vacía):

```bash
docker compose exec collector python -m src.timescale_migration
```

---

## Acceso remoto para el equipo (Tailscale)

`movilidad-streamlit` es el único contenedor expuesto en `0.0.0.0:8501` (ver tabla arriba) — TimescaleDB, pgAdmin y sqlite-web quedan atados a `127.0.0.1` a propósito, solo alcanzables desde la máquina que corre Docker. Para que el resto del equipo vea el dashboard sin exponer nada a internet abierto, usamos [Tailscale](https://tailscale.com) (VPN mesh privada, gratis hasta 6 usuarios con dispositivos ilimitados por usuario).

> Esto es para **acceso del equipo durante el desarrollo**, no para exponer el proyecto a internet público — para eso, ver `PRODUCTION.md`.

### Lado administrador (quien corre `docker compose up`)

1. Instalar Tailscale y crear cuenta (con GitHub o Google): https://tailscale.com/download
2. Confirmar que el dashboard sigue expuesto en todas las interfaces, no solo en local:
   ```bash
   docker compose ps
   # movilidad-streamlit debe mostrar 0.0.0.0:8501->8501/tcp
   # (si dice 127.0.0.1:8501->8501/tcp, solo este equipo puede verlo)
   ```
3. Invitar a cada integrante del equipo desde el admin console, **con su correo real** — no compartir esta cuenta entre todos: https://login.tailscale.com/admin/users
4. Obtener la IP de Tailscale de este equipo para compartirla con el resto:
   ```powershell
   tailscale status
   # la IP propia es del tipo 100.x.x.x
   ```
5. *(Opcional)* Si más adelante hace falta compartir también pgAdmin o sqlite-web, restringir por dispositivo vía ACL (https://login.tailscale.com/admin/acls) en vez de exponerlos a todo el tailnet sin filtro.

### Lado de quien se une al equipo

1. Instalar Tailscale en el propio dispositivo: https://tailscale.com/download
2. **Aceptar la invitación** que llega al correo (o el link que comparta el administrador) — no crear una cuenta propia por separado. Este es el error más común: si te logueas con una cuenta que nunca fue invitada, quedas en una red privada distinta a la del resto del equipo, y nunca vas a poder ver su equipo aunque todo lo demás esté bien configurado.
3. Confirmar que el equipo del administrador aparece como peer:
   ```
   tailscale status
   ```
4. Abrir el dashboard en el navegador, con la IP de Tailscale que compartió el administrador:
   ```
   http://100.x.x.x:8501
   ```

### Problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| "This site can't be reached" desde otro dispositivo, pero `localhost:8501` sí funciona en el host | Quien se une nunca aceptó la invitación — está en un tailnet distinto | Correr `tailscale status` en el dispositivo que se une: si el host no aparece como peer, revisar la invitación pendiente en el admin console |
| Falla incluso con la IP de Tailscale, probado desde el propio host | El puerto del dashboard quedó bindeado a `127.0.0.1` en vez de `0.0.0.0` | Revisar `docker compose ps` y la sección `ports` del servicio `dashboard` en `docker-compose.yml` |
| Funciona con la IP de Tailscale pero no con el nombre del equipo | MagicDNS no resolvió el hostname | Usar la IP `100.x.x.x` directamente, o correr `tailscale status` para confirmar el nombre exacto asignado |

---

## Uso local (sin Docker)

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env      # y completa tus claves, o usa el .env ya incluido

# Recolección puntual
python -m src.route_extraction

# Recolección continua cada 2 minutos (una sola fuente)
python -m src.route_extraction --interval 120

# Forzar una fuente para una corrida puntual
python -m src.route_extraction --source tomtom

# Modo híbrido: ORS + TomTom en paralelo, cada uno en su propio intervalo,
# ambos dentro de su cuota gratuita mensual (ver PRODUCTION.md) — es lo
# que usa docker-compose.yml por defecto
python -m src.route_extraction --hybrid --ors-interval 15 --tomtom-interval 27

# Dashboard
streamlit run streamlit_app/app.py
```

---

## Fuentes de datos: ORS vs TomTom vs HERE

| Característica | **ORS** | **TomTom** | **HERE** |
|---|:---:|:---:|:---:|
| Tráfico en tiempo real | ❌ | ✅ | ✅ |
| Tiempo de viaje **sin** tráfico (`no_traffic_time_min`) | — (no aplica) | ✅ | ✅ |
| Retraso por tráfico (`traffic_delay_min`) | ❌ | ✅ | ✅ |
| Velocidad promedio | Calculada por nosotros | ✅ nativa | ✅ nativa |
| Geometría de la ruta (polyline) | ✅ | ✅ | ✅ |
| Requiere tarjeta de crédito (plan free) | ❌ | ❌ | ❌ |
| Autenticación | API key simple | API key simple | API key simple |
| Cuota mensual gratis — routing base | 40.000 | 20.000 | 30.000 |
| Cuota diaria gratis | 2.500/día | — (solo mensual) | No confirmado por separado |
| Cuota mensual gratis **con tráfico real** | — (no tiene) | 20.000 (mismo pool) | ⚠️ **Pendiente de confirmar** — quizás 30.000, quizás solo 5.000 (ver nota abajo) |
| Límite de ráfaga (peticiones/seg) | No es el cuello de botella | No lo investigamos a fondo | ✅ 10 req/s confirmado |
| Intervalo mínimo viable (12 rutas) | ~13 min | ~26 min | 3-5 min si es 30k, ~105 min si es 5k |
| Integrado en el proyecto ahora mismo | ✅ `ORSClient` | ✅ `TomTomClient` | ⏳ Pendiente de la confirmación de cuota |
| Rol actual en el híbrido | Línea base cada 15 min | Foto real cada 27 min | — |
| Filas en el histórico ya recolectado | 97+ | 2.664+ | 0 |

**Nota sobre HERE:** en el dashboard de precios de la cuenta, `Real-Time Traffic`
(5.000/mes gratis) resultó ser un producto separado (la HERE Traffic API,
`data.traffic.hereapi.com`, para mapas de calor de tráfico por zona) que no
se dispara al llamar la Routing API — no debería aplicarnos. Pero
`Time Aware Routing` tiene exactamente los mismos tramos de precio, y no
hay documentación clara de si se activa al usar el parámetro
`departureTime` (necesario para tráfico en tiempo real) dentro de una
llamada de routing normal. Se está esperando ~2 días a que el dashboard
de uso de HERE refleje una llamada de prueba para confirmarlo antes de
integrarlo — con cobro real de por medio, no vale la pena asumir.

Todas escriben (o escribirían, en el caso de HERE) al mismo esquema unificado (`src/database.py`), así que agregar o cambiar de fuente no rompe nada aguas abajo (analytics, ML, dashboards).

## Modo híbrido (ambas fuentes en paralelo)

Con 12 rutas, ninguna de las dos APIs gratuitas alcanza para recolectar
cada pocos minutos sin agotar su cuota mensual:

| Fuente | Cuota real | Intervalo mínimo con 12 rutas |
|---|---|---|
| ORS | 2.500/día y 40.000/mes | ~13 min (manda el límite mensual) |
| TomTom | 20.000/mes | ~26 min |

El **modo híbrido** (`--hybrid`, el que usa `docker-compose.yml` por
defecto) corre ambas fuentes **a la vez, cada una en su propio reloj**:
ORS cada 15 min (línea base densa, sin tráfico en tiempo real) + TomTom
cada 27 min (fotos periódicas de tráfico real) — dentro del presupuesto
mensual de ambas, con margen. No son ciclos alternados: cada fuente tiene
su propio temporizador independiente (`src/collector.py::HybridScheduler`).

```bash
python -m src.route_extraction --hybrid --ors-interval 15 --tomtom-interval 27
```

**Nota metodológica para el TFM:** con esto, el dataset resultante tiene
densidad y calidad mixtas — la mayoría de las mediciones (ORS) no tienen
`traffic_delay_min` real, y solo las de TomTom (más escasas) sí. Vale la
pena documentarlo explícitamente como decisión de diseño (línea base de
alta frecuencia + muestreo periódico de tráfico real), no como una
inconsistencia de los datos.

---

## Variables de entorno

Ver `.env.example` para la plantilla completa. Resumen:

| Variable | Para qué | Default |
|---|---|---|
| `DATA_SOURCE` | `ors` o `tomtom` | `ors` |
| `ORS_API_KEY` | OpenRouteService | — |
| `TOMTOM_API_KEY` | TomTom (solo si `DATA_SOURCE=tomtom`) | — |
| `OPENWEATHER_API_KEY` | Clima (siempre necesaria) | — |
| `PGHOST` / `PGPORT` / `PGDATABASE` / `PGUSER` / `PGPASSWORD` | TimescaleDB | `localhost` / `5432` / `movilidad_urbana` / `postgres` / `tfm_password` |

Dentro de Docker, `docker-compose.yml` sobreescribe `PGHOST=timescaledb` automáticamente (los servicios se resuelven por nombre en la red interna).

---

## Qué necesitas instalar para cada cosa

El proyecto separa dependencias en `requirements.txt` (lo mínimo para correr el collector y el dashboard) y `requirements-dev.txt` (todo lo anterior + testing, linting, API, ML opcional). Esta tabla sale de auditar cada `import` real del código contra ambos archivos:

| Quiero... | Instalar | Paquetes clave |
|---|---|---|
| Correr el collector y el dashboard | `pip install -r requirements.txt` | `pandas`, `requests`, `streamlit`, `plotly`, `scikit-learn`, `scipy`, `statsmodels`, `psycopg2-binary` |
| Correr los tests (`pytest tests/`) | `pip install -r requirements-dev.txt` | `pytest`, `pytest-cov`, `pytest-xdist` |
| Lint / formato (igual que el CI) | incluido en `requirements-dev.txt` | `flake8`, `pylint`, `black`, `isort`, `mypy` |
| Levantar la API REST (`src/api.py`) | incluido en `requirements-dev.txt` | `fastapi`, `uvicorn`, `pydantic` |
| Ensemble ML completo (XGBoost + Exponential Smoothing) | incluido en `requirements-dev.txt` | `xgboost`, `prophet` — **opcionales**: `src/models/ensemble_predictor.py` los detecta con `try/except`; sin ellos, el ensemble usa solo Random Forest + Gradient Boosting |
| Generar documentación con Sphinx | incluido en `requirements-dev.txt` | `sphinx`, `sphinx-rtd-theme` |
| Notebooks / exploración | incluido en `requirements-dev.txt` | `ipython`, `jupyter`, `notebook` |
| Profiling | incluido en `requirements-dev.txt` | `py-spy`, `memory-profiler` |

**Cambios que hice al auditar `requirements-dev.txt` original** (de urban-mobility-analytics1):
- **Faltaban `xgboost` y `prophet`**: `ensemble_predictor.py` ya los importaba con `try/except`, pero no estaban declarados en ningún requirements — el ensemble se degradaba en silencio a solo 2 de 4 modelos. Agregados.
- **`dowhy` no lo usa ningún archivo del proyecto** (ni siquiera `causal_analysis.py`, que implementa su propia inferencia causal con `sklearn`/`scipy`). Lo dejé comentado como posible extensión futura, no como dependencia real.
- **`pydeck` estaba en `requirements.txt` pero nada lo importa** (el mapa usa `st.map()` nativo de Streamlit, no pydeck). Eliminado.
- Agregado `urllib3` explícito en `requirements.txt`: `ors_client.py`, `tomtom_client.py` y `weather_client.py` lo importan directamente (`from urllib3.util.retry import Retry`), no solo como dependencia transitiva de `requests`.

---

## Base de datos

### TimescaleDB — capa de producción (`traffic_trips`)

Esquema simplificado pensado para BI: `datetime, origin, destination, distance_km, duration_min, temperature, humidity, weather_description, mobility_level, data_source, traffic_delay_min`, con hypertable particionada por tiempo y un continuous aggregate (`trips_hourly`) que se refresca cada hora. Ver `init/01_init.sql`.

### SQLite — capa local / analítica / ML (`data/mobility.db`)

Esquema con **todo** el detalle (clima separado por origen/destino, tráfico, velocidad, polyline). Usado por `src/analytics.py`, los modelos de ML, y los 3 dashboards.

### Pipeline medallion (Bronze → Silver → Gold)

Se dispara automáticamente en cada ciclo del collector (`src/collector.py::_run_incremental_medallion`), solo sobre los registros nuevos de ese ciclo (no reprocesa todo el histórico, por rendimiento). Alimenta `gold_route_kpis` / `gold_route_rankings`, que es lo que lee el dashboard **Executive**.

Para reprocesar todo el histórico desde cero:

```bash
python -m src.run_medallion_pipeline
```

Ver `INTEGRATION_NOTES.md` para el detalle de los bugs que tenía este pipeline en el repo original (mezcla de nombres de columnas, funciones SQL no soportadas por SQLite, restricciones `UNIQUE` faltantes) y cómo se corrigieron.

---

## Dashboards disponibles

**`streamlit_app/app.py`** (activo, arranca con `docker compose up` / `streamlit run streamlit_app/app.py`):
selector lateral entre 3 vistas por rol —

- **Executive**: KPIs del sistema, mejores/peores rutas, tendencia de 30 días (lee de `gold_route_kpis`)
- **Operations**: monitoreo en tiempo real y alertas
- **Analyst**: exploración de datos y análisis de series de tiempo (incluye un tab **SQL Query** de solo lectura sobre `data/mobility.db`)

## Consultar la base de datos con SQL

Dos formas, según qué necesites:

- **`streamlit_app/app.py` → Analyst → tab "SQL Query"**: rápido, sin salir del dashboard, forzado a **solo lectura** a nivel del motor SQLite (`mode=ro` — cualquier intento de `INSERT`/`UPDATE`/`DELETE`/`DROP` falla, no solo se filtra por texto). Trae ejemplos precargados.
- **`movilidad-sqlite-web`** (http://localhost:8082): equivalente a pgAdmin pero para SQLite — navega tablas, exporta JSON/CSV, y también permite **editar y borrar filas** desde el navegador. Úsalo con cuidado mientras el collector escribe cada 2 minutos en paralelo.

Para la capa de producción (TimescaleDB), sigue usando **pgAdmin** (http://localhost:8080).

**`streamlit_app/legacy_reference/`** (no activos, se conservan como referencia):

- `app_advanced.py`: el dashboard original de urban-mobility-analytics1 — vista de una sola ruta con mapa, comparación de clima origen/destino, 4 pestañas y exportación. Sigue siendo funcional standalone: `streamlit run streamlit_app/legacy_reference/app_advanced.py`
- `app_classic.py`: el dashboard original de BD_BI_TFM. Apunta a `legacy_ors_traffic_weather_data.csv` (el CSV original, no al histórico fusionado)

---

## Testing y CI

```bash
pytest tests/ -v --cov=src --cov-report=term
```

`.github/workflows/tests.yml` corre en cada push/PR a `main`/`develop`:
1. **`test`**: pytest en Python 3.10/3.11/3.12 + un chequeo explícito de que `src.analytics` (módulo) y `src.analytics.time_series_analysis`/`causal_analysis` (submódulos) importan correctamente — regresión directa contra un bug de estructura que encontramos durante la fusión (ver `INTEGRATION_NOTES.md`)
2. **`docker-compose-lint`**: valida `docker-compose.yml` con `docker compose config`
3. **`lint`**: `black` + `isort`

---

## Documentación adicional

- **`INTEGRATION_NOTES.md`** — qué se fusionó de cada repo, y el detalle completo de cada bug encontrado y corregido durante la integración
- **`PRODUCTION.md`** — endurecimiento para servidor real: usuarios no-root, healthchecks, límites de recursos, contraseñas, puertos, y el checklist si esto sale a internet público
- **`docs/API.md`** — documentación de la API REST opcional (`src/api.py`)
- **`docs/research_paper/README.md`** — paper de investigación heredado de urban-mobility-analytics1 (ensemble ML, causal inference, arquitectura medallion)
