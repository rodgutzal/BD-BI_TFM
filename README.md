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
│   ├── business_type_classifier.py  ← texto libre en español -> categoría de Overpass (para el sistema de recomendación)
│   ├── location_scoring.py          ← motor de puntuación (MCDA) de zonas para dónde abrir un negocio
│   ├── ml/                          ← (fases 0, 1 y 1b del diseño de ML de recomendación) rejilla de 250 m, conteos por celda, perfiles de negocio ajustables, las tres lentes (competencia/mercado/proveedores), variables con control de fuga, modelos de oferta esperada (boosting de Poisson y red MLP), validación espacial y contexto de OSM (edificios, alojamiento, transporte)
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
├── tests/                        ← pytest, un archivo por módulo o tema; todos documentados: ver la sección "Tests" y docs/TESTS.md (catálogo generado)
├── tools/
│   ├── merge_legacy_data.py      ← script (ya ejecutado) que generó el histórico fusionado
│   ├── compare_overpass_foursquare.py ← (solo lectura) mide qué tan completo es OpenStreetMap frente a Foursquare, emparejando por nombre y distancia
│   ├── check_collection_gaps.py  ← (solo lectura) detecta y mide huecos en la recolección de tráfico (cuándo estuvo apagado el stack)
│   ├── measure_lens_variance.py  ← (solo lectura) mide cuánto varía cada lente del asistente entre celdas y cuánto se parecen entre sí
│   ├── validate_location_model.py ← (solo lectura) validación espacial de los modelos de oferta esperada frente a líneas base, con la regla de decisión y el contraste con Foursquare (`--contexto DIR` añade el contexto de OSM)
│   ├── download_osm_context.py   ← descarga de Overpass edificios, alojamiento, transporte e industria a archivos JSON (NO toca la base; `--dry-run` no hace llamadas de red)
│   ├── normalize_bronze_timestamps.py ← (ensayo por defecto; `--apply` con respaldo) normaliza los timestamps antiguos de Bronze al formato ISO — ver Troubleshooting
│   ├── generate_tests_doc.py     ← genera docs/TESTS.md (catálogo de todos los tests, una línea por test); `--check` verifica que esté al día
├── docs/                         ← documentación heredada de urban-mobility-analytics1 (API, research paper) + TESTS.md (catálogo de tests, generado)
├── .github/workflows/tests.yml   ← CI: tests + lint + validación de docker-compose.yml
├── collect.py                    ← wrapper de conveniencia: `python collect.py` == `python -m src.route_extraction`
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

> ⚠️ **Después de un `down` (o de un `stop`) el stack no vuelve solo**, ni siquiera reiniciando el equipo: los servicios tienen `restart: unless-stopped`, y esa política respeta una parada manual. Hay que volver a levantarlo con `docker compose up -d`. Si no, la recolección queda parada sin ningún aviso (ver "Huecos de recolección" en Troubleshooting).

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
- **Analyst**: exploración de datos, correlaciones y análisis de series de tiempo (incluye un tab **SQL Query** de solo lectura sobre `data/mobility.db`). La pestaña **Model Performance** muestra el estado de los modelos entrenados por ruta y, debajo, renderiza **`predictive_modeling_dashboard`** — clasificación (Random Forest / regresión logística) y regresión de tiempo de viaje, con curva ROC y comparación de modelos, más forecast temporal (ARIMA) y clustering; no es una vista aparte del selector, vive dentro de esa pestaña de Analyst. **Los cuatro modelos se entrenan bajo demanda**, al pulsar su botón (o el de "los cuatro"), no al abrir la pantalla (ver Troubleshooting)
- **Maps**: rutas monitorizadas sobre un mapa (`plotly.graph_objects.Scattermapbox`, estilo `open-street-map` — sin token), coloreadas por retraso reciente, con overlay opcional de POIs. Selector de fuente (Ninguna / Overpass / Foursquare — una a la vez, no combinadas) y, debajo, un multiselect con las categorías de esa fuente (en Foursquare todas marcadas por defecto; en Overpass arrancan marcadas solo las 4 clásicas — `food_drink`, `leisure` y `sport` suman miles de puntos y se activan a pedido)
- **Recomendación**: para el usuario final — describe el negocio en texto libre ("quiero abrir una pizzería"), el sistema lo interpreta y puntúa las 7 zonas (`src/location_scoring.py`), con un mapa de las zonas (marcadores coloreados por puntaje), tabla con el desglose completo (nunca solo el número final: cada factor aparece con su valor crudo —población, conteo de competencia, tiempo de viaje— y con su valor normalizado 0-1, donde más alto siempre es mejor; una zona sin dato en un factor se muestra como "sin dato" y se puntúa como neutral) y pesos ajustables por el usuario

## Consultar la base de datos con SQL

Dos formas, según qué necesites:

