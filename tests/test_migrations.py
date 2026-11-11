"""Tests de las migraciones del CSV histórico: a SQLite (src/migration.py) y a TimescaleDB (src/timescale_migration.py).

Sin Postgres real: `psycopg2` se sustituye por un módulo falso que guarda las filas que se habrían insertado.
"""

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import migration, timescale_migration  # noqa: E402

CABECERA = (
    "timestamp,origin,destination,data_source,distance_km,travel_time_min,traffic_delay_min,"
    "origin_temperature,origin_humidity,origin_weather,mobility_level"
)
FILAS_OK = [
    "2026-09-01T10:00:00+00:00,Msida,Gzira,tomtom,3.2,9.5,1.2,22.5,60,cielo claro,Normal",
    "2026-09-01T10:30:00+00:00,Msida,Gzira,ors,3.2,8.0,,22.0,61,cielo claro,Normal",
]


def _csv(tmp_path, *filas, cabecera=CABECERA):
    ruta = tmp_path / "historico.csv"
    ruta.write_text("\n".join([cabecera, *filas]) + "\n", encoding="utf-8")
    return ruta


def _filas_db(db_path):
    con = sqlite3.connect(db_path)
    try:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute("SELECT * FROM route_measurements ORDER BY timestamp")]
    finally:
        con.close()


# ---------------------------------------------------------------------------
# CSV -> SQLite
# ---------------------------------------------------------------------------


def test_migra_el_csv_a_sqlite(tmp_path):
    """Migra las filas del CSV a SQLite conservando la fuente, el tiempo de viaje, el clima y los nulos."""
    db = tmp_path / "m.db"
    assert migration.migrate_csv_to_sqlite(_csv(tmp_path, *FILAS_OK), db) == 2
    filas = _filas_db(db)
    assert [f["data_source"] for f in filas] == ["tomtom", "ors"]
    assert filas[0]["travel_time_min"] == 9.5 and filas[0]["origin_weather"] == "cielo claro"
    assert filas[1]["traffic_delay_min"] is None  # celda vacía -> NULL, no 0


def test_dry_run_no_crea_la_base(tmp_path):
    """Con `dry_run`, cuenta las filas pero no crea la base de datos."""
    db = tmp_path / "m.db"
    assert migration.migrate_csv_to_sqlite(_csv(tmp_path, *FILAS_OK), db, dry_run=True) == 2
    assert not db.exists()


def test_descarta_filas_sin_campos_obligatorios(tmp_path):
    """Se descartan las filas a las que les falta el timestamp o el origen."""
    ruta = _csv(
        tmp_path,
        FILAS_OK[0],
        ",Msida,Gzira,tomtom,3,9,1,20,50,x,Normal",
        "2026-09-01T11:00:00+00:00,,Gzira,tomtom,3,9,1,20,50,x,Normal",
    )
    assert migration.migrate_csv_to_sqlite(ruta, tmp_path / "m.db") == 1
    assert len(_filas_db(tmp_path / "m.db")) == 1


def test_data_source_vacio_o_ausente_pasa_a_unknown(tmp_path):
    """Una fuente de datos vacía o ausente en el CSV se guarda como «unknown»."""
    vacio = _csv(tmp_path, "2026-09-01T10:00:00+00:00,Msida,Gzira,,3,9,1,20,50,x,Normal")
    assert migration.migrate_csv_to_sqlite(vacio, tmp_path / "a.db") == 1
    assert _filas_db(tmp_path / "a.db")[0]["data_source"] == "unknown"

    sin_columna = tmp_path / "b.csv"
    sin_columna.write_text("timestamp,origin,destination,travel_time_min\n2026-09-01T10:00:00+00:00,A,B,7\n")
    assert migration.migrate_csv_to_sqlite(sin_columna, tmp_path / "b.db") == 1
    assert _filas_db(tmp_path / "b.db")[0]["data_source"] == "unknown"


def test_un_valor_numerico_ilegible_queda_nulo_sin_romper_la_migracion(tmp_path):
    """Un valor numérico ilegible queda como nulo y la fila se migra igualmente."""
    ruta = _csv(tmp_path, "2026-09-01T10:00:00+00:00,Msida,Gzira,tomtom,3,abc,1,20,50,x,Normal")
    assert migration.migrate_csv_to_sqlite(ruta, tmp_path / "m.db") == 1
    assert _filas_db(tmp_path / "m.db")[0]["travel_time_min"] is None


