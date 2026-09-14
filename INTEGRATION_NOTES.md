# INTEGRATION_NOTES.md — BD_BI_TFM

Registro completo de cómo se fusionaron **BD-BI_TFM** y **urban-mobility-analytics1**,
qué se decidió en cada punto, y — sobre todo — cada bug real que se encontró
en el proceso y cómo se corrigió. Este documento existe para que cualquiera
(incluido tu tribunal del TFM) pueda auditar exactamente qué cambió y por qué.

---

## 1. Decisiones de integración

Tomadas explícitamente durante la fusión:

| Decisión | Elegido |
|---|---|
| Estrategia general | Base BD_BI_TFM + sumar funciones avanzadas de urban-mobility (analytics, ML, tests, CI/CD) |
| Fuente de datos de tráfico | Ambas, configurables vía `DATA_SOURCE` (`ors` por defecto, `tomtom` opcional) |
| Base de datos | Ambas: TimescaleDB como producción + SQLite como capa local/analítica |
| Dashboard activo (`streamlit_app/app.py`) | `app_multi_dashboard.py` (Executive/Operations/Analyst) — la vista de ruta única (`app_advanced.py`) y la clásica (`app_classic.py`) quedaron en `streamlit_app/legacy_reference/`, no wireadas |
| Pipeline Bronze→Silver→Gold | Automático en cada ciclo del collector (no solo script manual) |

---

## 2. Fusión de datos históricos

Ejecutada por `tools/merge_legacy_data.py` (ya corrida; los resultados están en
`data/raw/route_weather_data.csv` y `data/mobility.db`).

| Fuente | Archivo original | Filas |
|---|---|---|
| BD_BI_TFM (ORS) | `data/raw/legacy_ors_traffic_weather_data.csv` | 97 |
| urban-mobility-analytics1 (TomTom) | `data/raw/legacy_tomtom_route_weather_data.csv` | 2.664 |
| **Total fusionado** | `data/raw/route_weather_data.csv` | **2.761** |

### Mapeo a esquema unificado

**ORS → unificado:**
- `duration_min` → `travel_time_min`
- No hay datos de tráfico en tiempo real → `no_traffic_time_min`, `traffic_delay_min`, `traffic_length_km` quedan `NULL`
- ORS solo pedía **una** lectura de clima por ciclo (no por ubicación) → se replica ese mismo valor en `origin_*` y `destination_*`
- `average_speed_kmh` se calcula (`distance_km / (duration_min/60)`), no venía en el CSV original

**TomTom → unificado:**
- Mapeo casi directo (el esquema de urban-mobility ya era más parecido al unificado)
- `mobility_level` no existía en su CSV original → se calculó con la misma regla que usaba BD_BI_TFM (`"Alta demora"` si `travel_time_min > 20`)

**Ambas:**
- Los `polyline` del histórico de TomTom (2.664 filas) se **descartaron** en la fusión — inflaban el CSV a 23MB por una codificación ineficiente (listas de diccionarios como texto Python), y el dashboard activo no los consume (`render_map` solo usa coordenadas de origen/destino). Las recolecciones nuevas del collector sí siguen guardando su polyline normalmente.
- Los timestamps de BD_BI_TFM eran *naive* (sin timezone). Se asumieron como UTC — el desfase real con Malta (UTC+1/+2) es de 1-2h y no afecta al análisis a nivel de tendencias/patrones horarios.

---

## 3. Bugs encontrados y corregidos

Todos estos bugs existían **en el código original** de uno de los dos repos
(la mayoría en urban-mobility-analytics1, que tenía features más ambiciosas
y, aparentemente, menos probadas de punta a punta — de ahí la cantidad de
archivos `IMPLEMENTATION_SUMMARY` / `PHASES_IMPLEMENTATION` en su raíz). Se
descubrieron ejecutando el código real contra los datos reales, no por
inspección visual.

### 3.1 `src/database.py` — clima perdido en SQLite (el más grave)

**Síntoma:** las 2.664 filas históricas de `route_measurements` en el
`mobility.db` original tenían `temperature`/`humidity`/`weather` en `NULL`,
a pesar de que el CSV correspondiente sí tenía los valores completos.

