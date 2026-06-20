# Master en Big Data and Buisness Intelligence
## Obtención de datos para el Trabajo de Fin de Master

Este stack levanta en tu máquina, con un solo comando, todo lo necesario para el TFM: base de datos de series temporales con soporte geoespacial, administrador
web (pgAdmin) y herramienta de visualización (Grafana).

## Requisitos
- (Docker Desktop (Windows/Mac))[https://docs.docker.com/desktop/setup/install/windows-install/] o Docker Engine + Docker Compose (Linux)
- 8 GB de RAM disponibles recomendados
- Cliente `psql` (opcional, viene incluido en pgAdmin si no quieres instalarlo)
### Nota: `psql` viene con pgAdimn( que ya se va a usar igual ):
#### Windows
1. Si instalas pgAdmin4 ( el cual se menciona dentro de este documento ), psql no viene incluido directamente, así que mejor instala el cliente oficial de (PostgreSQL)[https://www.postgresql.org/download/windows/].
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

## 1. Estructura del proyecto
```
tfm-movilidad/
├── docker-compose.yml
└── init/
    └── 01_init.sql      <- se ejecuta automáticamente la primera vez
```

## 2. Levantar el stack
Asegurate que Docker Desktop esté corriendo
```bash
cd tfm-movilidad
docker compose up -d
```
Espera 1-2 minutos. Verifica que los 3 contenedores están corriendo:
```bash
docker compose ps
```

## 3. Acceder a cada servicio
| Servicio    | URL                    | Usuario              | Contraseña    |
|-------------|-------------------------|-----------------------|----------------|
| TimescaleDB | localhost:5432          | postgres              | tfm_password   |
| pgAdmin     | http://localhost:8080   | admin@tfm.com         | tfm_password   |
| Grafana     | http://localhost:3000   | admin                 | admin (cambia en 1er login) |

## 4. Conectar desde psql (si lo tienes instalado)
```bash
psql -h localhost -p 5432 -U postgres -d movilidad_urbana
# password: tfm_password
```
#### Nota:
Sí al correr el comando anterrior te marca un error del tipo:
```
psql : The term 'psql' is not recognized as the name of a cmdlet, function, script file, or operable program. Check the spelling of the name, or if a path was included,
verify that the path is correct and try again.
```
puedes correr el psql desde el contenedor usando el comando:
```
docker exec -it movilidad-db psql -U postgres -d movilidad_urbana
```


## 5. Descargar el dataset de movilidad (NYC Taxi, usado como dataset semilla)
El tutorial oficial de Timescale ("Hello NYC") provee el dataset comprimido y
el esquema que ya replicamos en `init/01_init.sql`:
- Dataset: se descarga desde el propio tutorial de Timescale
  https://docs.timescale.com/tutorials/latest/nyc-taxi-cab/dataset-nyc/
- Repo Python con script de descarga + carga automatizada (alternativa recomendada
  para no descargar el CSV manualmente):
  https://github.com/dreamsofcode-io/timescaledb-taxidata

## 6. Cargar los datos (vaciado / "bulk load")
Una vez descomprimido `nyc_data_rides.csv`, dentro de psql:
```sql
\COPY rides(vendor_id, pickup_datetime, dropoff_datetime, passenger_count,
            trip_distance, pickup_longitude, pickup_latitude, rate_code,
            dropoff_longitude, dropoff_latitude, payment_type, fare_amount,
            extra, mta_tax, tip_amount, tolls_amount, improvement_surcharge,
            total_amount)
FROM 'nyc_data_rides.csv' CSV;
```
El trigger `set_geom_columns` rellena automáticamente las columnas geométricas
(`pickup_geom`, `dropoff_geom`) para que PostGIS pueda usarlas de inmediato.

## 7. Verificar que todo cargó bien
```sql
SELECT COUNT(*) FROM rides;
SELECT * FROM rides_hourly ORDER BY hour DESC LIMIT 10;
```

## 8. Conectar Grafana a TimescaleDB
1. Entra a http://localhost:3000
2. Connections → Add new connection → PostgreSQL
3. Host: `timescaledb:5432` (nombre del servicio Docker, no "localhost")
4. Database: `movilidad_urbana` | User: `postgres` | Password: `tfm_password`
5. En "PostgreSQL options" activa **TimescaleDB**
6. Save & Test

## 9. Apagar / limpiar
```bash
docker compose down          # detiene los contenedores (conserva los datos)
docker compose down -v       # detiene y BORRA los datos (empieza de cero)
```
