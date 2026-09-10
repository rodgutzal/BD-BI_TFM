# PRODUCTION.md — Endurecimiento para servidor real

BD_BI_TFM corre hoy en tu máquina, pero está preparado para moverse a un
servidor real (red privada o con salida a internet) sin rearquitectura.
Este documento explica qué se endureció, por qué, y qué falta si más
adelante decides exponerlo a internet.

## Qué se hizo (alcance "lo esencial")

### 1. Usuarios no-root en los contenedores propios — **revertido**

Se probó (`collector`/`dashboard` corriendo como `appuser`, UID/GID 1000,
en vez de root), pero causó un problema real en la práctica: un
despliegue que ya venía corriendo *antes* de este cambio tenía archivos en
`./logs` con ownership de root (de cuando el contenedor sí corría como
root) — el nuevo `appuser` no podía escribirlos, y `collector` quedó en
bucle de reinicio (`PermissionError`). Ver INTEGRATION_NOTES.md, bug 3.15.

Se revirtió a **root** por simplicidad — es el estado actual. `timescaledb`,
`pgadmin` y `sqlite-web` son imágenes de terceros que gestionan sus
propios usuarios internamente, no se tocaron en ningún momento.

**Si más adelante quieres retomarlo** (recomendable para un servidor con
acceso multiusuario real), la forma robusta de hacerlo sin repetir el
mismo problema es con un **entrypoint script** que corrija el ownership de
`./data`/`./logs` en cada arranque del contenedor (antes de bajar
privilegios a `appuser`), en vez de solo `USER appuser` al final del
`Dockerfile` — que solo controla permisos en tiempo de *build*, no puede
arreglar archivos que ya existen en un bind mount de una ejecución
anterior. No se implementó esta vez para no introducir una pieza nueva
sin poder probarla contra un Docker real primero.

### 2. Healthchecks reales + `depends_on` que espera de verdad

Antes, `depends_on: - timescaledb` solo esperaba a que el **contenedor**
arrancara, no a que Postgres estuviera realmente listo para aceptar
conexiones — en un servidor con disco más lento o bajo más carga, el
collector/dashboard podían intentar conectarse antes de tiempo y fallar en
su primer intento. Ahora:

- `timescaledb`: `pg_isready` cada 10s
- `collector`: no tiene puerto HTTP que consultar, así que se agregó un
  **heartbeat** — `src/collector.py` escribe `logs/heartbeat` con la hora
  después de cada ciclo exitoso, y el healthcheck falla si pasaron más de
  300s (2.5x el `--interval` por defecto) sin uno nuevo
- `dashboard`: consulta `/_stcore/health`, el endpoint de salud nativo de
  Streamlit
- `pgadmin` y `sqlite-web`: no se les agregó healthcheck explícito (son
  imágenes de terceros sin garantía de tener `curl`/`wget` disponible
  adentro; agregar uno a ciegas podía fallar de forma menos predecible que
  no tener ninguno)

`dashboard` y `collector` ahora esperan `condition: service_healthy` de
`timescaledb` antes de arrancar, no solo `service_started`.

### 3. Límites de recursos por servicio

Cada servicio tiene un tope de CPU/memoria (`deploy.resources.limits`) —
sin esto, un solo contenedor con un bug (o un pico de tráfico) podría
consumir todos los recursos del servidor y tumbar a los demás. Valores
elegidos con margen generoso para el tamaño de este proyecto, no ajustados
al límite — si en el futuro ves que algún contenedor se queda corto (por
ejemplo, `dashboard` con datasets mucho más grandes), son los primeros
números a subir.

### 4. Contraseñas separadas y más fuertes

- **Antes**: pgAdmin reusaba literalmente la contraseña de Postgres
  (`PGPASSWORD`) — si alguien adivinaba/filtraba el login de pgAdmin, tenía
  también la contraseña real de la base de datos.
- **Ahora**: `PGADMIN_PASSWORD` es una variable separada.
- **`sqlite-web` no tenía NINGUNA autenticación** — cualquiera con acceso a
  ese puerto podía leer y editar `mobility.db` libremente. Ahora requiere
  `SQLITE_WEB_PASSWORD`.
- `PGPASSWORD` (la de Postgres) se dejó sin cambiar a propósito: Postgres
  solo la usa en el primer arranque del volumen — cambiarla en `.env` sin
  además rotarla dentro de Postgres (`ALTER USER postgres PASSWORD ...`)
  simplemente rompe la autenticación de un despliegue que ya tiene datos.
  Ver el comentario en `.env` para el comando exacto si quieres rotarla.

### 5. Puertos de administración solo en `127.0.0.1`

`timescaledb` (5432), `pgadmin` (8080) y `sqlite-web` (8082) ahora se
publican como `127.0.0.1:puerto:puerto` en vez de `puerto:puerto` — antes
escuchaban en `0.0.0.0`, es decir, alcanzables desde **cualquier
dispositivo de la misma red**, no solo desde tu máquina. Con el cambio,
solo son alcanzables desde el propio host. `dashboard` (8501) es la
excepción intencional: es la aplicación en sí, se mantiene expuesta.

**Efecto práctico para ti ahora mismo:** ninguno — seguías accediendo a
todo por `localhost`, así que `127.0.0.1:8080` funciona exactamente igual
que antes desde tu Windows. El cambio importa el día que esto corra en un
servidor de verdad.

### 6. Rotación de logs