**Causa:** `collector.py` generaba los registros con las claves
`origin_temperature` / `destination_temperature` / etc., pero
`RouteDatabase.save_records_to_sqlite()` solo leía las claves genéricas
`temperature` / `feels_like` / `humidity` / `weather` (que nunca existían en
el registro) vía `record.get(...)`.

**Fix:** el esquema de `route_measurements` ahora tiene columnas explícitas
`origin_temperature`, `origin_feels_like`, `origin_humidity`, `origin_weather`,
`destination_temperature`, `destination_feels_like`, `destination_humidity`,
`destination_weather` — que es además lo que ya esperaban el dashboard
avanzado y `travel_time_model.py`. Los datos históricos se re-derivaron del
CSV (que sí tenía los valores completos) al fusionar.

### 3.2 `src/analytics.py` — `get_weather_impact()` roto por el fix anterior

Al renombrar las columnas (3.1), `get_weather_impact()` seguía buscando la
columna `temperature` a secas. Se agregó el mismo patrón de fallback que ya
usaba `travel_time_model.py`: `origin_temperature` si existe, si no
`temperature`.

### 3.3 `src/database.py` — `get_time_series()` / `get_route_statistics()`

`valid_metrics` incluía literalmente `"temperature"`/`"humidity"` como
nombres de columna SQL, y `get_route_statistics()` hacía `AVG(temperature)`
— ambos dejaron de existir tras el fix 3.1. Actualizados a
`origin_temperature`/`origin_humidity`.

### 3.4 `src/data_warehouse/bronze_layer.py` — columna inexistente

`ingest()` nunca renombraba `timestamp` → `raw_timestamp` antes de
`to_sql()`, pero la tabla `bronze_measurements` define la columna como
`raw_timestamp`. Insertar fallaba con `no such column: timestamp`. Además,
no filtraba las columnas extra del esquema unificado (`traffic_delay_min`,
`data_source`, `mobility_level`, `polyline`, etc.) antes de insertar, lo que
también rompía el insert. Se corrigieron ambas cosas.

### 3.5 `src/data_warehouse/silver_layer.py` — tres bugs

1. `transform_bronze()` intentaba convertir `df['timestamp']` a fecha
   **antes** de renombrar `raw_timestamp` → `timestamp` — `KeyError`
   inmediato. Se invirtió el orden.
2. No filtraba las columnas propias de Bronze (`id`, `ingestion_timestamp`,
   `data_quality_score`, `validation_status`) antes de insertar en
   `silver_measurements` → `no such column`. Se agregó el filtro.
3. `sqlite3` no puede bindear objetos `pandas.Timestamp` directamente
   (`Error binding parameter 1: type 'Timestamp' is not supported`) — se
   convierten a texto ISO 8601 antes de insertar.
4. `aggregate_hourly()` usaba `MEDIAN()` y `STDDEV()` en SQL — funciones que
   **SQLite no trae integradas** (sí existen en PostgreSQL, de donde
   probablemente se copió el patrón). Reescrito para agrupar con pandas
   (`.median()`, `.std()`), que sí las soporta nativamente.

### 3.6 `src/data_warehouse/gold_layer.py` — dos bugs

1. `calculate_rankings()` tenía `metric: str = 'reliability'` por defecto,
   pero la columna real se llama `reliability_score` — fallaba con
   `no such column: reliability` en cuanto se llamaba sin argumentos
   explícitos.
2. `calculate_kpis()` y `calculate_rankings()` usaban
   `to_sql(if_exists='append')`, un `INSERT` plano. Con el collector
   corriendo cada 1-2 minutos, la segunda vez que se recalculaban las KPIs
   de un mismo día chocaba con el `UNIQUE(date, origin, destination)` de
   `gold_route_kpis` y lanzaba `IntegrityError`. Además, `gold_route_rankings`
   **no tenía ninguna restricción UNIQUE**, así que se habría llenado de
   filas duplicadas del mismo día sin parar. Se cambiaron ambos métodos a
   `INSERT OR REPLACE`, y se agregó `UNIQUE(date, origin, destination)` a
   `gold_route_rankings`.

Verificado corriendo dos ciclos sintéticos consecutivos el mismo día: sin
excepciones, y sin filas duplicadas.

