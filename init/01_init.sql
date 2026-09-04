-- =============================================================
-- init/01_init.sql  (BD_BI_TFM)
-- Se ejecuta UNA SOLA VEZ al primer arranque del contenedor.
-- Docker monta ./init en /docker-entrypoint-initdb.d
--
-- Esquema heredado de BD_BI_TFM (capa de producción / BI), extendido con
-- dos columnas nuevas y compatibles hacia atrás para poder recibir
-- registros de ambas fuentes de datos (OpenRouteService y TomTom):
--   - data_source: de qué API vino el registro ('ors' | 'tomtom')
--   - traffic_delay_min: retraso por tráfico en minutos (sólo TomTom;
--     NULL para registros de ORS, que no reporta tráfico en tiempo real)
-- =============================================================

-- 1. Extensiones
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2. Tabla principal — columnas exactas de traffic_weather_data.csv + extensión BD_BI_TFM
CREATE TABLE IF NOT EXISTS traffic_trips (
    datetime              TIMESTAMPTZ   NOT NULL,
    origin                TEXT          NOT NULL,
    destination           TEXT          NOT NULL,
    distance_km           NUMERIC(8,2),
    duration_min          NUMERIC(8,2),
    temperature           NUMERIC(5,2),
    humidity              INTEGER,
    weather_description   TEXT,
    mobility_level        TEXT,
    data_source            TEXT         DEFAULT 'unknown',
    traffic_delay_min      NUMERIC(8,2)
);

-- 2b. Si la tabla ya existía de una instalación previa de BD_BI_TFM (sin
--     estas dos columnas), se añaden de forma idempotente.
ALTER TABLE traffic_trips ADD COLUMN IF NOT EXISTS data_source TEXT DEFAULT 'unknown';
ALTER TABLE traffic_trips ADD COLUMN IF NOT EXISTS traffic_delay_min NUMERIC(8,2);

-- 3. Convertir a hypertable (particionado automático por tiempo)
SELECT create_hypertable('traffic_trips', by_range('datetime'), if_not_exists => TRUE);

-- 4. Índices para las consultas más habituales
CREATE INDEX IF NOT EXISTS idx_trips_origin_dest
    ON traffic_trips (origin, destination, datetime DESC);

CREATE INDEX IF NOT EXISTS idx_trips_mobility
    ON traffic_trips (mobility_level, datetime DESC);

CREATE INDEX IF NOT EXISTS idx_trips_source
    ON traffic_trips (data_source, datetime DESC);

-- 5. Continuous aggregate: viajes agrupados por hora
CREATE MATERIALIZED VIEW IF NOT EXISTS trips_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', datetime)     AS hour,
    origin,
    destination,
    COUNT(*)                             AS num_trips,
    AVG(duration_min)                    AS avg_duration_min,
    AVG(distance_km)                     AS avg_distance_km,
    AVG(temperature)                     AS avg_temperature,
    AVG(humidity)                        AS avg_humidity,
    AVG(traffic_delay_min)               AS avg_traffic_delay_min,
    ROUND(
        100.0 * SUM(CASE WHEN mobility_level = 'Alta demora' THEN 1 ELSE 0 END)
        / COUNT(*), 1
    )                                    AS pct_alta_demora
FROM traffic_trips
GROUP BY hour, origin, destination;

-- 6. Política de refresco automático cada hora
SELECT add_continuous_aggregate_policy(
    'trips_hourly',
    start_offset      => INTERVAL '3 hours',
    end_offset        => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists     => TRUE
);
