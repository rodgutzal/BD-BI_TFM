-- =============================================================
-- init/01_init.sql
-- Se ejecuta UNA SOLA VEZ al primer arranque del contenedor.
-- Docker monta ./init en /docker-entrypoint-initdb.d
-- =============================================================

-- 1. Extensiones
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2. Tabla principal — columnas exactas de traffic_weather_data.csv
CREATE TABLE IF NOT EXISTS traffic_trips (
    datetime              TIMESTAMPTZ   NOT NULL,
    origin                TEXT          NOT NULL,
    destination           TEXT          NOT NULL,
    distance_km           NUMERIC(8,2),
    duration_min          NUMERIC(8,2),
    temperature           NUMERIC(5,2),
    humidity              INTEGER,
    weather_description   TEXT,
    mobility_level        TEXT
);

-- 3. Convertir a hypertable (particionado automático por tiempo)
SELECT create_hypertable('traffic_trips', by_range('datetime'), if_not_exists => TRUE);

-- 4. Índices para las consultas más habituales
CREATE INDEX IF NOT EXISTS idx_trips_origin_dest
    ON traffic_trips (origin, destination, datetime DESC);

CREATE INDEX IF NOT EXISTS idx_trips_mobility
    ON traffic_trips (mobility_level, datetime DESC);

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