### 3.7 `src/analytics.py` vs `src/analytics/` — colisión de nombres (crítico)

El repo original tenía **a la vez** un archivo `src/analytics.py` (con la
clase `MobilityAnalytics`) y una carpeta `src/analytics/` (con
`causal_analysis.py` y `time_series_analysis.py`) — algo que Python no
permite de forma consistente. En la práctica, `import src.analytics`
resolvía siempre al archivo `.py`, lo que hacía que
`from src.analytics.time_series_analysis import TimeSeriesAnalytics` fuera
**completamente imposible de importar** (`'src.analytics' is not a
package`). Esto afectaba directamente al dashboard **Analyst**, a
`src/api.py`, y a `tests/test_time_series.py` — nunca se habían ejecutado
juntos antes de esta fusión.

**Fix:** `src/analytics.py` se convirtió en `src/analytics/__init__.py`
(la forma estándar de Python de tener un paquete con una clase "principal"
en `__init__.py` y submódulos especializados al lado). Cero cambios
necesarios en ningún otro archivo que ya hacía
`from src.analytics import MobilityAnalytics`. Se agregó
`src/analytics/__main__.py` para no perder el comando documentado
`python -m src.analytics summary` (que de otra forma habría dejado de
funcionar, porque `python -m paquete` ejecuta `paquete/__main__.py`, no
`__init__.py`).

### 3.8 Seguridad: clave de API hardcodeada en el código fuente

`src/api_extraction.py` (BD_BI_TFM) tenía la clave de ORS escrita
directamente en el código, committeada al repo. Se movió a `.env`
(`ORS_API_KEY`), fuera de control de versiones.

### 3.9 Seguridad: `.dockerignore` no excluía `.env`

El `.dockerignore` original de urban-mobility-analytics1 no excluía `.env`,
así que `COPY . .` en el `Dockerfile` horneaba las claves de API reales
**dentro de la imagen Docker** — cualquiera con acceso a la imagen podía
extraerlas. `docker-compose.yml` ya inyecta `.env` en tiempo de ejecución
vía `env_file:`, así que no hace falta que viva dentro de la imagen. Se
agregó `.env`/`.env.local` a `.dockerignore`.

### 3.10 `setup.py` — dos inconsistencias

1. Declaraba `python_requires=">=3.13"`, pero el propio CI del repo solo
   probaba Python 3.10/3.11/3.12 — ninguna versión cumplía su propio
   requisito. El código no usa nada exclusivo de 3.13. Ajustado a `>=3.10`.
2. Leía `README_FINAL.md` para el `long_description`, archivo que no se
   trajo a la fusión (se consolidó toda la documentación dispersa del repo
   original — `COMPLETE_SUMMARY.md`, `IMPLEMENTATION_COMPLETE.md`,
   `IMPLEMENTATION_SUMMARY.txt`, `MASTER_IMPROVEMENTS.md`,
   `PHASES_IMPLEMENTATION.md`, `QUICKSTART.md`, `README_FINAL.md`,
   `RUNNING_NOW.md`, `RESUMEN_PROYECTO.pdf` — en un único `README.md`
   nuevo). Se corrigió para leer `README.md`.

### 3.11 Dependencias declaradas incorrectamente

- `requirements-dev.txt` no declaraba `xgboost` ni `prophet`, a pesar de que
  `src/models/ensemble_predictor.py` los importa con `try/except` — el
  ensemble se degradaba en silencio (2 de 4 modelos) sin ningún aviso.
  Agregados como dependencias opcionales explícitas.
- `dowhy` estaba declarado pero **ningún archivo lo importa** — ni siquiera
  `causal_analysis.py`, que implementa su propia inferencia causal con
  `sklearn`/`scipy`. Se dejó comentado como posible extensión futura.
- `requirements.txt` incluía `pydeck`, que no usa ningún archivo (el mapa
  usa `st.map()` nativo de Streamlit). Eliminado.
- `urllib3` se usa directamente (`from urllib3.util.retry import Retry`) en
  tres clientes HTTP, pero solo estaba presente de forma transitiva (vía
  `requests`). Se agregó explícito.

---

