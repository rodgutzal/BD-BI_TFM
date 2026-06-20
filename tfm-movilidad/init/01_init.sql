-- Este script se ejecuta automáticamente la primera vez que arranca el contenedor
-- (Docker monta /init en /docker-entrypoint-initdb.d)

-- 1. Habilitar extensiones necesarias
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2. Tabla principal de viajes (basada en el esquema NYC Taxi de Timescale)
CREATE TABLE IF NOT EXISTS rides (
    vendor_id           TEXT,
    pickup_datetime      TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    dropoff_datetime     TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    passenger_count       NUMERIC,
    trip_distance         NUMERIC,
    pickup_longitude       NUMERIC,
    pickup_latitude        NUMERIC,
    rate_code             INTEGER,
    dropoff_longitude       NUMERIC,
    dropoff_latitude        NUMERIC,
    payment_type           INTEGER,
    fare_amount            NUMERIC,
    extra                  NUMERIC,
    mta_tax                NUMERIC,
    tip_amount              NUMERIC,
    tolls_amount             NUMERIC,
    improvement_surcharge      NUMERIC,
    total_amount             NUMERIC,
    pickup_geom             GEOMETRY(Point, 4326),
    dropoff_geom             GEOMETRY(Point, 4326)
);

-- 3. Convertir a hypertable (particionado automático por tiempo)
SELECT create_hypertable('rides', by_range('pickup_datetime'), if_not_exists => TRUE);

-- 4. Índices para acelerar consultas habituales en movilidad
CREATE INDEX IF NOT EXISTS idx_rides_vendor_time ON rides (vendor_id, pickup_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_rides_pickup_geom ON rides USING GIST (pickup_geom);
CREATE INDEX IF NOT EXISTS idx_rides_dropoff_geom ON rides USING GIST (dropoff_geom);

-- 5. Tablas catálogo (dimensiones)
CREATE TABLE IF NOT EXISTS payment_types (
    payment_type INTEGER PRIMARY KEY,
    description  TEXT
);
INSERT INTO payment_types (payment_type, description) VALUES
    (1, 'credit card'), (2, 'cash'), (3, 'no charge'),
    (4, 'dispute'), (5, 'unknown'), (6, 'voided trip')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS rates (
    rate_code   INTEGER PRIMARY KEY,
    description TEXT
);
INSERT INTO rates (rate_code, description) VALUES
    (1, 'standard rate'), (2, 'JFK'), (3, 'Newark'),
    (4, 'Nassau or Westchester'), (5, 'negotiated fare'), (6, 'group ride')
ON CONFLICT DO NOTHING;

-- 6. Trigger para poblar automáticamente las columnas geométricas desde lat/lon
CREATE OR REPLACE FUNCTION set_geom_columns() RETURNS TRIGGER AS $$
BEGIN
    NEW.pickup_geom  := ST_SetSRID(ST_MakePoint(NEW.pickup_longitude, NEW.pickup_latitude), 4326);
    NEW.dropoff_geom := ST_SetSRID(ST_MakePoint(NEW.dropoff_longitude, NEW.dropoff_latitude), 4326);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_set_geom
BEFORE INSERT ON rides
FOR EACH ROW EXECUTE FUNCTION set_geom_columns();

-- 7. Continuous aggregate de ejemplo: viajes por hora (base para dashboards de congestión)
CREATE MATERIALIZED VIEW IF NOT EXISTS rides_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', pickup_datetime) AS hour,
    vendor_id,
    COUNT(*) AS num_trips,
    AVG(trip_distance) AS avg_distance,
    AVG(total_amount) AS avg_fare
FROM rides
GROUP BY hour, vendor_id;