Todos los servicios ahora usan el driver `json-file` con
`max-size: 10m, max-file: 3` — sin esto, `docker compose logs` de un
collector corriendo por semanas/meses podía crecer sin límite hasta llenar
el disco del servidor.

### 7. Versiones de imagen fijadas

`pgadmin` y `sqlite-web` no tenían tag explícito (`latest` implícito) —
significa que un `docker compose pull` en el futuro podía traer una
versión distinta sin aviso, con el riesgo de romper algo silenciosamente.
Fijadas a `dpage/pgadmin4:9.17` y `coleifer/sqlite-web:0.7.2` (las
estables más recientes al momento de este cambio). `timescaledb-ha:pg17`
ya estaba razonablemente fijado (pins la versión mayor de Postgres) y no
se tocó.

## Qué NO se hizo (quedó fuera del alcance "lo esencial")

No elegiste estas opciones cuando te pregunté, así que no se
implementaron — pero el resto de las decisiones de arriba están pensadas
para no tener que rehacer nada si más adelante sí las quieres:

- **Reverse proxy con HTTPS** (nginx/traefik + certbot): necesario recién
  si `dashboard` va a ser alcanzable desde internet público. Con la
  arquitectura actual (dashboard como único puerto expuesto, todo lo demás
  en 127.0.0.1), agregar esto después es sencillo: un servicio `nginx`
  nuevo en `docker-compose.yml` que haga proxy hacia `dashboard:8501`, sin
  tocar nada de lo existente.
- **Backups automáticos** de TimescaleDB/SQLite: no configurados. Para
  SQLite, un `cp data/mobility.db backups/mobility-$(date +%F).db` por
  cron alcanza. Para TimescaleDB, `pg_dump` programado o los backups
  nativos de `timescaledb-ha`.
- **Usuario no-root para `timescaledb`/`pgadmin`/`sqlite-web`**: son
  imágenes de terceros — ya gestionan sus propios usuarios internamente
  (pgAdmin4 corre como `pgadmin`, no root, desde hace varias versiones);
  no había nada que corregir ahí.

## Checklist si el día de mañana esto sale a internet público

1. Reverse proxy (nginx/traefik) con HTTPS delante de `dashboard` — nunca
   Streamlit HTTP directo al puerto 8501 desde internet.
2. Firewall del servidor: solo 80/443 abiertos hacia afuera (todo lo demás
   ya está en 127.0.0.1, así que en realidad el firewall del SO es la
   última capa, no la única).
3. Rotar `PGPASSWORD` de verdad (ver sección 4) — el valor que trae este
   proyecto (`tfm_password`) es un default de desarrollo, no debería llegar
   a un servidor público tal cual.
4. Backups automáticos (ver arriba) — sin reverse proxy ni backups, un
   servidor expuesto sin respaldo es el escenario de mayor riesgo.
5. Considerar autenticación adicional delante de pgAdmin/sqlite-web (están
   en 127.0.0.1, pero si alguna vez necesitas alcanzarlos remotamente, hazlo
   por VPN/túnel SSH — no los vuelvas a exponer directo a internet).

## Recolección híbrida (ORS + TomTom en paralelo)

Descubierto en producción real: con `DATA_SOURCE=tomtom` y el intervalo
original de 2 minutos, la clave de TomTom empezó a devolver
`403 Forbidden` en todas las rutas a los pocos días. Investigando la
causa exacta (el dashboard de uso de TomTom, ver captura compartida
durante el debugging), se confirmó que la cuota real es **mensual**
(20.000 peticiones/mes para la Routing API), no diaria como se había
asumido inicialmente — con 12 rutas cada 2 minutos, eso son ~263.000
peticiones/mes, 13 veces el límite. Se agotaba en ~2-3 días.

**Solución implementada:** `HybridScheduler`
(`src/collector.py`) corre dos `DataCollector` (uno ORS, uno TomTom) en
paralelo dentro del mismo proceso, cada uno con su propio temporizador
independiente — no ciclos alternados, cada fuente respeta su propio
intervalo sin importar qué esté haciendo la otra.

**Números calculados y verificados** (con las 12 rutas de
`src/locations.py`):

| Fuente | Cuota real | Intervalo elegido | Uso resultante |
|---|---|---|---|
| ORS | 2.500/día, 40.000/mes | 15 min | ~35.000/mes (88% del límite mensual) |
| TomTom | 20.000/mes | 27 min | ~19.500/mes (97% del límite, margen ajustado a propósito) |

Se verificó también que OpenWeather (ambas fuentes disparan sus propias
llamadas de clima por ubicación única en cada ciclo, así que el volumen
combinado de ambas se suma) no se convierte en el nuevo cuello de
botella: su free tier permite 1.000.000 de llamadas/mes, muy por encima
del uso combinado estimado (~32.000/mes).

**Si cambia el número de rutas** (`src/locations.py`), estos intervalos
dejan de ser válidos — hay que recalcular. La fórmula: `intervalo_min =
(días_del_mes × 24 × 60) / (cuota_mensual / número_de_rutas)`.

**Implicación para el dashboard/análisis:** con este esquema, la mayoría
de las mediciones (ORS, cada 15 min) no tienen `traffic_delay_min` real
— solo las de TomTom (cada 27 min) sí. Ya está cubierto por el fix del
bug 3.12 (`_safe()` en los dashboards), pero vale la pena tenerlo
presente al interpretar tendencias de tráfico: los picos de dato real de
congestión aparecen con menor frecuencia que las mediciones de tiempo de
viaje en sí.
