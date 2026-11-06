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

- **Dos fuentes de tráfico intercambiables** (`DATA_SOURCE=ors` o `tomtom` en `.env`), corriendo en paralelo en modo híbrido
- **Dos capas de almacenamiento en paralelo**: TimescaleDB (producción/BI) + SQLite (local, analítica y ML)
- **Pipeline Bronze → Silver → Gold automático** en cada ciclo de recolección, alimentando un dashboard Executive con KPIs reales
- **POIs de infraestructura urbana** (escuelas, hospitales, restauración y bares, ocio, deporte, centros comerciales y comercios) vía Overpass API (OpenStreetMap, sin key), refrescados semanalmente y visualizados en el dashboard **Maps** — con **Foursquare Places API como fuente opcional complementaria** (categorización de negocio más rica, y búsqueda a lo largo de cada ruta, no solo en sus 7 extremos; requiere `FOURSQUARE_API_KEY`, ver `poi-collector-foursquare`)
- **Demografía por zona** (población) vía **Google Data Commons** (opcional, requiere `DATACOMMONS_API_KEY`) — pensada para transicionar a otras ciudades sin tocar código: resuelve cada lugar **por nombre** la primera vez y cachea el DCID resultante, ver `src/demographics_extraction.py`
- **78.500+ registros históricos y creciendo** (48.513 vía ORS + 30.012 vía TomTom al 6-nov-2026 — ver `data/mobility.db` para el conteo actual), con varios bugs de los repos originales corregidos en el proceso (ver `INTEGRATION_NOTES.md`)

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
   src/analytics/, src/models/*     streamlit_app/app.py
   (tendencias, ML, predicción)     (Executive / Operations / Analyst / Maps / Recomendación)

              ┌───────────────────────────────────────────────────┐
              │  OverpassClient (OSM, sin key) — src/poi_client.py │
              │  refresco semanal, independiente del loop de       │
              │  tráfico — src/poi_extraction.py                   │
              └──────────────────────┬──────────────────────────┘
                                     ▼
                        data/mobility.db (tabla pois)
                                     │
                                     ▼
                     streamlit_app/dashboards/maps_dashboard.py
                        (overlay de POIs sobre el mapa de rutas)
```

---

## Estructura del proyecto

```
BD_BI_TFM/
├── data/
│   ├── raw/
│   │   ├── route_weather_data.csv              ← histórico fusionado (esquema unificado), ~78.500 filas al 6-nov-2026 y creciendo
│   │   ├── legacy_ors_traffic_weather_data.csv  ← CSV original de BD_BI_TFM, sin tocar
│   │   ├── legacy_tomtom_route_weather_data.csv ← CSV original de urban-mobility, sin tocar
│   │   └── traffic_weather_data.csv             ← ⚠️ huérfano: solo lo generaba api_extraction.py (no usado, ver abajo)
│   ├── processed/                               ← ⚠️ huérfano: solo lo generaba cleaning.py (no usado, ver abajo); 2 archivos de bytes, no reflejan el histórico real
│   └── mobility.db                              ← SQLite: route_measurements + pois + bronze/silver/gold
├── init/
│   └── 01_init.sql               ← esquema de TimescaleDB (tabla traffic_trips + continuous aggregate)
├── src/
│   ├── config.py                 ← claves de API, DATA_SOURCE, config de TimescaleDB
│   ├── locations.py              ← ubicaciones y las 12 rutas fusionadas
│   ├── ors_client.py             ← cliente OpenRouteService (nuevo, extraído del script original)
│   ├── tomtom_client.py          ← cliente TomTom
│   ├── weather_client.py         ← cliente OpenWeather (con cache)
│   ├── poi_client.py             ← cliente Overpass API (OSM) para POIs — sin API key
│   ├── poi_extraction.py         ← CLI del recolector de POIs (--interval-hours, default semanal)
│   ├── foursquare_client.py      ← cliente Foursquare Places API — COMPLEMENTA poi_client.py (todas las categorías, sin excluir nada; búsqueda en las 7 zonas + puntos intermedios a lo largo de cada ruta)
│   ├── poi_extraction_foursquare.py ← CLI del recolector de Foursquare (opcional, requiere FOURSQUARE_API_KEY)
│   ├── demographics_client.py       ← cliente Google Data Commons — población por zona, resuelve por NOMBRE (transición a otras ciudades sin tocar código)
│   ├── demographics_extraction.py   ← CLI del recolector de demografía (opcional, requiere DATACOMMONS_API_KEY; sin servicio Docker propio — correr a mano, la población casi no cambia)
│   ├── database.py               ← capa CSV + SQLite + TimescaleDB (esquema con bug de clima corregido)
│   ├── collector.py               ← orquestador: recolecta y guarda en las 3 capas + dispara medallion
│   ├── route_extraction.py       ← CLI del collector (--interval, --source, --hybrid, --no-timescale, --no-medallion)
│   ├── migration.py              ← migra CSV → SQLite
│   ├── timescale_migration.py    ← backfill de CSV histórico → TimescaleDB
│   ├── run_medallion_pipeline.py ← backfill manual de Bronze/Silver/Gold sobre todo el histórico
│   ├── analytics/                ← paquete: tendencias, impacto del clima, consistencia, series de tiempo, causal
│   ├── data_warehouse/           ← Bronze / Silver / Gold (arquitectura medallion)
│   ├── models/                   ← RandomForest + Ensemble (XGBoost/RandomForest/GradientBoosting; Prophet solo para el pronóstico semanal)
│   ├── predictor.py              ← orquesta entrenamiento/predicción por ruta
│   ├── api.py                    ← API REST opcional (FastAPI) sobre analytics/predicciones
│   └── api_extraction.py, cleaning.py, scheduler.py
│                                  ← ⚠️ NO SE USAN: script original pre-fusión de BD_BI_TFM.
│                                     `scheduler.py` llamaba a `api_extraction.py` vía os.system();
│                                     ambos fueron reemplazados por collector.py + route_extraction.py
│                                     (confirmado en el propio docker-compose.yml). Ningún dashboard,
│                                     script activo ni docker-compose los invoca. Candidatos a borrar.
├── streamlit_app/
│   ├── app.py                    ← entrypoint activo: selector Executive / Operations / Analyst / Maps / Recomendación
│   ├── dashboards/
│   │   ├── executive_dashboard.py
│   │   ├── operations_dashboard.py
│   │   ├── analyst_dashboard.py            ← incluye, en su pestaña Model Performance, predictive_modeling_dashboard (ver abajo)
│   │   ├── predictive_modeling_dashboard.py ← NO es un dashboard aparte: se renderiza dentro de la pestaña Model Performance de Analyst
│   │   ├── maps_dashboard.py               ← mapa de rutas (Plotly Scattermapbox) + overlay de POIs
│   │   └── recommendation_dashboard.py     ← ¿dónde abrir un negocio? — interfaz de src/location_scoring.py para el usuario final
│   └── legacy_reference/          ← dashboards de los repos originales, NO activos (ver más abajo)
├── tests/                        ← pytest (locations, database, config, analytics, ensemble, time series)
├── tools/
│   ├── merge_legacy_data.py      ← script (ya ejecutado) que generó el histórico fusionado
│   ├── compare_overpass_foursquare.py ← (solo lectura) mide qué tan completo es OpenStreetMap frente a Foursquare, emparejando por nombre y distancia
│   ├── check_collection_gaps.py  ← (solo lectura) detecta y mide huecos en la recolección de tráfico (cuándo estuvo apagado el stack)
├── docs/                         ← documentación heredada de urban-mobility-analytics1 (API, research paper)
├── .github/workflows/tests.yml   ← CI: tests + lint + validación de docker-compose.yml
├── collect.py                    ← wrapper de conveniencia: `python collect.py` == `python -m src.route_extraction`├── business_type_classifier.py ← (src/) texto libre en español -> categoría de Overpass (para el sistema de recomendación)
├── location_scoring.py       ← (src/) motor de puntuación (MCDA) de zonas para dónde abrir un negocio
├── docker-compose.yml            ← TimescaleDB + pgAdmin + collector + poi-collector + dashboard + sqlite-web
├── Dockerfile                    ← imagen compartida por collector, poi-collector y dashboard
├── requirements.txt / requirements-dev.txt
├── .env / .env.example
├── INTEGRATION_NOTES.md          ← qué se fusionó, qué bugs se encontraron y cómo se corrigieron
└── README.md                     ← este archivo
```

---

## Inicio rápido (Docker — recomendado)

### Prerrequisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado y **corriendo** (Windows, Mac o Linux).
- Haber clonado este repositorio.

### 1. Configurar las variables de entorno

`.env` está en `.gitignore` (nunca se sube al repo, porque tiene API keys y contraseñas) — así que un clon nuevo del repositorio **no lo trae**. Hay que crearlo a partir de la plantilla:

```bash
# Windows (PowerShell)
Copy-Item .env.example .env

# Mac/Linux
cp .env.example .env
```

Después, abre `.env` y completa al menos estas dos claves (las demás tienen defaults que funcionan sin tocar nada):

- `ORS_API_KEY` — gratis en https://openrouteservice.org/dev/#/signup
- `OPENWEATHER_API_KEY` — gratis en https://openweathermap.org/api

(`TOMTOM_API_KEY` y `FOURSQUARE_API_KEY` son opcionales — solo hacen falta si vas a usar esas fuentes específicas.)

### 2. Levantar el stack

```bash
docker compose up -d --build
```

La primera vez tarda varios minutos (construye las imágenes). Las siguientes veces es mucho más rápido.

### 3. Verificar que todo levantó bien

```bash
docker compose ps
```

Todos los contenedores deberían aparecer como `Up` (o `Up (healthy)`). Si alguno no lo está, revisa sus logs puntuales:

```bash
docker compose logs -f nombre_del_servicio   # ej: collector, dashboard, timescaledb
```

### 4. Abrir el dashboard

http://localhost:8501 — si ya tienes el histórico en `data/mobility.db` (ver más abajo), verás datos reales desde el primer arranque; en un clon limpio, el dashboard empieza vacío y se va llenando con cada ciclo del collector.

| Contenedor | Descripción | URL |
|---|---|---|
| `movilidad-db` | TimescaleDB (capa de producción) | `127.0.0.1:5433` (solo local — puerto interno sigue siendo 5432) |
| `movilidad-pgadmin` | Administrador web de la DB | http://localhost:8080 (`admin@tfm.com` / ver `.env` → `PGADMIN_PASSWORD`) |
| `movilidad-collector` | Recolecta tráfico/clima en modo híbrido (ORS cada 15 min + TomTom cada 27 min) | — |
| `movilidad-poi-collector` | Recolecta POIs (escuelas, hospitales, restauración y bares, ocio, deporte, centros comerciales, comercios y oficinas) vía Overpass API — sin API key, refresco cada 168h (semanal) | — |
| `movilidad-poi-collector-foursquare` *(opcional)* | Complementa `poi-collector`: trae TODOS los POIs que devuelva Foursquare (restaurant/retail/services/entertainment/school/health/mall/other — sin excluir nada), buscando en las 7 zonas más ~20 puntos intermedios a lo largo de cada ruta (~27 llamadas/refresco, ~117/mes — 23% del límite gratis). **No arranca con un `docker compose up` normal** — requiere `FOURSQUARE_API_KEY` en `.env` y correrlo explícito: `docker compose --profile foursquare up -d poi-collector-foursquare` | — |
| `movilidad-streamlit` | Dashboard (Executive / Operations / Analyst / Maps / Recomendación) | http://localhost:8501 (único expuesto a la red) |
| `movilidad-sqlite-web` | Visualizador SQL para `data/mobility.db` (SQLite) | http://localhost:8082 (solo local, ver `.env` → `SQLITE_WEB_PASSWORD`) |

Desde la versión endurecida para servidor real (ver `PRODUCTION.md`), `timescaledb`/`pgadmin`/`sqlite-web` solo escuchan en `127.0.0.1` — alcanzables desde tu propia máquina, no desde el resto de la red. Solo `dashboard` se expone hacia afuera.

**El histórico NO viene en el repositorio.** `data/mobility.db` y `data/raw/route_weather_data.csv` están en `.gitignore` (crecen con cada ciclo del collector y pesan cientos de MB), así que un clon limpio los **no trae**: el dashboard arranca vacío y se llena a medida que el collector guarda datos. En la máquina donde se ha venido recolectando, esos archivos sí existen (78.500+ registros al 6-nov-2026 y creciendo — `SELECT COUNT(*) FROM route_measurements` para el número exacto).

Para trabajar con el histórico existente en otra máquina, copia a mano `data/mobility.db` (y, si lo necesitas, `data/raw/route_weather_data.csv`) desde la máquina que lo recolectó, con el stack apagado (`docker compose down`) para no copiar la base a mitad de una escritura. Lo único del histórico que sí está versionado son los CSV `data/raw/legacy_*` (snapshots fijos de los repos originales).

Para cargar también el histórico en TimescaleDB (opcional, la tabla `traffic_trips` empieza vacía):

```bash
docker compose exec collector python -m src.timescale_migration
```

### Apagar el stack

```bash
docker compose down
```

Esto detiene y elimina los contenedores **sin tocar los datos** (los volúmenes de TimescaleDB y `data/mobility.db` persisten). Nunca agregues `-v` a menos que quieras borrar todo el histórico a propósito.

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
| "This site can't be reached" desde otro dispositivo, pero `localhost:8501` sí funciona en el host | Quien se une inició sesión con una cuenta que nunca fue invitada — está en una tailnet distinta. **Confirmado dos veces con Mac**: el cliente ofrece "Sign in with Apple" de forma muy visible, y eso crea/entra a una tailnet personal, no a la del equipo | Correr `tailscale status` en el dispositivo que se une: si el host no aparece como peer, cerrar sesión (menú de Tailscale → Settings → Log out) y volver a entrar con el **mismo correo/proveedor exacto** con el que se mandó la invitación — nunca "Sign in with Apple" |
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

## Fuentes de datos: ORS vs TomTom

| Característica | **ORS** | **TomTom** |
|---|:---:|:---:|
| Tráfico en tiempo real | ❌ | ✅ |
| Tiempo de viaje **sin** tráfico (`no_traffic_time_min`) | — (no aplica) | ✅ |
| Retraso por tráfico (`traffic_delay_min`) | ❌ | ✅ |
| Velocidad promedio | Calculada por nosotros | ✅ nativa |
| Geometría de la ruta (polyline) | ✅ | ✅ |
| Requiere tarjeta de crédito (plan free) | ❌ | ❌ |
| Autenticación | API key simple | API key simple |
| Cuota mensual gratis — routing base | 40.000 | 20.000 |
| Cuota diaria gratis | 2.500/día | — (solo mensual) |
| Cuota mensual gratis **con tráfico real** | — (no tiene) | 20.000 (mismo pool) |
| Límite de ráfaga (peticiones/seg) | No es el cuello de botella | No lo investigamos a fondo |
| Intervalo mínimo viable (12 rutas) | ~13 min | ~26 min |
| Integrado en el proyecto ahora mismo | ✅ `ORSClient` | ✅ `TomTomClient` |
| Rol actual en el híbrido | Línea base cada 15 min | Foto real cada 27 min |
| Filas en el histórico ya recolectado (al 6-nov-2026) | 48.513+ | 30.012+ |

Ambas escriben al mismo esquema unificado (`src/database.py`), así que agregar o cambiar de fuente no rompe nada aguas abajo (analytics, ML, dashboards).

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
| `FOURSQUARE_API_KEY` | Foursquare Places API (opcional — solo para `poi-collector-foursquare`) | — |
| `DATACOMMONS_API_KEY` | Google Data Commons (opcional — solo para `src/demographics_extraction.py`, sin servicio Docker propio) | — |
| `PGHOST` / `PGPORT` / `PGDATABASE` / `PGUSER` / `PGPASSWORD` | TimescaleDB | `localhost` / `5432` / `movilidad_urbana` / `postgres` / `tfm_password` |

Dentro de Docker, `docker-compose.yml` sobreescribe `PGHOST=timescaledb` automáticamente (los servicios se resuelven por nombre en la red interna).

---

## Qué necesitas instalar para cada cosa

El proyecto separa dependencias en `requirements.txt` (lo mínimo para correr el collector y el dashboard) y `requirements-dev.txt` (todo lo anterior + testing, linting, API, ML opcional). Esta tabla sale de auditar cada `import` real del código contra ambos archivos:

| Quiero... | Instalar | Paquetes clave |
|---|---|---|
| Correr el collector, el poi-collector y el dashboard | `pip install -r requirements.txt` | `pandas`, `requests`, `python-dotenv`, `streamlit`, `plotly`, `scikit-learn`, `scipy`, `statsmodels`, `psycopg2-binary` |
| Correr los tests (`pytest tests/`) | `pip install -r requirements-dev.txt` | `pytest`, `pytest-cov`, `pytest-xdist` |
| Lint / formato (igual que el CI) | incluido en `requirements-dev.txt` | `flake8`, `pylint`, `black`, `isort`, `mypy` |
| Levantar la API REST (`src/api.py`) | incluido en `requirements-dev.txt` | `fastapi`, `uvicorn`, `pydantic` |
| Ensemble ML completo (XGBoost + Random Forest + Gradient Boosting) y pronóstico semanal | incluido en `requirements-dev.txt` | `xgboost`, `prophet` — **opcionales**: `src/models/ensemble_predictor.py` los detecta con `try/except`; sin `xgboost`, el ensemble usa solo Random Forest + Gradient Boosting; `prophet` solo alimenta `forecast_week_ahead()` (sin él, ese pronóstico devuelve un error explícito) |
| Demografía por zona (`src/demographics_extraction.py`, opcional) | incluido en `requirements-dev.txt` | `datacommons-client` |
| Generar documentación con Sphinx | incluido en `requirements-dev.txt` | `sphinx`, `sphinx-rtd-theme` |
| Notebooks / exploración | incluido en `requirements-dev.txt` | `ipython`, `jupyter`, `notebook` |
| Profiling | incluido en `requirements-dev.txt` | `py-spy`, `memory-profiler` |

**Cambios que hice al auditar `requirements-dev.txt` original** (de urban-mobility-analytics1):
- **Faltaban `xgboost` y `prophet`**: `ensemble_predictor.py` ya los importaba con `try/except`, pero no estaban declarados en ningún requirements — el ensemble se degradaba en silencio a solo 2 de 4 modelos. Agregados.
- **`dowhy` no lo usa ningún archivo del proyecto** (ni siquiera `causal_analysis.py`, que implementa su propia inferencia causal con `sklearn`/`scipy`). Lo dejé comentado como posible extensión futura, no como dependencia real.
- **`pydeck` estaba en `requirements.txt` pero nada lo importa** (los mapas usan `plotly.graph_objects.Scattermapbox` con estilo `open-street-map` — gratis, sin token — en `maps_dashboard.py`, no pydeck). Eliminado.
- Agregado `urllib3` explícito en `requirements.txt`: `ors_client.py`, `tomtom_client.py` y `weather_client.py` lo importan directamente (`from urllib3.util.retry import Retry`), no solo como dependencia transitiva de `requests`.

---

## Base de datos

### TimescaleDB — capa de producción (`traffic_trips`)

Esquema simplificado pensado para BI: `datetime, origin, destination, distance_km, duration_min, temperature, humidity, weather_description, mobility_level, data_source, traffic_delay_min`, con hypertable particionada por tiempo y un continuous aggregate (`trips_hourly`) que se refresca cada hora. Ver `init/01_init.sql`.

### SQLite — capa local / analítica / ML (`data/mobility.db`)

Esquema con **todo** el detalle (clima separado por origen/destino, tráfico, velocidad, polyline). Usado por el paquete `src/analytics/`, los modelos de ML y los dashboards.

Incluye también la tabla **`pois`** (7 categorías vía Overpass API/OpenStreetMap, `src/poi_client.py`: `school`, `hospital`, `food_drink`, `leisure`, `sport`, `mall`, `business`; la columna `subcategory` guarda el valor del tag de OpenStreetMap que la definió, ej. `restaurant`, `cafe`, `hairdresser`), poblada por el servicio `poi-collector` y consumida por el dashboard **Maps**. A diferencia de `route_measurements`, se actualiza (upsert) en vez de solo insertar, y a un ritmo mucho menor (semanal, no cada minutos).

**Cómo se definen las categorías de Overpass.** `CATEGORY_TAGS` en `src/poi_client.py` es la única fuente de verdad: de ahí salen tanto la query que se envía a Overpass como la clasificación de cada elemento. Su **orden es la prioridad** (gana la primera categoría que matchee; las específicas van antes que `business`). Cada especificación admite `clave`, `clave=valor` o `clave=v1|v2|v3`. Quedan excluidos a propósito `leisure=pitch`, `playground`, `park` y `swimming_pool` (espacios públicos o piscinas privadas, ruido para medir competencia). A diferencia de Foursquare, Overpass no tiene tope de resultados por consulta, así que sus conteos por categoría no se aplanan en zonas densas.

Para poblar las categorías nuevas en una base que ya tenía datos, basta con correr el recolector una vez (los POIs se actualizan por `osm_type`+`osm_id`, sin duplicar):

```powershell
docker compose run --rm -v "${PWD}/src:/app/src" collector python -m src.poi_extraction
```

**Medir qué tan completo es OpenStreetMap.** `tools/compare_overpass_foursquare.py` (solo lectura) empareja lugares de Overpass y Foursquare por distancia y nombre. Usa el log del recolector de Foursquare para saber qué puntos de búsqueda devolvieron menos del tope de 50 — en esos círculos Foursquare está completo y la comparación vale en ambos sentidos; en el resto solo aporta una muestra. Es una estimación, no una verdad: el mismo negocio puede llamarse distinto en cada fuente, y los círculos completos están en la zona menos densa.

```powershell
docker compose run --rm -v "${PWD}/src:/app/src" -v "${PWD}/tools:/app/tools" collector python tools/compare_overpass_foursquare.py
```

Y, opcionalmente, la tabla **`pois_foursquare`** (`src/foursquare_client.py`) — TODOS los POIs que devuelva Foursquare (restaurant/retail/services/entertainment/school/health/mall/other, sin excluir nada, aunque se solape con `pois`), complementaria a `pois`, no un reemplazo. Tabla separada a propósito: el esquema de `pois` es específico de OpenStreetMap (`UNIQUE(osm_type, osm_id)`), y Foursquare identifica sus lugares con `fsq_place_id`, sin esos campos. Solo se puebla si se corre `poi-collector-foursquare` (requiere `FOURSQUARE_API_KEY`, ver la tabla de servicios más arriba).

A diferencia de `pois` (un solo bounding box que ya cubre toda el área monitorizada), Foursquare busca en un radio de 1.5km por punto — insuficiente para cubrir rutas largas de punta a punta. `build_search_points()` (`src/foursquare_client.py`) agrega puntos intermedios interpolados a lo largo de cada corredor único entre las 7 zonas (sin duplicar rutas que son la misma en reversa), espaciados cada 1.5km para que los círculos se solapen ~50%. Con las rutas actuales: 7 zonas + ~20 intermedios = ~27 llamadas por refresco.

Y, también opcional, la tabla **`zone_demographics`** (`src/demographics_client.py`) — población por zona vía Google Data Commons. Diseñada para transicionar a otras ciudades sin tocar código: en vez de tener DCIDs (Data Commons ID) de Malta hardcodeados, cada zona se resuelve **por nombre** la primera vez que se corre `demographics_extraction.py`, y el DCID resultante se cachea en la propia tabla (columna `dcid`) — las corridas siguientes lo reusan sin volver a resolver. Agregar una ciudad nueva a `src/locations.py` no requiere ningún cambio de código aquí. Junto a ella vive `zone_population_history` (todas las observaciones de población por zona, no solo la más reciente). A diferencia de `pois`/`pois_foursquare`, estas tablas **no tienen servicio Docker propio**: la población cambia tan poco (como mucho, una vez al año) que no se justifica un contenedor siempre encendido — se corre a mano cuando haga falta. Como `datacommons-client` no está en la imagen de Docker (vive en `requirements-dev.txt`), se usa un contenedor temporal:

```powershell
docker compose run --rm -v "${PWD}/src:/app/src" collector sh -c "pip install -q 'datacommons-client[Pandas]' && python -m src.demographics_extraction"
```

**Ojo con las fechas:** cada zona trae su observación *más reciente*, y no todas son del mismo año. En Malta, la mayoría de las localidades traen cifras de 2014, Birkirkara de 2019 y Marsaskala de 2021 — y la población del país creció bastante en ese lapso, así que comparar las cifras crudas entre zonas sesga hacia las fechas más nuevas. La columna `observation_date` de `zone_demographics` guarda la fecha de cada una.

Para ver qué fechas existen realmente por zona (y guardar la serie completa en la tabla `zone_population_history`, sin tocar `zone_demographics`):

```powershell
docker compose run --rm -v "${PWD}/src:/app/src" collector sh -c "pip install -q 'datacommons-client[Pandas]' && python -m src.demographics_extraction --diagnose"
```

El diagnóstico indica si existe un año común a todas las zonas (se puede unificar sin estimar) o si no (hay que estimar o cargar otra fuente), e incluye la serie nacional como referencia (`--country`, por defecto `country/MLT`). Cuesta 2 llamadas a la API.

**Llevar cada zona a un año común, priorizando la recencia.** En Malta no existe un año compartido por las 7 zonas (`--diagnose` lo confirma), y forzarlas a la fecha común más vieja disponible las desactualizaría a todas. `--reconcile` ancla cada zona en su **propio dato real más reciente** (de cualquier fuente — no en `date="latest"` de la API, que en producción devolvió para Valletta un valor de 2014 habiendo uno de 2021 en su misma serie) y proyecta solo la diferencia de años con la tasa de crecimiento **nacional**. Una zona cuyo dato ya sea igual o más nuevo que el año objetivo no se toca. Guarda en `zone_demographics` tanto el valor final como el año/población real que se usó de ancla (`basis_year`, `basis_population`) y el método (`observed` o `national_growth_adjustment`), para que quede trazable cuánto de cada cifra es dato real y cuánto es proyección. Requiere haber corrido `--diagnose` antes (usa `zone_population_history`, no vuelve a resolver DCIDs ni a llamar a la API por zona — solo pide la serie nacional, 1 llamada):

```powershell
docker compose run --rm -v "${PWD}/src:/app/src" collector sh -c "pip install -q 'datacommons-client[Pandas]' && python -m src.demographics_extraction --reconcile"
```

Por defecto usa el año más reciente de la serie nacional como objetivo; `--target-year 2024` fija uno específico.

### Pipeline medallion (Bronze → Silver → Gold)

Se dispara automáticamente en cada ciclo del collector (`src/collector.py::_run_incremental_medallion`), solo sobre los registros nuevos de ese ciclo (no reprocesa todo el histórico, por rendimiento). Alimenta `gold_route_kpis` / `gold_route_rankings`, que es lo que lee el dashboard **Executive**.

Para procesar todo el histórico de `route_measurements` por las tres capas:

```bash
python -m src.run_medallion_pipeline
```

El script es **idempotente**: Bronze y Silver ignoran las filas que ya tienen (índice/restricción única sobre `timestamp, origin, destination`) y Gold recalcula cada fecha (`INSERT OR REPLACE`), así que se puede volver a ejecutar sin duplicar. Pero **no borra** lo que ya había: para rehacer las capas realmente desde cero, vacía antes `bronze_measurements`, `silver_measurements`, `gold_route_kpis` y `gold_route_rankings`.

Ver `INTEGRATION_NOTES.md` para el detalle de los bugs que tenía este pipeline en el repo original (mezcla de nombres de columnas, funciones SQL no soportadas por SQLite, restricciones `UNIQUE` faltantes) y cómo se corrigieron.

### Modelos entrenados (dónde viven los `.pkl`)

Hay dos familias de modelos, cada una con su script y su carpeta. **Ninguna se versiona** (`*.pkl` está en `.gitignore` y en `.dockerignore`): se regeneran entrenando.

| Modelo | Se entrena con | Se guarda en | Quién lo usa |
|---|---|---|---|
| Ensemble por ruta (`EnsemblePredictor`) | `python train_ensemble_models.py` | `models/<Origen>_<Destino>_ensemble.pkl` | pestaña **Model Performance** de Analyst y la API (`src/api.py`) |
| Modelo simple por ruta (`TravelTimePredictor`) | `python train_models.py` | `src/models/trained/<Origen>_<Destino>_model.pkl` | `src/predictor.py` |

**En Docker:** como los `.pkl` no entran en la imagen, `docker-compose.yml` monta `./models` en el servicio `dashboard` (`./models:/app/models`). Así, lo que entrenes en tu máquina —o dentro del contenedor— lo ve la pestaña Model Performance. Para entrenar dentro del contenedor y que quede en tu carpeta `./models`:

```bash
docker compose run --rm dashboard python train_ensemble_models.py
```

Sin ningún modelo entrenado, esa pestaña muestra "No trained models yet" y los modelos de cada ruta aparecen como "Not Trained"; el resto del dashboard funciona igual.

---

## Dashboards disponibles

**`streamlit_app/app.py`** (activo, arranca con `docker compose up` / `streamlit run streamlit_app/app.py`):
selector lateral entre 5 vistas —

- **Executive**: KPIs del sistema (con su variación frente al periodo anterior) y mejores/peores rutas, que leen de `gold_route_kpis`; la tendencia y el histograma de 30 días se agregan en SQL directamente desde `route_measurements` (`RouteDatabase.get_daily_average` / `query_columns`), cubriendo la ventana completa y no solo las últimas N filas
- **Operations**: monitoreo en tiempo real y alertas
- **Analyst**: exploración de datos, correlaciones y análisis de series de tiempo (incluye un tab **SQL Query** de solo lectura sobre `data/mobility.db`). La pestaña **Model Performance** muestra el estado de los modelos entrenados por ruta y, debajo, renderiza **`predictive_modeling_dashboard`** — clasificación (Random Forest / regresión logística) y regresión de tiempo de viaje, con curva ROC y comparación de modelos; no es una vista aparte del selector, vive dentro de esa pestaña de Analyst
- **Maps**: rutas monitorizadas sobre un mapa (`plotly.graph_objects.Scattermapbox`, estilo `open-street-map` — sin token), coloreadas por retraso reciente, con overlay opcional de POIs. Selector de fuente (Ninguna / Overpass / Foursquare — una a la vez, no combinadas) y, debajo, un multiselect con las categorías de esa fuente (en Foursquare todas marcadas por defecto; en Overpass arrancan marcadas solo las 4 clásicas — `food_drink`, `leisure` y `sport` suman miles de puntos y se activan a pedido)
- **Recomendación**: para el usuario final — describe el negocio en texto libre ("quiero abrir una pizzería"), el sistema lo interpreta y puntúa las 7 zonas (`src/location_scoring.py`), con un mapa de las zonas (marcadores coloreados por puntaje), tabla con el desglose completo (nunca solo el número final) y pesos ajustables por el usuario

## Consultar la base de datos con SQL

Dos formas, según qué necesites:

- **`streamlit_app/app.py` → Analyst → tab "SQL Query"**: rápido, sin salir del dashboard, forzado a **solo lectura** a nivel del motor SQLite (`mode=ro` — cualquier intento de `INSERT`/`UPDATE`/`DELETE`/`DROP` falla, no solo se filtra por texto). Trae ejemplos precargados.
- **`movilidad-sqlite-web`** (http://localhost:8082): equivalente a pgAdmin pero para SQLite — navega tablas, exporta JSON/CSV, y también permite **editar y borrar filas** desde el navegador. Úsalo con cuidado mientras el collector escribe en paralelo (modo híbrido: ORS cada 15 min, TomTom cada 27 min — y, si está activo, `poi-collector`/`poi-collector-foursquare` semanalmente).

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
1. **`test`**: pytest en Python 3.11/3.12 (Python ≥ 3.11, que es lo que exigen los pines de `requirements.txt`) + un chequeo explícito de que `src.analytics` (módulo) y `src.analytics.time_series_analysis`/`causal_analysis` (submódulos) importan correctamente — regresión directa contra un bug de estructura que encontramos durante la fusión (ver `INTEGRATION_NOTES.md`). Incluye calidad de código:
   - **Bloqueante**: `flake8 --select=E9,F63,F7,F82` (sintaxis y nombres sin definir) y `pylint --enable=E,F` (errores y fatales). Si fallan, el pipeline falla.
   - **Informativo** (`continue-on-error`, no bloquea): `flake8` de estilo completo.
2. **`docker-compose-lint`**: valida `docker-compose.yml` con `docker compose config`
3. **`lint`**: `black` + `isort`, **informativos** por ahora (`continue-on-error`): el código actual no está formateado con ellos, así que se muestran como aviso en vez de bloquear. Para volverlos obligatorios: aplicar el formato una vez y quitar `continue-on-error` de `.github/workflows/tests.yml`.

---

## Troubleshooting

Registro de problemas reales encontrados operando el proyecto, con la causa raíz y cómo se resolvieron — para no re-diagnosticar lo mismo la próxima vez. Se va actualizando cada vez que aparece algo nuevo.

### `.env not found` al correr `docker compose up`

**Síntoma:**
```
env file .../.env not found: GetFileAttributesEx .../.env: The system cannot find the file specified.
```

**Causa:** `.env` está (correctamente) en `.gitignore` — nunca se sube al repo porque contiene API keys y contraseñas. Si el repo se clona de nuevo, o el archivo se pierde localmente, `docker-compose.yml` no encuentra los valores que espera.

**Solución:**
```powershell
Get-ChildItem -Path . -Filter "*.env*" -Recurse -Force -File
# si aparece .env.example:
Copy-Item .env.example .env
notepad .env   # completar las API keys y passwords reales
```

### `password authentication failed for user "postgres"` en el collector

**Síntoma:** el collector loguea `FATAL: password authentication failed for user "postgres"` al escribir en TimescaleDB. Fácil de pasar por alto: el pipeline sigue reportando `"Successfully saved N records"` porque cae a un fallback (SQLite/CSV) — no se ve como un error crítico a simple vista.

**Causa:** el password en `.env` (`PGPASSWORD`) no coincide con el que quedó grabado dentro del volumen de TimescaleDB. Postgres solo aplica `POSTGRES_PASSWORD` la **primera vez** que se crea el volumen — si `.env` se recrea o edita después (por ejemplo, al reconstruirlo desde `.env.example` tras el problema anterior), el volumen sigue con el password viejo aunque `.env` tenga uno nuevo.

**Solución:**
```powershell
# 1. Confirmar el nombre real de la variable en docker-compose.yml (ojo, no es literalmente POSTGRES_PASSWORD)
Select-String -Path .\docker-compose.yml -Pattern "PASSWORD"

# 2. Sincronizar el password de la base con el valor actual de .env, sin exponerlo en pantalla
$pw = ((Get-Content .env | Select-String "^PGPASSWORD=") -replace '^PGPASSWORD=', '').ToString()
docker exec -it movilidad-db psql -U postgres -c "ALTER USER postgres WITH PASSWORD '$pw';"

# 3. Reiniciar el collector para que reconecte
docker compose restart collector
docker compose logs -f collector
```

**Cómo confirmar que quedó resuelto:** buscar `Saved N records to TimescaleDB (traffic_trips)` en los logs del siguiente ciclo — no basta con que desaparezca el error, hay que ver la confirmación positiva.

**Nota:** los registros guardados solo en SQLite/CSV mientras la conexión estuvo rota no se migran solos a TimescaleDB. Si el hueco es de pocos minutos, normalmente no vale la pena migrar; si es de horas o días, conviene un backfill manual.

### Un compañero no aparece como máquina en Tailscale aunque ya "se unió"

Ver la tabla de problemas comunes en [Acceso remoto para el equipo (Tailscale)](#acceso-remoto-para-el-equipo-tailscale) — el culpable casi siempre es iniciar sesión con una cuenta/proveedor distinto al invitado (en Mac, típicamente "Sign in with Apple"), lo que crea una tailnet personal separada de la del equipo.

### `sqlite3.OperationalError: database is locked` en el dashboard

**Síntoma:** el dashboard (`analyst_dashboard.py` u otros) lanza `database is locked` al consultar `mobility.db`, típicamente dentro de `RouteDatabase.init_sqlite()` o `query_measurements()`.

**Causa confirmada con una prueba de concurrencia (no solo hipótesis):** `mobility.db` es escrito por el `collector` y leído por el `dashboard` al mismo tiempo. `sqlite3.connect()` en Python ya trae un timeout por defecto de 5 segundos (no 0) — pero si una escritura tarda más que eso bajo carga (varias personas viendo el dashboard a la vez vía Tailscale, o dos escrituras que se solapan), el timeout se agota y SQLite lanza el error tal cual se ve en producción. Se reprodujo exactamente con dos escrituras simultáneas donde una mantiene el lock 6 segundos: sin el fix, falla con este mismo mensaje; con el fix, no.

Además, `init_sqlite()`/`init_poi_table()` volvían a ejecutar el `CREATE TABLE/INDEX IF NOT EXISTS` en **cada** llamada (cada lectura del dashboard incluida), no solo la primera vez — trabajo repetido e innecesario en cada consulta.

**Solución aplicada en `src/database.py`:**
1. Modo **WAL** (`PRAGMA journal_mode=WAL`) en todas las conexiones — permite que lectores y un escritor convivan sin bloquearse mutuamente en el caso normal.
2. Timeout de conexión subido a 10s (`PRAGMA busy_timeout=10000`) — más margen de espera/reintento antes de fallar.
3. El DDL de `init_sqlite()`/`init_poi_table()` ahora corre **una sola vez por instancia** (flag `_sqlite_initialized`/`_poi_initialized`), no en cada consulta. Como el dashboard ya cachea `RouteDatabase` con `@st.cache_resource`, en la práctica esto significa que corre una sola vez por proceso, no una vez por página vista.

**Cómo confirmar que sigue funcionando:** el dashboard debería dejar de mostrar el traceback incluso con el collector escribiendo activamente en segundo plano. Si vuelve a aparecer, revisar si hay algún otro proceso escribiendo en `mobility.db` fuera del `collector` (por ejemplo, `poi_extraction.py` corriendo al mismo tiempo).

### `backup.sql` / `backup_.sql` commiteados en git por error

**Síntoma:** el repo trae dos dumps SQL sueltos en la raíz (3.4 MB y 6.8 MB) — generados durante una sesión de troubleshooting de Docker/TimescaleDB, nunca pensados para versionarse.

**Causa:** se crearon como respaldo preventivo antes de un cambio riesgoso (`docker exec ... pg_dump ...`) y quedaron en la carpeta del repo, que `git add .` recogió sin que nadie se diera cuenta — `.gitignore` no tenía una regla para `*.sql` sueltos en la raíz (sí la tiene para lo que genera el pipeline dentro de `data/`, pero esto vive fuera de ahí).

**Solución:**
```bash
git rm --cached backup.sql backup_.sql
echo "/backup*.sql" >> .gitignore
git commit -m "Quitar backups de Postgres del control de versiones"
```
(Los archivos siguen existiendo en tu disco como respaldo local — esto solo los saca de git, no los borra. Seguirán apareciendo en el historial de commits anteriores; quitarlos de ahí exigiría reescribir el historial.)

### Archivos que ya no se usan (candidatos a limpiar)

Auditoría de imports reales contra el código activo (docker-compose.yml, `app.py`, dashboards, tests) encontró código huérfano de antes de la fusión de repos:

| Archivo | Por qué ya no se usa | Reemplazado por |
|---|---|---|
| `src/api_extraction.py`, `src/cleaning.py`, `src/scheduler.py` | El propio `docker-compose.yml` documenta que `scheduler` fue retirado; nada activo los importa | `src/collector.py` + `src/route_extraction.py` |
| `data/raw/traffic_weather_data.csv` | Solo lo generaba `api_extraction.py` | `data/raw/route_weather_data.csv` (el histórico fusionado real) |
| `data/processed/clean_traffic_weather_data.csv`, `cleaned_traffic_weather_data.csv` | Solo los generaba `cleaning.py`; son archivos de bytes, no reflejan el histórico real | El pipeline medallion (Bronze/Silver/Gold) cumple ese rol ahora |

No se borraron en esta pasada (por si algún commit reciente todavía los necesita para algo no evidente en el grep) — pero si nadie objeta, son seguros de eliminar en un PR aparte.

### Dashboard lento / demasiadas consultas a SQLite por interacción

**Síntoma:** cualquier clic, cambio de pestaña o slider en Executive/Operations/Analyst/Maps se sentía lento, incluso para acciones que no deberían tocar la base de datos.

**Causa (confirmada leyendo el código, no solo sospechada):** dos problemas compuestos:
1. Ninguna función de consulta estaba cacheada con `@st.cache_data` — solo la conexión (`@st.cache_resource`). Streamlit re-ejecuta el script completo en cada interacción, así que cada clic repetía todas las consultas desde cero.
2. Seis funciones (`render_real_time_alerts`, `render_24h_predictions` y `render_route_status_grid` en Operations; `render_model_performance` en Analyst; `render_route_map` y `render_route_status_table` en Maps) hacían **una consulta SQLite por ruta** en un bucle (`for origin, destination in routes: db.get_route_statistics(...)`), en vez de una sola consulta agregada — con 12 rutas, eso es hasta 24 round-trips a la base solo para una tabla.

Agravante en Analyst: `st.tabs()` en Streamlit ejecuta el contenido de **todas** las pestañas en cada rerun (no solo la visible), así que las 7 pestañas —con sus consultas y bucles— se disparaban aunque el usuario solo tocara la primera.

**Solución aplicada:**
- `@st.cache_data(ttl=60)` en las funciones de obtención de datos de los dashboards (60s: el collector escribe cada 15-27 min, así que no hace falta más frescura que esa).
- 5 de los 6 bucles por ruta se reemplazaron por una sola llamada a `get_all_routes_statistics()` (que ya existía en `database.py`) — validado que da exactamente los mismos números que el bucle que reemplaza, comparado ruta por ruta contra los datos reales.
- El conteo de muestras por ruta en Analyst, de paso, quedó más preciso: antes topaba en 1000 (`limit=1000`) aunque una ruta tuviera miles de mediciones; ahora usa el conteo real sin tope.
- **Pendiente (no resuelto en esta pasada):** `render_route_status_grid` (Operations) sigue haciendo una consulta por ruta, porque necesita la última fila completa de cada una (no un agregado) y no existe todavía una función para eso — candidato para una función nueva `get_latest_per_route()` en `database.py`.

### Foursquare: pizzerías, bistros y otros comercios caían en la categoría `other`

**Síntoma:** en `pois_foursquare`, `other` concentraba ~31% de los POIs (215 de 682), y al mirar `subcategory` la mitad eran comercios de comida (Pizzeria, Bistro, Steakhouse, Burger Joint, Trattoria...). Como el objetivo es medir competencia por tipo de negocio, esto subestimaba `restaurant`.

**Causa:** la lista de palabras de `restaurant` en `src/foursquare_client.py` era demasiado corta (solo "restaurant", "café", "bar", "pub", "bakery", "food", "diner"). Además, el orden de las reglas tenía dos errores: "Department Store" nunca llegaba al balde `mall` (lo atrapaba antes el "store" genérico de `retail`), y "Food and Beverage Retail" / "Health Food Store" caían en `restaurant` por contener "food". Se detectó revisando los nombres reales que devolvió Foursquare para Malta, no con datos de prueba.

**Solución:** la categorización pasó de un diccionario a una **lista de reglas ordenadas** (`_CATEGORY_RULES`), ampliada con los nombres reales observados. Ahora `other` queda reservado a lugares no comerciales (iglesias, parques, plazas, playas, edificios públicos). Validado con 146 nombres reales: `other` bajó de 59 a 22 nombres, todos no comerciales.

**Cómo aplicarlo a los datos ya guardados:** `category` se sobrescribe en cada refresco (upsert por `fsq_place_id`), así que basta con correr el recolector una vez más (27 llamadas de las 500 gratis del mes) o esperar al refresco semanal:
```powershell
docker compose run --rm -v "${PWD}/src:/app/src" collector python -m src.poi_extraction_foursquare
```

**Límite conocido:** con el tope de 50 resultados por punto de búsqueda, 24 de 27 puntos devuelven exactamente 50 — en zonas densas el conteo por categoría es un mínimo, no un total. Solo los puntos hacia Marsaskala (menos densos) devuelven menos de 50, o sea que ahí sí se cubre todo lo que hay.

### `No module named src.<script nuevo>` al correr un script nuevo dentro de Docker

**Síntoma:** `docker compose run ... python -m src.demographics_extraction` responde `No module named src.demographics_extraction`, aunque el archivo sí existe en tu carpeta `src/`.

**Causa:** la imagen se construyó *antes* de que existiera ese archivo, y `./src` no está montada como volumen en `collector` (solo `./data` y `./logs`), así que el contenedor solo ve el código que tenía en el último `--build`. Lo mismo pasa con cambios a archivos existentes, como `database.py`.

**Solución:** montar tu `src/` actual sobre el del contenedor con `-v "${PWD}/src:/app/src"`, o reconstruir con `docker compose up -d --build`. Para scripts que se corren a mano de vez en cuando, el `-v` evita reconstruir.

### Data Commons responde 401 `UNAUTHENTICATED: Method doesn't allow unregistered callers`

**Síntoma:** la resolución de nombres a DCID funciona (las 7 zonas se resuelven), pero la consulta de población falla con 401 aunque `DATACOMMONS_API_KEY` esté en `.env`.

**Causa:** el mensaje indica que la petición llegó *sin ninguna identidad* (una key inválida daría "API key not valid"). La primera versión de `src/demographics_client.py` solo dejaba la key en la variable de entorno `DC_API_KEY` y asumía que `datacommons-client` la leería; en la versión 2.1.6 no lo hace para las consultas de observación.

**Solución:** pasar la key **explícitamente** al constructor (`DataCommonsClient(api_key=...)`). El cliente ahora inspecciona la firma del constructor instalado en vez de asumir el nombre del parámetro, y registra en el log cuántos caracteres tiene la key (nunca el valor) y qué parámetros acepta la versión instalada. Confirmado en producción: el log muestra `parámetros del cliente instalado: ['api_key', 'dc_instance', 'url', 'surface_header_value']`.

**Nota sobre la key:** el portal https://apikeys.datacommons.org muestra una "Key" y un "Secret". Para las llamadas REST/Python normales solo se usa la **Key**; el Secret no hace falta.

### Al elegir Foursquare en Maps aparecían también escuelas y centros comerciales de Overpass (y al revés)

**Síntoma:** con el selector de fuente en "Foursquare", el mapa mostraba además lugares de Overpass en las categorías Escuelas y Centros comerciales; con "Overpass", pasaba lo mismo en sentido contrario. El selector "una fuente u otra" no aislaba del todo.

**Causa:** `render_poi_layer` deducía de qué tabla leer mirando el **nombre** de cada categoría seleccionada, pero `school` y `mall` existen en los dos catálogos. Al ver `school` en la lista, consultaba las dos tablas. Reproducido con una base de prueba en la que ambas fuentes tenían lugares en `school` y `mall`: el dashboard anterior devolvía 5 lugares al elegir Foursquare (2 de ellos de Overpass).

**Solución:** `render_poi_layer(fig, db, categorias, source)` recibe ahora la fuente de forma explícita (`"overpass"` o `"foursquare"`), la que ya eligió el usuario en el selector, y lee solo esa tabla con solo sus estilos. Ya no depende de que los nombres de categoría no se repitan entre fuentes.

### El collector de tráfico no recolecta y nada avisa (stack apagado)

**Síntoma:** no hay ningún error. Simplemente dejan de llegar datos de tráfico, y mientras tanto `docker compose run ...` (para correr un script suelto) funciona con normalidad, lo que da la impresión de que el sistema está en marcha.

**Causa:** con el stack abajo (típicamente tras un `docker compose down`, o con el equipo apagado o suspendido) no corre el `collector` ni el dashboard. `docker compose run` solo levanta `timescaledb`, como dependencia. La pista está en su salida: `Network ... Created` y `Container movilidad-db Created` en lugar de `Running`.

**Diagnóstico:**
```powershell
docker compose ps          # ¿están arriba collector, dashboard, etc.?
docker compose run --rm -v "${PWD}/tools:/app/tools" collector python tools/check_collection_gaps.py
```
La herramienta (solo lectura) indica cuándo llegó el último dato, avisa si hoy no está llegando tráfico y lista los huecos de más de 2 h.

**Solución:** `docker compose up -d`.

**Lo que mostró el historial** (datos hasta el 28-sep, desde que la recolección es continua, el 16-ago): 7 huecos de más de 2 h que suman 9,1 días, el 21% de la ventana. Dos duran varios días (3,4 y 2,8) y cuatro duran entre 12 y 20 h y empiezan entre las 03:00 y las 05:00 UTC, un patrón compatible con que el equipo anfitrión se apague o suspenda de noche.

**Consecuencia para los análisis:** las horas sin datos **no deben rellenarse** (ni con `ffill` ni interpolando). El notebook de la Asignatura 7 rellenaba con el último valor conocido: eso fabricó 110 de 337 horas (un tercio de la serie) y el RMSE del modelo temporal salía 0,016; sin horas inventadas es 0,025. Corregido en ambos notebooks.

## Sistema de recomendación de ubicación (`src/location_scoring.py`)

Responde "¿dónde me conviene abrir este negocio?" combinando lo que ya existe en el proyecto: demografía, POIs y tráfico. **No es un modelo de machine learning** — no hay datos históricos de resultados de negocio (ventas, cierres, supervivencia) con qué entrenar uno. Es un **análisis de decisión multicriterio (MCDA)**: un puntaje por zona, suma ponderada de tres factores normalizados, con el desglose siempre visible — la idea es apoyar la decisión con criterios explícitos, no dar un número de caja negra.

### El usuario describe el negocio con sus propias palabras

`src/business_type_classifier.py` interpreta texto libre en español ("quiero poner una pizzería") y lo mapea a una de las 7 categorías de Overpass (`CATEGORY_TAGS` en `poi_client.py`), con 140 palabras clave organizadas por categoría. Mismo patrón (y mismo cuidado) que la categorización de Overpass y Foursquare: límites de palabra (`\b`) para que "barbería" no matchee la palabra clave "bar" — ese bug ya ocurrió una vez con datos reales de Foursquare, así que aquí se probó explícitamente contra el mismo caso. Verificado además que ninguna de las 140 palabras choca con otra de distinta categoría. Si el texto no matchea ninguna palabra clave, se lanza un error explícito — nunca elige una categoría al azar.

### Las tres dimensiones, con lo que ya existe

| Dimensión | Fuente | Función |
|---|---|---|
| Demanda | `zone_demographics` (población, ya reconciliada a un año común) | `zone_demand()` |
| Competencia | `pois` (Overpass), conteo dentro de 1.500 m del centro de cada zona | `zone_competition()` |
| Accesibilidad | `route_measurements`, vía `get_all_routes_statistics()` (ya existía) | `zone_accessibility()` |

**Corrección para `food_drink`:** Overpass ve ~61% de los restaurantes reales según la comparación con Foursquare (`tools/compare_overpass_foursquare.py`, sección A1). El conteo de competencia para esa categoría se divide por ese factor — un número por zona, marcado explícitamente como `corregido_por_cobertura` (columna `metodo_competencia`) y no como observado directo. Es una medición puntual en la zona menos densa (cerca de Marsaskala): puede no generalizar igual a zonas más densas.

**Hallazgo al validar con las coordenadas reales:** 4 de las 7 zonas están a menos de 1.500 m entre sí (Msida↔Gzira, Gzira↔Sliema, Gzira↔St Julian's, Sliema↔St Julian's) — sus radios de competencia se solapan de forma genuina. No es un error: son así de cercanas en la realidad. Solo Marsaskala está a más de 6 km de todas las demás.

### Cómo se combinan

Cada dimensión se normaliza 0-1 (`min-max`); competencia y tiempo de viaje se invierten (`1 - normalizado`) para que, en las tres, "más alto = mejor para el negocio" — así los pesos siempre se leen como "qué tanto importa cada cosa", sin convenciones de signo que recordar. Pesos por defecto: demanda 0.40, competencia 0.35, accesibilidad 0.25 (configurables, deben sumar 1.0). Una zona sin dato en alguna dimensión (por ejemplo, sin demografía cargada) no se penaliza como si fuera la peor opción: se trata como neutral (0.5) en esa dimensión.

```python
from src.location_scoring import recommend_locations
recommend_locations(db, "quiero abrir una pizzería")
# -> DataFrame con las 7 zonas, ordenadas por score, con demanda/competencia/
#    accesibilidad crudas Y normalizadas visibles (nunca solo el número final)
```

Expuesto al usuario final en el dashboard **Recomendación** (`streamlit_app/dashboards/recommendation_dashboard.py`), con los pesos ajustables desde la propia interfaz.

---

## Documentación adicional

- **`INTEGRATION_NOTES.md`** — qué se fusionó de cada repo, y el detalle completo de cada bug encontrado y corregido durante la integración
- **`PRODUCTION.md`** — endurecimiento para servidor real: usuarios no-root, healthchecks, límites de recursos, contraseñas, puertos, y el checklist si esto sale a internet público
- **`docs/API.md`** — documentación de la API REST opcional (`src/api.py`)
- **`docs/research_paper/README.md`** — paper de investigación heredado de urban-mobility-analytics1 (ensemble ML, causal inference, arquitectura medallion)