## 4. Archivos deliberadamente NO incluidos

- `backups/` (urban-mobility-analytics1): copias de versiones anteriores de
  `app.py`, `api_extraction.py`, `config.py`, `route_extraction.py` —
  redundantes con lo ya integrado en `src/`.
- `COMPLETE_SUMMARY.md`, `IMPLEMENTATION_COMPLETE.md`,
  `IMPLEMENTATION_SUMMARY.txt`, `MASTER_IMPROVEMENTS.md`,
  `PHASES_IMPLEMENTATION.md`, `QUICKSTART.md`, `README_FINAL.md`,
  `RUNNING_NOW.md`, `RESUMEN_PROYECTO.pdf`: documentación de proceso de
  desarrollo del repo original, consolidada en un único `README.md` nuevo.
- Los `polyline` del histórico masivo de TomTom (ver sección 2).

## 5. Archivos movidos, no eliminados

`streamlit_app/app_advanced.py` → `streamlit_app/legacy_reference/app_advanced.py`
`streamlit_app/app_classic.py` → `streamlit_app/legacy_reference/app_classic.py`
`streamlit_app/components.py` → `streamlit_app/legacy_reference/components.py`
`streamlit_app/charts.py` → `streamlit_app/legacy_reference/charts.py`

Ninguno se borró: siguen siendo funcionales de forma standalone (ver
`README.md`, sección "Dashboards disponibles"), solo no forman parte del
`streamlit_app/app.py` activo.
### 3.12 Dashboards — crash con rutas cuya última medición es de ORS

**Descubierto después de la primera entrega**, al probar el dashboard
Operations en un despliegue real con `DATA_SOURCE=ors` (el default).

**Síntoma:**

```
TypeError: '<=' not supported between instances of 'NoneType' and 'int'
File "streamlit_app/dashboards/operations_dashboard.py", line 76, in render_route_status_grid
    if delay <= 1:
```

**Causa:** con ORS, `traffic_delay_min` (y `no_traffic_time_min`,
`traffic_length_km`) vienen `NULL` — es el comportamiento esperado y ya
documentado (ver sección 2 de este mismo archivo), ORS no reporta tráfico
en tiempo real. El problema es que `dict.get(key, default)` y
`pd.Series.get(key, default)` **solo** usan `default` cuando la *clave*
falta — si la clave existe pero su valor es `None`/`NaN`, devuelven ese
`None`/`NaN` tal cual. Varios puntos de código asumían (incorrectamente)
que `.get('traffic_delay_min', 0)` bastaba para protegerse de valores
faltantes.

Con una consulta de una sola fila (`limit=1`, exactamente lo que usa
`render_route_status_grid`), pandas puede devolver directamente `None`
(no `NaN`) para una columna REAL nula — de ahí el `NoneType` específico del
traceback, en vez de un `float('nan')` silencioso.

**Fix:** se agregó un helper `_safe(value, default=0.0)` (usa `pd.isna()`,
que reconoce tanto `None` como `NaN`) en los 3 archivos afectados, aplicado
en cada punto de riesgo:

- `streamlit_app/dashboards/operations_dashboard.py`: `render_real_time_alerts()`
  (avg_travel_time, avg_delay), `render_route_status_grid()`
  (traffic_delay_min — el crash reportado), `render_24h_predictions()`
  (avg_travel_time)
- `streamlit_app/legacy_reference/components.py`: `render_metric_cards()`
  (no_traffic_time_min, traffic_delay_min), `render_traffic_status()`
  (traffic_delay_min)
- `streamlit_app/legacy_reference/charts.py`: `create_traffic_delay_chart()`
  — aquí el riesgo no era un crash (la iteración fila-por-fila sobre una
  Series sí produce `NaN` en vez de `None`, y las comparaciones con `NaN`
  simplemente son `False`), sino algo más sutil: sin el fix, una ruta sin
  datos de tráfico caía por descarte en la rama `else` y se pintaba de
  **rojo (tráfico pesado)** — el peor color posible para el caso de "no
  sabemos". Ahora tiene su propio color (gris, "sin datos").

`executive_dashboard.py` y `analyst_dashboard.py` no tenían este problema:
sus valores agregados ya pasan por `float(...) if not summary_df.empty
else 0` antes de llegar a cualquier comparación.