- **`streamlit_app/app.py` → Analyst → tab "SQL Query"**: rápido, sin salir del dashboard, forzado a **solo lectura** a nivel del motor SQLite (`mode=ro` más un *authorizer* que solo deja pasar `SELECT`/`WITH` y funciones: `INSERT`/`UPDATE`/`DELETE`/`DROP`/`CREATE`, `PRAGMA`, `ATTACH` y `VACUUM` fallan, no solo se filtra por texto). Trae ejemplos precargados. *(Con solo `mode=ro`, `ATTACH` y `VACUUM INTO` creaban archivos nuevos en disco, p. ej. una copia de la base; se midió y se cerró con el authorizer.)*
- **`movilidad-sqlite-web`** (http://localhost:8082): equivalente a pgAdmin pero para SQLite — navega tablas, exporta JSON/CSV, y también permite **editar y borrar filas** desde el navegador. Úsalo con cuidado mientras el collector escribe en paralelo (modo híbrido: ORS cada 15 min, TomTom cada 27 min — y, si está activo, `poi-collector`/`poi-collector-foursquare` semanalmente).

Para la capa de producción (TimescaleDB), sigue usando **pgAdmin** (http://localhost:8080).

**`streamlit_app/legacy_reference/`** (no activos, se conservan como referencia):

- `app_advanced.py`: el dashboard original de urban-mobility-analytics1 — vista de una sola ruta con mapa, comparación de clima origen/destino, 4 pestañas y exportación. Sigue siendo funcional standalone: `streamlit run streamlit_app/legacy_reference/app_advanced.py`
- `app_classic.py`: el dashboard original de BD_BI_TFM. Apunta a `legacy_ors_traffic_weather_data.csv` (el CSV original, no al histórico fusionado)

---

## Testing y CI

### Tests (`tests/`)

```bash
pip install -r requirements-dev.txt
pytest tests/ -v --cov=src --cov-report=term
```

**Todos los tests están documentados**, y esa regla se hace cumplir en el CI (ver abajo):

- **Esta tabla**: qué cubre cada archivo, y qué *no* cubre la suite.
- **[`docs/TESTS.md`](docs/TESTS.md)**: el catálogo completo, **una línea por test** (nombre, número de casos y descripción). Es un archivo **generado**: no se edita a mano, se regenera con `python tools/generate_tests_doc.py`.

Convenciones: un archivo por módulo o tema; **ningún test toca `data/mobility.db`** (usan bases temporales; la API se apunta a una con `MOBILITY_DB_PATH`); `tests/conftest.py` fija el backend `Agg` de matplotlib (con el backend Tk por defecto, los tests de dashboards con `AppTest` hacían caer a pytest al cerrar).

<!-- tests:inicio -->
| Archivo | Qué cubre |
|---|---|
| `test_api_clients.py` | Clientes HTTP **sin red** (sesión falsa): TomTom, ORS, OpenWeather y Overpass: parseo y claves comunes (ORS deja el tráfico en `None`, no en 0), petición enviada (ORS usa `[lon, lat]`), reintentos solo en 429/5xx, caché del clima, fallback entre espejos de Overpass, clasificación de POIs y propagación de errores |
| `test_migrations.py` | Migración del CSV histórico: a SQLite (filas sin campos obligatorios, `data_source` por defecto, números ilegibles → NULL, `--dry-run` sin escribir, idempotencia, CLI) y a TimescaleDB con un `psycopg2` falso (orden de columnas, rollback ante error, celdas vacías como NULL y no como `NaN`) |
| `test_causal_analysis.py` | `CausalAnalysis` con datos sintéticos de efecto conocido (0,5 min/°C): recupera el efecto y su signo, no ve efecto donde no lo hay, antes/después, confusores (exigen afectar a tratamiento **y** resultado) e interpretaciones. Comprueba los cálculos, **no** que el resultado sea causal |
| `test_travel_time_predictor.py` | Modelo simple por ruta: `TravelTimePredictor` (construcción de las 6 variables, nulos, entrenar/guardar/cargar, `predict` sensible a los datos y con el lag esperado) y `RoutePredictor` (archivos por ruta, `min_samples` que llega al modelo, entrenar todas las rutas, estado). Incluye las regresiones de `predict()` y de `min_samples` |
| `test_dashboards_executive_maps.py` | Pantallas **Executive** y **Maps** (AppTest, base temporal con Bronze→Silver→Gold): tarjetas y deltas calculados de los datos (aumento de tiempo en rojo), alertas con sus umbrales exactos (>30 min, <50 %), mejores/peores rutas, colores y estados del mapa (1 y 4 min de retraso), capas de POIs sin mezclar fuentes, base vacía |
| `test_analyst_tabs.py` | Pestañas de **Analyst**: editor SQL de solo lectura **de verdad** (rechaza escrituras, `PRAGMA`, `ATTACH` y `VACUUM INTO` sin crear archivos ni cambiar un byte; cierra la conexión), todos los ejemplos ejecutables, exportación completa (con/sin `polyline`, con/sin fechas, sin datos), explorador, estadística, correlaciones, estado de modelos y base vacía |
| `test_analytics.py` | `MobilityAnalytics`: inicialización, *consistency score* (ventana móvil de 24 h) y resumen de la base |
| `test_analyst_quality.py` | Analyst al abrirse: usa **un** perfil de la base y no las consultas caras de antes (`get_available_routes` ×4, completitud ruta por ruta, 100 mil filas cargadas); las métricas de calidad son las del perfil |
| `test_api.py` | API REST con `TestClient` y una base temporal: **404** en recursos sin datos (antes salía 400), **422** en parámetros inválidos, caminos felices y `predict` de punta a punta |
| `test_business_type_classifier.py` | Texto libre en español → categoría de Overpass: "barbería" ≠ "bar", sin coincidencia → `None`, las 140 palabras clave sin choques entre categorías |
| `test_check_collection_gaps.py` | `tools/check_collection_gaps.py`: detección y medición de huecos de recolección, solo lectura |
| `test_config.py` | `config.py`: selección de la fuente de datos (ORS/TomTom) y configuración de TimescaleDB |
| `test_forecasting.py` | Pronóstico SARIMA (`src/forecasting.py`): converge sin avisos, aprende el ciclo diario, no inventa horas sin dato; y la validación (`tools/validate_forecast.py`): cortes, referencias sin datos del futuro, comparación pareada y lectura en solo lectura |
| `test_data_profile.py` | `get_data_profile` (calidad de toda la tabla en **una** pasada, contrastado con pandas), `get_last_timestamp` y `get_database_summary(include_routes=False)` |
| `test_database.py` | `RouteDatabase` básico: inicialización, guardado en CSV y SQLite, consulta de mediciones |
| `test_database_windows.py` | Consultas de ventana completa sin `LIMIT` (promedio diario, ruta × hora, columnas elegidas) y protección contra inyección SQL |
| `test_demographics.py` | Población por zona: reconciliado a un año común con la tasa nacional, *upserts* con `COALESCE`, historial |
| `test_ensemble_predictor.py` | `EnsemblePredictor`: features, entrenamiento, predicción con intervalos de confianza, anomalías, guardar y cargar |
| `test_foursquare_client.py` | Categorización con nombres reales de Foursquare, `build_search_points` (7 zonas + 20 intermedios = 27 llamadas) y los dos formatos de respuesta |
| `test_hybrid_scheduler.py` | `HybridScheduler`: cada fuente con su propio reloj, primer ciclo inmediato y cierre por señal. **Ojo:** simula la lógica con una función auxiliar en vez de ejecutar `run()`; el bucle real lo prueba `test_collector.py` |
| `test_collector.py` | `DataCollector` de punta a punta con clientes falsos y sin esperas: un ciclo guarda las 12 rutas en CSV y SQLite, clima por lugar, umbral de "Alta demora" (>20 min, estricto), tolerancia a fallos de clima/ruta/guardado, TimescaleDB solo con configuración, heartbeat (redirigido, no toca `logs/`), medallón incremental (cada ciclo procesa solo sus filas) y el bucle real de `HybridScheduler` |
| `test_ml_grid.py` | Rejilla de 250 m (fija, 45×51 celdas, bordes, identificadores, vecindad por anillos sin dar la vuelta) y conteos por celda × subcategoría (`Selector`, POIs fuera de la rejilla, tabla precalculada) |
| `test_ml_inputs_bundle.py` | Fase 1c: paquete de entrada del ML para entrenar en otra máquina — hash de tablas independiente del orden, exportación idéntica a la base de origen (que no se toca), rutas agregadas, tablas opcionales ausentes, negativa a pisar o a exportar sobre la base, verificación contra el manifiesto (valor alterado, filas perdidas, tabla ausente, formato), contexto de OSM dentro del paquete con prioridad del directorio, procedencia de resultados, las herramientas aceptan el paquete en `--db` y requirements-ml.txt fija versiones exactas |
| `test_ml_context.py` | Fase 1b: conversión del contexto de OSM (edificios, alojamiento, transporte sin posiciones duplicadas, industria), su efecto en las lentes (residentes sin los edificios industriales, hoteles como turistas, **índice de mercado 0-1 que ningún segmento domina por su unidad**), en las celdas activas (no cambian) y en los modelos opcionales (`boosting_poi`, `solo_edificios`); y la herramienta de descarga con un cliente falso: franjas sin huecos, un archivo por trozo, fallback entre espejos, pausas entre peticiones pero no tras la última, `--dry-run` sin red |
| `test_ml_validation.py` | Fase 1 del ML: lectura de datos en solo lectura, modelos de oferta esperada (positivos, deterministas, cada línea base usa solo sus variables, una variable toda NaN no rompe el ajuste), validación espacial (los bloques no se parten entre entrenamiento y prueba, la predicción de una celda no usa su propio valor), desviación de Poisson contra scikit-learn, bootstrap de bloques, la regla de decisión —con la regresión de que el veredicto no depende del número de repeticiones— y `validate_location_model.py` de punta a punta |
| `test_ml_lenses.py` | Perfiles de negocio y su ajuste por el usuario (una lente no queda vacía, aviso al quitar más de la mitad de la competencia), las tres lentes (NaN ≠ 0, un POI cuenta en una sola lente, apoyo y diversidad), variables del modelo con **control de fuga** (el objetivo no entra) y la herramienta `measure_lens_variance.py` |
| `test_ml_panorama.py` | Fase 2a: panorama por celda — reconstrucción de los conteos desde la tabla (las lentes recalculadas salen **idénticas**, incluido el contexto de OSM de celdas inactivas vecinas), percentiles que conservan los NaN y los empates, confianza de datos (una lente sin datos cuenta 0; la competencia se apoya en los POIs de la vecindad y no en el número de competidores), brecha exploratoria alineada por celda, sin modelo ni etiqueta de validada cuando no hay brecha y sin tocar ninguna otra columna, el módulo no importa scikit-learn, archivos de salida con manifiesto (hash, formato, archivo ausente o fuera del manifiesto, salida determinista) y `build_panorama.py` de punta a punta con y sin brecha |
| `test_location_scoring.py` | Recomendación de ubicación (MCDA): demanda, competencia, accesibilidad, pesos, zonas sin dato como neutrales y caso de punta a punta |
| `test_locations.py` | Las 7 ubicaciones y las 12 rutas |
| `test_medallion.py` | Bronze / Silver / Gold: idempotencia, `get_period_metrics`, resumen ejecutivo con base vacía y el pipeline completo |
| `test_normalize_bronze_timestamps.py` | `tools/normalize_bronze_timestamps.py`: ensayo sin cambios, aplicar con respaldo, base ocupada, *rollback* y que después el pipeline no duplique |
| `test_operations_status.py` | `get_latest_per_route` y el estado por ruta de Operations (una ruta sin lectura de tráfico nunca sale en verde) |
| `test_ors_null_fields.py` | Regresión: campos que vienen `NULL` con `DATA_SOURCE=ors` (el ayudante `_safe`) |
| `test_predictive_modeling_dashboard.py` | Preparación de datos del modelado: clima ausente (no es "lluvia") y exclusión de filas incompletas |
| `test_predictive_modeling_ondemand.py` | Modelado bajo demanda con `AppTest`: al abrir no se entrena nada, un botón entrena solo su sección, el de "los cuatro" entrena todo |
| `test_query_measurements_polyline.py` | `include_polyline` en `query_measurements`: sin la columna pesada por defecto y con ella intacta cuando se pide |
| `test_recommendation_dashboard.py` | Tabla de Recomendación: cada factor crudo y normalizado; el puntaje es la suma ponderada de lo que se muestra |
| `test_tests_documentation.py` | Esta regla: `docs/TESTS.md` al día y todos los archivos de test en esta tabla |
| `test_time_series.py` | `TimeSeriesAnalytics`: descomposición estacional, estacionariedad, autocorrelación, patrones, puntos de cambio |
<!-- tests:fin -->

**Qué NO cubre la suite** (lo que hoy se comprueba solo a mano o con el CI de otro modo):

- **Docker real**: el CI solo valida la sintaxis de `docker-compose.yml` (`docker compose config`); que el stack arranque, el volumen `./models` y los healthchecks se probaron a mano, no hay test automático.
- **Servicios externos reales**: ORS, TomTom, OpenWeather, Overpass, Foursquare y Data Commons se prueban con datos simulados, nunca contra la API.
- **Sin tests propios** (los ejercitan indirectamente, o nada): los CLI `poi_extraction*` y el render visual (de las seis pantallas se prueba que abren sin excepciones, con datos y con la base vacía, y lo que muestran).
- **Executive con la base vacía** muestra "System Reliability 0.0%" y la alerta "Low system reliability (<50%)", cuando en realidad la fiabilidad es desconocida (observado al escribir sus tests; sin cambiar).
- **`causal_analysis` no es inferencia causal rigurosa** (observado al escribir sus tests): el "propensity score matching" calcula los *propensity scores* pero **no los usa**: `_calculate_psm_effect` es la diferencia de medias entre grupo tratado y control, sin emparejar; y los textos ("causes ~X min") presentan como causal una asociación en datos observacionales. Para el TFM conviene llamarlo análisis de asociación estratificada.
- **El modelo simple por ruta (`TravelTimePredictor`) tiene una variable que filtra el objetivo** (observado al escribir sus tests; no se cambió, es una decisión de metodología): `travel_time_min_lag` es una media móvil de 5 filas que **incluye la fila actual**, o sea, parte del propio `travel_time_min` que se quiere predecir; y las filas llegan de la base ordenadas de más reciente a más antigua y no se reordenan, así que la ventana mezcla también filas posteriores en el tiempo. Sus métricas no deben presentarse como capacidad predictiva real. Además, antes de PR #34 `predict()` devolvía siempre `None` (columnas con otro nombre que en el ajuste), así que este modelo nunca había dado una predicción.
- **Render visual** en un navegador real.

**Añadir un test sin dejar la documentación atrás:** escríbelo con un nombre y un docstring descriptivos; si es un archivo nuevo, añade su fila a la tabla de arriba; y regenera el catálogo con `python tools/generate_tests_doc.py`. Si se te olvida, `tests/test_tests_documentation.py` falla en el CI y dice qué falta.

### CI

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

### Bronze se "duplica" la primera vez que se corre `run_medallion_pipeline`

**Síntoma:** al correr `python -m src.run_medallion_pipeline` por primera vez sobre una base que ya tenía datos, `bronze_measurements` crece en miles de filas (medido sobre una copia de la base real: +2.761, de 78.541 a 81.302) aunque `route_measurements` no cambió. Silver y Gold no se ven afectadas; solo se infla Bronze.

**Causa:** un bug antiguo de `bronze_layer.py` guardaba `raw_timestamp` con un **espacio** como separador (`2026-05-25 23:54:03…`) en vez de la `T` del resto del proyecto (`2026-05-25T23:54:03…`). Esas filas siguen en la base y el índice único `idx_bronze_unique` compara texto: ve la fila antigua y la misma medición en formato ISO como distintas, así que el pipeline reinserta esas mediciones como "nuevas".

**Solución:** normalizar esos timestamps **una sola vez**, con el stack apagado (`docker compose down`), usando la herramienta de ensayo/aplicación:

```powershell
# 1. Ensayo: solo lee y muestra qué haría. No modifica nada.
python tools/normalize_bronze_timestamps.py

# 2. Aplicar: respaldo consistente + bloqueo exclusivo + verificación; ROLLBACK si algo falla.
python tools/normalize_bronze_timestamps.py --apply
```

Qué hace con cada fila de Bronze con separador antiguo: si ya existe la misma medición en ISO, **borra** la antigua (es un duplicado); si varias antiguas coinciden, conserva la de menor `id`; en cualquier otro caso la **renombra** a ISO. Sirve igual **antes** de correr el pipeline (solo renombra) que **después** (también limpia los duplicados que ya se hayan generado). No toca otras tablas, es idempotente, y deja un respaldo `mobility.db.bak-AAAAMMDD-HHMMSS` junto a la base (git y Docker lo ignoran; bórralo a mano cuando verifiques que todo está bien). Ojo: si el repo está dentro de OneDrive u otro sincronizador, ese archivo de ~400 MB también se sincroniza.

**Cómo confirmar que quedó resuelto:** `SELECT COUNT(*) FROM bronze_measurements WHERE raw_timestamp LIKE '____-__-__ %'` debe dar 0, y volver a correr `run_medallion_pipeline` no debe cambiar el conteo de Bronze.

### Archivos que ya no se usan (candidatos a limpiar)

Auditoría de imports reales contra el código activo (docker-compose.yml, `app.py`, dashboards, tests) encontró código huérfano de antes de la fusión de repos:

| Archivo | Por qué ya no se usa | Reemplazado por |
|---|---|---|
| `src/api_extraction.py`, `src/cleaning.py`, `src/scheduler.py` | El propio `docker-compose.yml` documenta que `scheduler` fue retirado; nada activo los importa | `src/collector.py` + `src/route_extraction.py` |
| `data/raw/traffic_weather_data.csv` | Solo lo generaba `api_extraction.py` | `data/raw/route_weather_data.csv` (el histórico fusionado real) |
| `data/processed/clean_traffic_weather_data.csv`, `cleaned_traffic_weather_data.csv` | Solo los generaba `cleaning.py`; son archivos de bytes, no reflejan el histórico real | El pipeline medallion (Bronze/Silver/Gold) cumple ese rol ahora |

No se borraron en esta pasada (por si algún commit reciente todavía los necesita para algo no evidente en el grep) — pero si nadie objeta, son seguros de eliminar en un PR aparte.

### Analyst tardaba minutos en abrir (y se quedaba sin memoria en Docker)

**Síntoma:** abrir la vista Analyst con la base real (78,5 mil filas) tardaba ~82 s en un equipo de 16 CPUs y **~9 min dentro del contenedor del dashboard** (1 CPU, 1 GiB), donde además el proceso podía morir por falta de memoria (código 137).

**Causas (medidas, no supuestas):**
1. **Streamlit ejecuta el contenido de todas las pestañas en cada rerun**, así que los cuatro modelos de *Modelado Predictivo* se entrenaban de golpe al abrir la pantalla: clasificación 25 s, regresión 20 s, forecast temporal 25 s y clustering 3 s (con 16 CPUs), y cada uno ocupaba su propia memoria (el forecast llegaba a ~870 MB de pico).
2. `query_measurements` cargaba la columna `polyline` (el 93% de la memoria de la tabla: 339 de 365 MB). Resuelto antes: ya no se carga por defecto.

**Solución aplicada:**
- **Modelado bajo demanda:** al abrir Analyst no se entrena nada; cada pestaña tiene su botón y hay uno para los cuatro. Lo pedido se mantiene durante la sesión y queda en caché (`max_entries=1`: si cambian los datos, la entrada nueva sustituye a la vieja). Los modelos se guardan con `st.cache_resource` (el objeto tal cual, sin la copia serializada que hacía `cache_data`).
- **`low_memory=True` en el ARIMA:** mismo AIC y mismo pronóstico (idénticos a 4 decimales), con un pico de ~405 MB en vez de ~870 MB, a cambio de un ~15% más de tiempo.
- En tu equipo (16 CPUs), **abrir Analyst pasó de ~82 s a ~5 s**.

**Qué esperar al pulsar los botones:** del orden de 1 minuto en un equipo con varios núcleos y varios minutos con 1 CPU (p. ej. dentro de Docker). Después, inmediato mientras no cambien los datos.

**Medido dentro del contenedor del dashboard (1 CPU, 1 GiB, base real de 78,5 mil filas, `data/` en un volumen de Docker):**

| | Antes de estos cambios | Ahora |
|---|---|---|
| Abrir Analyst | 536 s | **3,2 s** |
| Entrenar los cuatro modelos (al pulsar el botón) | — (se hacía al abrir) | 445 s (≈ 7,4 min), sin excepciones |
| Pico de memoria del contenedor (límite 1.024 MiB) | 961 MiB (margen del 6%) | **728 MiB (margen del 29%)** |
| `OOMKilled` / reinicios | — | no / 0 |

Esos 445 s son cómputo puro de una sola CPU: lo que cambió es que ya **no se pagan al abrir la pantalla** y que la memoria deja de acumularse. Si se quiere reducirlos hay que cambiar los modelos (menos árboles, rejilla más pequeña, menos candidatos ARIMA), lo que altera la metodología respecto al `.Rmd` y no se hizo.

**Corrección de un texto engañoso:** el comentario del forecast temporal decía que se modelaba "el bloque continuo más reciente". No es así: `resample("1h")` crea un índice horario *regular*, así que la serie nunca se parte y se modela **entera** (82 días, con el ~46% de las horas vacías tratadas como datos faltantes, sin rellenar). Se dejó el comportamiento y se corrigió el texto: dividir por los huecos reales dejaría, con un equipo que se apaga cada noche, un bloque de pocas horas, inútil para una estacionalidad de 24 h. Además, **los 4 candidatos ARIMA terminaban con avisos de convergencia del optimizador** (ver la sección siguiente).

#### Forecast temporal: no convergía y no mejora a la referencia

**Diagnóstico (base real, `tools/validate_forecast.py`, solo lectura):**
- Los 4 candidatos `(p,d,q)x(1,0,1,24)` se detenían en el tope de 50 iteraciones del optimizador (`warnflag=1`), con el AR estacional pegado a ~0,99 (casi raíz unitaria que se cancela con el MA ≈ −0,9) y una serie en escala 0-1 (`sigma2` ≈ 4·10⁻⁴). En la validación convergía en **10 de 35** cortes.
- La serie es el % de mediciones con `travel_time_min > 20`: tiene un ciclo diario claro (autocorrelación a 24 h = 0,84; media por hora de 0,18 de noche a 0,31 de día), pero su desviación típica es solo 0,061.

**Cambio (aprobado):** SARIMA `(1,0,1)x(0,1,1,24)` (diferenciación estacional) con la serie en escala 0-100, en `src/forecasting.py`. Converge en **35 de 35** cortes y deja de probar 4 candidatos. Se corrigió además un error previo: `fit(low_memory=True)` dejaba el intervalo de confianza del pronóstico en **NaN** (la banda del gráfico nunca se dibujaba); ahora, tras optimizar con poca memoria, una pasada `smooth` con los parámetros ya estimados lo calcula. El dashboard dibuja además la referencia (media por hora del día) y muestra la nota de validación.

**Validación de origen móvil** (35 cortes diarios, 28-ago a 26-oct-2026; se ajusta con el pasado y se pronostican las 24 h siguientes; error sobre las horas con dato; menos es mejor):

| Modelo | MAE | Frente al perfil horario (IC 95%) |
|---|---|---|
| Mismo hora de ayer | 0,0208 | −0,0015 ± 0,0044 · indistinguible |
| **Perfil horario (media por hora del día)** | **0,0222** | referencia |
| **SARIMA nuevo** | 0,0233 | +0,0011 ± 0,0019 · indistinguible |
| ARIMA anterior | 0,0247 | +0,0025 ± 0,0030 · indistinguible |
| Media global | 0,0479 | +0,0256 ± 0,0051 · peor |
| Último valor | 0,0608 | +0,0386 ± 0,0075 · peor |

**Limitación para el TFM:** el SARIMA captura el ciclo diario (gana a la media global y a la persistencia) pero **no aporta evidencia de mejorar a la media por hora del día**; con estos datos (54% de horas con dato) un pronóstico tan simple rinde igual. Se reproduce con `python tools/validate_forecast.py` (con `--include-legacy` añade el ARIMA anterior).

#### En Windows, `./data` como bind mount de Docker es ~30 veces más lento

Además de lo anterior, al medir **dentro del contenedor** apareció otra causa, esta del entorno:

| Lectura completa de `route_measurements` (78.597 filas) | Bind mount de Windows (`./data`) | Sistema de archivos del contenedor |
|---|---|---|
| Columnas anteriores a `polyline` | 4,9 s | 0,36 s |
| Sin `polyline` pero con `created_at` | **14,9 s** | 0,47 s |

Con el bind mount, **abrir Analyst dentro del contenedor tardaba 114 s** (resumen de la base 8 s, las 12 consultas del informe de calidad 41 s, la muestra de 78 mil filas 18 s…), aunque ya no entrenara ningún modelo. **Con `data/` en un volumen de Docker tardó 3,3 s.** Dos efectos se suman: el acceso a archivos de Windows desde un contenedor (Docker Desktop) es lento, y `created_at` va *después* de `polyline` en cada fila, por lo que leerla obliga a recorrer las páginas de desbordamiento de la polilínea de todas las filas.

Esto afecta solo a quien ejecuta el stack en **Docker Desktop sobre Windows**; en un servidor Linux el bind mount es nativo. Si la lentitud importa, las opciones son: mover `data/` a un volumen con nombre (**es lo único que se midió**: 3,3 s; a costa de no ver `data/mobility.db` desde el host, de modo que las herramientas de `tools/` y los respaldos tendrían que correr con `docker compose run`), o ejecutar el proyecto desde el sistema de archivos de WSL2 (p. ej. `~/BD-BI_TFM`, no desde `C:\...`), que es la recomendación habitual de Docker pero **no se probó aquí**. **No se cambió el `docker-compose.yml`**: es una decisión de quien opera el stack.

**Qué se corrigió en el código para que importe menos** (medido en el entorno lento: contenedor de 1 CPU y 1 GiB con `./data` en el bind mount de Windows, base real de 78,5 mil filas; mismo hardware, mismos datos):

| Abrir Analyst | Antes | Ahora |
|---|---|---|
| Tiempo total | **114,5 s** | **16,0 s** (7× menos) |
| Rutas únicas (`SELECT DISTINCT`, que recorre toda la tabla) | 4 llamadas, 31,3 s | 0 (salen del perfil) |
| Completitud por ruta | 12 consultas | 0 (salen del perfil) |
| Lectura de filas (muestra de 100 mil, completitud, explorador) | 66,7 s | 7,4 s (solo la ruta elegida) |
| Resumen de la base (`get_database_summary`) | 16,1 s | 0 en Analyst; en el panel lateral, `MAX(timestamp)`: 0,0 s |
| Recuento de filas por ruta en *Model Performance* (`get_all_routes_statistics`) | 7,9 s | 0 (sale del perfil) |
| **Perfil de la base en una pasada** (`get_data_profile`) | — | 8,0 s, **una vez** y compartido por todas las pestañas |

Cómo: (1) `RouteDatabase.get_data_profile()` calcula en **una sola consulta agregada** (filas, primera y última fecha, duplicados y nulos de cada columna, por ruta) todo lo que antes salía de más de diez consultas, y `st.cache_data` lo comparte 5 minutos entre las pestañas; (2) `get_last_timestamp()` (`MAX(timestamp)` sobre un índice) reemplaza al resumen completo que el panel lateral pedía en *todas* las pantallas solo para mostrar la hora del último dato; (3) `get_database_summary(include_routes=False)` evita el `DISTINCT` de rutas cuando no hace falta; (4) `query_measurements` ya no lee `created_at` (ningún código la usa) y deja de recorrer las páginas de desbordamiento de la polilínea de todas las filas.

**Lo que no se hizo, a propósito:** los 8,0 s del perfil y los 7,4 s de leer la ruta elegida son recorridos de la tabla que solo desaparecerían con un índice compuesto `(origin, destination)` o separando `polyline` en otra tabla. Ambos son **cambios de esquema sobre una base de 412 MB en producción** (crear un índice bloquea las escrituras del collector mientras dura y, en el bind mount, puede tardar más que su `busy_timeout` de 10 s), por lo que quedan como decisión aparte.

**Cambios en lo que se muestra en "Data Quality"** (la definición cambia, no es un error): *Missing Values* pasa de **13,0 %** (muestra de las 100 mil filas más recientes, contando `id`, `polyline` y `created_at`) a **14,7 %** (toda la base, solo las 21 columnas de medición). *Duplicates* antes contaba filas idénticas **incluyendo `id`**, que es autoincremental, así que daba 0 siempre; ahora cuenta filas repetidas para la misma ruta, instante y fuente (la clave `UNIQUE` debería impedirlas, así que 0 es lo normal y la métrica sirve de comprobación de que la restricción sigue en pie). Un detalle útil: el 99,8 % de esos vacíos (242.685 de 243.151) son 5 columnas que **no existen para ORS** (`no_traffic_time_min`, `traffic_delay_min`, `traffic_length_km`, `departure_time`, `arrival_time`: 48.537 nulos cada una, todas las filas de ORS), así que la métrica mezcla "falta" con "no aplica".

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
- **Resuelto después:** `render_route_status_grid` (Operations) era el único que seguía haciendo una consulta por ruta, porque necesita la última fila completa de cada una. Ahora usa `RouteDatabase.get_latest_per_route()` (una consulta con `ROW_NUMBER()`; dos en total: la última medición y la última con dato de tráfico).

### Operations mostraba "🟢 Free Flow" para rutas sin dato de tráfico

**Síntoma:** la tabla *Route Status Overview* pintaba de verde (Free Flow, 0.0 min de retraso) rutas de las que no había ninguna lectura de tráfico.

**Causa:** el estado salía de `traffic_delay_min` de la **última fila** de cada ruta, y `_safe()` convertía el `NULL` en `0`. ORS no reporta tráfico en tiempo real (el 100% de sus filas trae `traffic_delay_min` nulo), así que cualquier ruta cuya última medición fuera de ORS —la fuente más frecuente en el modo híbrido— quedaba "libre" sin ningún dato que lo respaldara.

**Solución:** el estado se calcula con la **última lectura que sí trae tráfico** (TomTom) y la tabla indica de hace cuánto es y de qué fuente (`Traffic reading`), además de la última medición (`Last measurement`). Si una ruta nunca tuvo lectura de tráfico aparece como "⚪ Sin dato de tráfico", y si la última tiene más de 90 min (unos 3 ciclos de TomTom perdidos) como "⚪ Lectura desactualizada" — útil también como aviso de que el collector lleva rato parado. El tiempo de viaje y la velocidad siguen saliendo de la última medición de cualquier fuente.
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

#### Huecos de recolección: cuánto se pierde, por qué y qué opciones hay

**Medición actualizada (6-nov-2026, 82 días desde el 16-ago):** la recolección corrió el **55%** de los ciclos esperados (6.765 de unos 12.300; ORS cada 15 min + TomTom cada 27 min). Hay 22 huecos de más de 2 h que suman **39 días, el 47,5% de la ventana** (la cifra del 21% de arriba era de finales de septiembre). Por tipo:

| Tipo | Cantidad | Tiempo sin datos | Qué parece |
|---|---|---|---|
| Cortos (< 24 h) | 15 | 9,3 días (mediana 16 h) | Equipo apagado por las noches: empiezan sobre las 21–23 h locales (03–05 UTC) y terminan sobre las 10–11 h (16–17 UTC) |
| Medios (1 a 3 días) | 4 | 6,8 días | Paradas puntuales / fines de semana |
| Largos (> 3 días) | 3 | 23 días (el mayor, 15,8 días: del 7 al 22 de octubre) | Equipo o stack apagado varios días |

**Por qué ocurre (confirmado por quien opera el stack):** **es una decisión deliberada, no una falla**: el equipo anfitrión se apaga a propósito porque, con el volumen de datos ya acumulado, se considera suficiente y no hace falta que esté encendido las 24 h. Los huecos son, por tanto, un *coste aceptado*, y lo importante es que el análisis los trate bien (ver "Consecuencia para los análisis" más abajo: no rellenar las horas sin datos).

Detalle técnico del equipo actual, útil para entender qué pasa al volver a encenderlo: es un sobremesa con Windows en plan *Balanced* y con la suspensión por inactividad, estando enchufado, en **0 (nunca)**, es decir, no se duerme solo. Docker Desktop sí arranca con Windows (`AutoStart`) y los servicios, al arrancar Docker, se levantan solos porque tienen `restart: unless-stopped`. **Pero** esa política **no** reinicia lo que se detuvo a mano, y `docker compose down` además elimina los contenedores: si antes de apagar se hace `down` (o `stop`), al volver a encender hay que hacer `docker compose up -d`. Si se apaga el equipo *sin* hacer `down`, el stack debería volver solo. Para comprobar la configuración en tu equipo:

```powershell
powercfg /getactivescheme                                   # plan de energía activo
powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE        # suspensión por inactividad (0 = nunca)
docker compose ps                                           # ¿está arriba el collector?
```

**Lo que NO se puede hacer:** recuperar los datos perdidos. Las APIs de tráfico (ORS, TomTom) y de clima entregan solo el estado *de ahora*; no existe un histórico al que pedir lo que faltó.

**Si algún día se quiere reducir los huecos** (hoy no es el caso: se aceptan; de menor a mayor esfuerzo; ninguna está implementada en el repo):

| Opción | Qué arregla | Qué no arregla |
|---|---|---|
| Disciplina: tras cualquier `down`/`stop`, `docker compose up -d` de inmediato; revisar con `docker compose ps` o el aviso del dashboard (lateral) | Huecos medios y largos por olvido | Noches con el equipo apagado |
| Tarea programada de Windows (al iniciar sesión: esperar a Docker y ejecutar `docker compose up -d` en la carpeta del repo) | Que el stack vuelva solo tras cada arranque aunque se haya hecho `down` | Noches con el equipo apagado |
| Dejar el equipo encendido 24/7 (y sin suspender/hibernar manualmente) | Los huecos nocturnos | Cortes de luz y reinicios de Windows Update |
| Mover el stack a una máquina siempre encendida (servidor, Raspberry Pi, VM en la nube): mismo `docker-compose.yml` y `.env`, y copiar `data/` | Todos, es la única que da cobertura continua | Requiere una máquina y migrar la base |

**Cómo saber si está recolectando:** el panel lateral del dashboard muestra la hora del último dato y avisa en amarillo si pasan más de 60 min sin datos nuevos (es lo esperado justo después de volver a encender un equipo que estuvo apagado: se quita solo en cuanto llega el primer ciclo); `docker compose ps`; y `tools/check_collection_gaps.py` para medir los huecos.

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
- **`docs/DISENO_ML_RECOMENDACION.md`** — diseño (borrador) del machine learning y las redes neuronales para el asistente de recomendación: qué se puede y qué no se puede afirmar, auditoría de datos, arquitectura, protocolo de validación y fases
- **`docs/research_paper/README.md`** — paper de investigación heredado de urban-mobility-analytics1 (ensemble ML, causal inference, arquitectura medallion)