def test_csv_inexistente_vacio_o_sin_columnas_obligatorias_devuelve_cero(tmp_path):
    """Un CSV inexistente, vacío o sin las columnas obligatorias devuelve 0 filas y no crea la base."""
    assert migration.migrate_csv_to_sqlite(tmp_path / "no_existe.csv", tmp_path / "m.db") == 0
    solo_cabecera = _csv(tmp_path)
    assert migration.migrate_csv_to_sqlite(solo_cabecera, tmp_path / "m.db") == 0
    sin_destino = tmp_path / "x.csv"
    sin_destino.write_text("timestamp,origin\n2026-09-01T10:00:00+00:00,A\n")
    assert migration.migrate_csv_to_sqlite(sin_destino, tmp_path / "m.db") == 0
    assert not (tmp_path / "m.db").exists()


def test_las_lineas_corruptas_del_csv_se_saltan(tmp_path):
    """Las líneas corruptas del CSV se saltan y se migran las demás."""
    ruta = _csv(
        tmp_path, FILAS_OK[0], "esto,no,es,una,fila,valida,porque,tiene,demasiadas,columnas," "a,b,c,d,e,f", FILAS_OK[1]
    )
    assert migration.migrate_csv_to_sqlite(ruta, tmp_path / "m.db") == 2


def test_migrar_dos_veces_no_duplica_filas(tmp_path):
    """El índice único de Bronze/route_measurements hace idempotente la migración."""
    ruta, db = _csv(tmp_path, *FILAS_OK), tmp_path / "m.db"
    migration.migrate_csv_to_sqlite(ruta, db)
    migration.migrate_csv_to_sqlite(ruta, db)
    assert len(_filas_db(db)) == 2


# ---- CLI (src.migration.main) ----


@pytest.fixture
def cli(monkeypatch):
    """Ejecuta main() sin tocar data/: registra con qué argumentos se llamó a migrate_csv_to_sqlite."""
    llamadas = []

    def falso(csv_path, db_path, dry_run=False):
        llamadas.append({"csv": csv_path, "db": db_path, "dry_run": dry_run})
        if falso.error:
            raise falso.error
        return falso.resultado

    falso.resultado, falso.error = 3, None
    monkeypatch.setattr(migration, "migrate_csv_to_sqlite", falso)

    def ejecutar(*args, respuesta=None):
        monkeypatch.setattr(sys, "argv", ["migration", *args])
        if respuesta is not None:
            monkeypatch.setattr("builtins.input", lambda _="": respuesta)
        return migration.main()

    ejecutar.llamadas, ejecutar.falso = llamadas, falso
    return ejecutar


def test_cli_dry_run_no_pide_confirmacion(cli):
    """La línea de comandos con `--dry-run` no pide confirmación y migra en modo ensayo."""
    assert cli("--dry-run") == 0
    assert cli.llamadas[0]["dry_run"] is True


def test_cli_cancelada_no_migra(cli):
    """Si el usuario cancela la confirmación, no se migra nada."""
    assert cli(respuesta="no") == 0 and cli.llamadas == []


def test_cli_confirmada_o_con_skip_migra_y_usa_las_rutas_del_proyecto(cli):
    """Con confirmación o `--skip-confirmation` se migra usando las rutas del CSV y de la base del proyecto."""
    assert cli(respuesta="yes") == 0
    assert cli("--skip-confirmation") == 0
    assert len(cli.llamadas) == 2 and all(c["dry_run"] is False for c in cli.llamadas)
    assert cli.llamadas[0]["csv"] == ROOT / "data" / "raw" / "route_weather_data.csv"
    assert cli.llamadas[0]["db"] == ROOT / "data" / "mobility.db"


def test_cli_devuelve_error_si_no_se_importa_nada_o_falla(cli):
    """La línea de comandos devuelve código de error si no se importa ninguna fila o la migración falla."""
    cli.falso.resultado = 0
    assert cli("--skip-confirmation") == 1

    cli.falso.error = RuntimeError("disco lleno")
    assert cli("--skip-confirmation") == 1


# ---------------------------------------------------------------------------
# CSV -> TimescaleDB (psycopg2 falso)
# ---------------------------------------------------------------------------