Se agregó `tests/test_ors_null_fields.py` como regresión: reproduce el
escenario exacto (una sola medición ORS, `traffic_delay_min=None`) y
confirma que el helper `_safe()` lo neutraliza.

**Si ya tienes el stack corriendo con la versión anterior**, este fix vive
en el código Python, que Docker hornea dentro de la imagen en el build —
reiniciar el contenedor no alcanza, hay que reconstruir:

```bash
docker compose up -d --build dashboard
```

### 3.13 Dashboard Analyst — `UnboundLocalError` con `models/` inexistente

**Descubierto después de la primera entrega**, al probar la pestaña Analyst.

**Síntoma:**

```
UnboundLocalError: cannot access local variable 'model_files' where it is not associated with a value
File "streamlit_app/dashboards/analyst_dashboard.py", line 172, in render_model_performance
    'Model Status': '✅ Trained' if any(m for m in model_files if f"{origin}_{destination}" in m.name) else '❌ Not Trained',
```

**Causa:** `render_model_performance()` solo asignaba `model_files` **dentro**
del bloque `if models_dir.exists():`, pero lo usa más abajo **fuera** de ese
bloque, sin importar si la carpeta existió o no. `models_dir` apunta a
`models/` en la raíz del proyecto — la carpeta que crea
`train_ensemble_models.py` (distinta de `src/models/trained/`, que sí
viene con un modelo de ejemplo) — y como BD_BI_TFM nunca corre ese script
automáticamente, esa carpeta no existe hasta que alguien la ejecuta a mano.
Con `models_dir.exists()` en `False`, el código nunca entraba al `if` y
`model_files` quedaba sin definir para el resto de la función.

**Fix:** `model_files = []` inicializado antes del `if`, para que siempre
exista sin importar la rama que se tome. Se agregó también un mensaje más
claro (`"Models directory not found — run train_ensemble_models.py to
create it."`) en vez de dejarlo en silencio.

Igual que el bug 3.12: si ya tienes el stack corriendo,
`docker compose up -d --build dashboard` para que tome el fix.

### 3.14 Dashboard Executive — `NameError: name 'np' is not defined`

**Descubierto después de la primera entrega**, al probar la pestaña Executive.

**Síntoma:**

```
NameError: name 'np' is not defined
File "streamlit_app/dashboards/executive_dashboard.py", line 131, in render_trend_chart
    z = np.polyfit(range(len(daily_avg)), daily_avg.values, 1)
```

**Causa:** `render_trend_chart()` usa `np.polyfit`/`np.poly1d` para la línea
de tendencia del gráfico de 30 días, pero el archivo nunca importaba
`numpy` — solo `pandas`, `plotly.graph_objects` y `streamlit`. Se revisó
el resto de dashboards (`operations_dashboard.py`, `analyst_dashboard.py`,
`streamlit_app/legacy_reference/*.py`) por el mismo patrón; solo aparecía
aquí.

**Fix:** `import numpy as np` agregado. Verificado con datos reales de
`data/mobility.db` reproduciendo la consulta exacta de la función — la
guarda `if len(daily_avg) > 1:` que ya tenía el código protege
correctamente el caso de un solo día de datos en la ventana (no llega a
llamar `np.polyfit`), así que el único problema real era el import
faltante.

Igual que los anteriores: `docker compose up -d --build dashboard`.

### 3.15 `collector` en bucle de reinicio tras pasar a usuario no-root

**Descubierto después de aplicar el endurecimiento de PRODUCTION.md** (ver
sección 1 de ese archivo), en un despliegue que ya venía corriendo desde
antes del cambio.

**Síntoma:**

```
PermissionError: [Errno 13] Permission denied: '/app/logs/collector.log'
```

`movilidad-collector` en `Restarting (1)` en bucle infinito.

**Causa:** exactamente el riesgo anticipado en `PRODUCTION.md` sección 1
— `collector`/`dashboard` pasaron a correr como `appuser` (UID 1000) en
vez de root. El archivo `logs/collector.log` ya existía de **antes** de
ese cambio (creado por una versión del contenedor que corría como root),
así que sigue siendo propiedad de root en el bind mount — `appuser` no
tiene permiso para escribirlo, aunque sí podría crear un archivo nuevo en
esa misma carpeta sin problema.

**Fix aplicado por el usuario:** borrar `logs/collector.log` (o toda la
carpeta `logs/`) y dejar que el contenedor la regenere desde cero — el
archivo nuevo se crea con el propietario correcto (`appuser`).

**Nota para quien despliegue esto en un servidor nuevo desde cero** (sin
arrastrar archivos de una versión anterior corriendo como root): este
problema específico no debería aparecer, porque nunca existiría un
`logs/collector.log` con ownership viejo de por medio. Solo afecta
**upgrades in-place** de un despliegue que ya estaba corriendo antes de
adoptar el usuario no-root — exactamente el caso aquí.

**Actualización:** el usuario no-root se terminó revirtiendo por completo
(ver PRODUCTION.md sección 1) — este bug ya no puede volver a ocurrir en
este proyecto tal como está entregado, se documenta por si en el futuro
se retoma esa práctica.

### 3.16 TimescaleDB — `column "data_source" does not exist` en un volumen ya existente

**Descubierto después de la primera entrega**, al confirmar que el
collector escribía en TimescaleDB.

**Síntoma:**

```
Error writing to TimescaleDB: column "data_source" of relation "traffic_trips" does not exist
```

**Causa:** no es un bug de código — es una característica de cómo
funciona Postgres/TimescaleDB en Docker. Los scripts en
`/docker-entrypoint-initdb.d` (donde `docker-compose.yml` monta
`init/01_init.sql`) **solo se ejecutan la primerísima vez que se crea el
volumen de datos**, nunca de nuevo en arranques posteriores. `init/01_init.sql`
ya incluía `ALTER TABLE ... ADD COLUMN IF NOT EXISTS data_source` /
`traffic_delay_min` pensado exactamente para bases que vinieran del
BD_BI_TFM original (sin esas columnas) — pero como el volumen `movilidad-db`
de este despliegue ya existía desde antes de la fusión, ese archivo
completo (incluyendo esas líneas de compatibilidad) nunca se volvió a
ejecutar contra él.

**Fix aplicado:** correr las dos líneas `ALTER TABLE` manualmente, una
sola vez, contra la base ya viva:

```bash
docker compose exec timescaledb psql -U postgres -d movilidad_urbana -c "ALTER TABLE traffic_trips ADD COLUMN IF NOT EXISTS data_source TEXT DEFAULT 'unknown';"
docker compose exec timescaledb psql -U postgres -d movilidad_urbana -c "ALTER TABLE traffic_trips ADD COLUMN IF NOT EXISTS traffic_delay_min NUMERIC(8,2);"
```

**Para quien despliegue esto en un servidor nuevo desde cero** (volumen
de TimescaleDB creado por primera vez): este problema no debería aparecer
nunca, porque `init/01_init.sql` corre completo, con las columnas ya
incluidas desde el `CREATE TABLE` original. Solo afecta upgrades in-place
de una base ya existente — mismo patrón que el bug 3.15.

### 3.17 Silver siempre en `+0` y Gold en `no_data`, a pesar de que Bronze sí inserta

**Descubierto después de la primera entrega**, al revisar por qué el log
del collector mostraba `bronze +12, silver +0, gold[fecha]=no_data` en
cada ciclo, ciclo tras ciclo.

**Causa raíz:** `bronze_layer.py` (paso "3. Data type validation", código
original, no algo introducido en la fusión) convierte la columna
`timestamp` a `datetime64` con `pd.to_datetime()` para poder validar y
descartar filas inválidas. El problema es que esa conversión **se queda
así** hasta el momento de guardar — y `pandas.to_sql()` serializa una
columna `datetime64` usando un **espacio** como separador
(`'2026-08-17 04:00:40...'`), no con `'T'` como el resto del proyecto
(`'2026-08-17T04:00:40...'`).