class ConexionFalsa:
    def __init__(self, falla=False):
        self.filas, self.sql, self.commits, self.rollbacks, self.cerrada, self.falla = [], None, 0, 0, False, falla

    def cursor(self):
        conexion = self

        class Cursor:
            def executemany(self, sql, filas):
                if conexion.falla:
                    raise RuntimeError("tabla inexistente")
                conexion.sql, conexion.filas = sql, list(filas)

            def close(self):
                pass

        return Cursor()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.cerrada = True


@pytest.fixture
def pg(monkeypatch):
    """psycopg2 falso: guarda los parámetros de conexión y devuelve una conexión que registra lo insertado."""
    conexion = ConexionFalsa()
    parametros = {}

    def connect(**kwargs):
        parametros.update(kwargs)
        return conexion

    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=connect))
    conexion.parametros = parametros
    return conexion


def test_backfill_inserta_las_filas_con_el_orden_de_columnas_de_traffic_trips(tmp_path, pg):
    """El backfill a Timescale inserta cada fila de `traffic_trips` con el orden de columnas correcto y hace commit."""
    assert timescale_migration.backfill(_csv(tmp_path, *FILAS_OK)) == 2
    assert pg.commits == 1 and pg.cerrada
    assert "INSERT INTO traffic_trips" in pg.sql and pg.sql.count("%s") == 11
    # (datetime, origin, destination, distance_km, duration_min, temperature, humidity, weather, level, source, delay)
    assert pg.filas[0] == (
        "2026-09-01T10:00:00+00:00",
        "Msida",
        "Gzira",
        3.2,
        9.5,
        22.5,
        60,
        "cielo claro",
        "Normal",
        "tomtom",
        1.2,
    )
    assert pg.parametros["dbname"] and pg.parametros["host"]  # se leen de src.config


def test_backfill_celdas_vacias_van_como_null_y_no_como_nan(tmp_path, pg):
    """Regresión: una celda vacía llegaba como NaN (float) incluso a columnas de texto (origin_weather), que
    Postgres rechaza; con ello fallaba y se revertía todo el backfill. Ahora es None (NULL), y data_source
    vacío pasa a 'unknown' como en la migración a SQLite."""
    fila = "2026-09-01T10:00:00+00:00,Msida,Gzira,,3.2,9.5,,22.5,60,,Normal"
    assert timescale_migration.backfill(_csv(tmp_path, fila)) == 1
    datetime_, _, _, dist, dur, temp, hum, clima, nivel, fuente, retraso = pg.filas[0]
    assert (clima, retraso) == (None, None) and fuente == "unknown"
    assert (dist, dur, temp, hum, nivel) == (3.2, 9.5, 22.5, 60, "Normal")
    assert all(type(v) in (str, float, int, type(None)) for v in pg.filas[0])  # sin numpy ni NaN
    assert not any(isinstance(v, float) and v != v for v in pg.filas[0])


def test_backfill_con_error_hace_rollback_y_devuelve_cero(tmp_path, pg):
    """Si el backfill falla, hace rollback, cierra la conexión y devuelve 0."""
    pg.falla = True
    assert timescale_migration.backfill(_csv(tmp_path, *FILAS_OK)) == 0
    assert pg.rollbacks == 1 and pg.commits == 0 and pg.cerrada


def test_backfill_csv_inexistente_o_vacio_no_se_conecta(tmp_path, monkeypatch):
    """Con un CSV inexistente o vacío, el backfill no abre ninguna conexión."""

    def no_debe_conectar(**kwargs):
        raise AssertionError("no debería abrir conexión")

    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=no_debe_conectar))
    assert timescale_migration.backfill(tmp_path / "no_existe.csv") == 0
    assert timescale_migration.backfill(_csv(tmp_path)) == 0


def test_backfill_sin_psycopg2_instalado_devuelve_cero(tmp_path, monkeypatch):
    """Si `psycopg2` no está instalado, el backfill devuelve 0 en vez de fallar."""
    monkeypatch.setitem(sys.modules, "psycopg2", None)  # import -> ImportError
    assert timescale_migration.backfill(_csv(tmp_path, *FILAS_OK)) == 0


def test_backfill_main_devuelve_el_codigo_segun_las_filas(monkeypatch):
    """`main` del backfill devuelve 0 si migró filas y 1 si no migró ninguna."""
    monkeypatch.setattr(timescale_migration, "backfill", lambda csv: 5)
    assert timescale_migration.main() == 0
    monkeypatch.setattr(timescale_migration, "backfill", lambda csv: 0)
    assert timescale_migration.main() == 1