`src/collector.py::_run_incremental_medallion()` vuelve a consultar
`bronze_measurements` justo después de insertar, buscando el `timestamp`
original (con `'T'`) para pasárselo a Silver — como el valor realmente
guardado tiene espacio en vez de `'T'`, la consulta **nunca encontraba
nada**, Silver recibía un DataFrame vacío cada ciclo (de ahí el
`silver +0` constante), y Gold nunca tenía datos del día que agregar (de
ahí el `no_data` constante) — aunque Bronze sí insertaba bien sus 12
filas por ciclo.

**Fix:** después de la validación con `pd.to_datetime()`, se reconvierte
explícitamente a string ISO (`df['timestamp'].apply(lambda t:
t.isoformat())`) antes de guardar, preservando el formato `'T'`
consistente con el resto del proyecto.

**Efecto secundario encontrado al verificar el fix:** con esto, cualquier
base que ya llevara varios ciclos corriendo *antes* del fix va a tener
`bronze_measurements`/`silver_measurements` con una **mezcla** de
timestamps viejos (con espacio) y nuevos (con `'T'`). `pd.to_datetime()`
sin un `format` explícito intenta inferir un solo formato para todo el
lote y se cae en cuanto encuentra una fila que no coincide — esto rompía
específicamente `run_medallion_pipeline.py` (el backfill manual completo,
que sí procesa todo el historial de una sola vez; el flujo incremental
normal del collector no se ve afectado porque cada ciclo es un lote
pequeño e internamente consistente). Se agregó `format='mixed'` en ambos
puntos de parseo (`bronze_layer.py` y `silver_layer.py`) para que cada
fila se interprete individualmente sin importar su formato exacto.

**Verificado** con la base real de un despliegue que ya llevaba corriendo
varios ciclos con el bug: `run_medallion_pipeline.py` ahora procesa las
2.761 filas históricas sin crashear, y el flujo incremental muestra
`silver +3` / `gold=success` en vez de `+0` / `no_data` en un ciclo nuevo
de prueba.

### 3.18 ORS — `403 Forbidden` / `Access to this API has been disallowed` por migración de dominio

**Descubierto en producción real**, una semana después de poner en marcha
el híbrido — ORS empezó a fallar en el 100% de sus ciclos, primero con
`403 Forbidden` genérico y luego, al probar manualmente con `curl`, con
el mensaje explícito `{"error": "Access to this API has been disallowed"}`.

**Investigación (y varios callejones sin salida antes de dar con la causa
real):**
1. Se recalculó el presupuesto de cuota (2.000-2.500/día según la fuente)
   — con el intervalo de 15 min y 12 rutas, el uso real era de solo
   46-58% del límite diario. La cuota no explicaba el fallo.
2. Se revisó el dashboard de la cuenta (`account.heigit.org`): la clave
   mostraba **2.000/2.000 de cuota disponible, sin usar nada** — la clave
   ni siquiera estaba cerca de su límite.
3. Se generó una clave nueva por si la original había sido revocada — el
   mismo error persistió incluso con una clave recién creada y con cuota
   completa.

**Causa real, encontrada en el anuncio oficial de HeiGIT** (la
organización detrás de ORS): `api.openrouteservice.org` — el dominio que
usaba `src/ors_client.py` desde el principio de la fusión — fue
**apagado por completo el 24 de agosto de 2026**, como parte de una
migración hacia un dominio unificado (`api.heigit.org`) anunciada desde
abril de 2026. El aviso oficial es explícito: *"tu clave ya está
preparada para las URLs nuevas, y la cuota que ves en tu dashboard ya es
la de `api.heigit.org`"* — es decir, nunca fue un problema de la clave,
ninguna clave (vieja o nueva) iba a funcionar contra un dominio que ya no
existe.

**Fix:** `ROUTE_URL` en `src/ors_client.py` actualizada según la tabla de
migración oficial:

```
api.openrouteservice.org/v2/directions  ->  api.heigit.org/openrouteservice/v2/directions
```

El resto de la petición (headers, formato del body, respuesta) no cambió
— la migración es únicamente de dominio/ruta.

**Lección para el futuro:** con servicios externos en evolución activa
(como quedó claro con TomTom y HERE también), un error de autenticación/
acceso no siempre es sobre la clave — vale la pena revisar primero si el
proveedor publicó algún aviso de migración o depreciación antes de asumir
que el problema está del lado de la cuenta.

