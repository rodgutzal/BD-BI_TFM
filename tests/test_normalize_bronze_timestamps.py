"""Pruebas de tools/normalize_bronze_timestamps.py.

Todo ocurre sobre bases temporales: ninguna prueba toca data/mobility.db.
"""

import hashlib
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# tools/ no es un paquete (no tiene __init__.py): se carga el script por ruta.
_spec = importlib.util.spec_from_file_location("normalize_bronze", ROOT / "tools" / "normalize_bronze_timestamps.py")
nb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nb)

from src.data_warehouse.bronze_layer import BronzeLayer

LEGACY_A = "2026-05-25 23:54:03.692522+00:00"     # formato antiguo
ISO_A = "2026-05-25T23:54:03.692522+00:00"       # la misma medición, en ISO
LEGACY_B = "2026-05-26 00:10:00.000000+00:00"
ISO_B = "2026-05-26T00:10:00.000000+00:00"


def _insertar(db_path, filas):
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO bronze_measurements (raw_timestamp, origin, destination, travel_time_min, ingestion_timestamp) "
        "VALUES (?, ?, ?, ?, '2026-11-01T00:00:00')",
        filas,
    )
    conn.commit()
    conn.close()


def _filas(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT raw_timestamp, origin, destination FROM bronze_measurements ORDER BY id").fetchall()
    finally:
        conn.close()


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "t.db"
    BronzeLayer(path)      # crea el esquema real, incluido idx_bronze_unique
    return path


@pytest.fixture
def db_mixta(db_path):
    """Una base como la real después de correr el pipeline una vez:
       - A: fila antigua CON su gemela ISO                    -> borrar la antigua
       - B: fila antigua SIN gemela                           -> renombrar
       - C y D: dos antiguas idénticas                        -> renombrar una, borrar la otra
       - E: ya está en ISO                                    -> no se toca

    C y D solo pueden existir si la base se creó ANTES de idx_bronze_unique (el
    índice impide insertar dos filas iguales), así que se quita el índice para
    reproducir ese caso.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("DROP INDEX IF EXISTS idx_bronze_unique")
    conn.commit()
    conn.close()
    _insertar(db_path, [
        (LEGACY_A, "Msida", "Gzira", 5.0),
        (ISO_A, "Msida", "Gzira", 5.0),
        (LEGACY_B, "Msida", "Sliema", 7.0),
        ("2026-06-01 10:00:00+00:00", "Valletta", "Sliema", 9.0),
        ("2026-06-01 10:00:00+00:00", "Valletta", "Sliema", 9.0),   # duplicada exacta entre antiguas
        ("2026-07-01T08:00:00+00:00", "Msida", "Gzira", 6.0),
    ])
    return db_path


# ---------------------------------------------------------------------------
# Funciones puras
# ---------------------------------------------------------------------------

def test_is_legacy_y_normalize():
    """`is_legacy` reconoce el formato antiguo de timestamp, `normalize` lo pasa a ISO y normalizar dos veces da lo mismo."""
    assert nb.is_legacy(LEGACY_A) and not nb.is_legacy(ISO_A)
    assert not nb.is_legacy("") and not nb.is_legacy(None)
    assert nb.normalize(LEGACY_A) == ISO_A
    assert nb.normalize(nb.normalize(LEGACY_A)) == ISO_A     # idempotente


def test_plan_clasifica_cada_fila():
    """El plan clasifica cada fila: gemelas de otra fila ISO, duplicadas entre antiguas, a renombrar y las que no se tocan."""
    rows = [
        (1, LEGACY_A, "Msida", "Gzira"),     # tiene gemela ISO (id 2)
        (2, ISO_A, "Msida", "Gzira"),
        (3, LEGACY_B, "Msida", "Sliema"),    # sin gemela
        (4, "2026-06-01 10:00:00+00:00", "V", "S"),
        (5, "2026-06-01 10:00:00+00:00", "V", "S"),   # duplicada entre antiguas
        (6, "2026-07-01T08:00:00+00:00", "Msida", "Gzira"),
        (7, "otro-formato", "Msida", "Gzira"),        # ni ISO ni antiguo: no se toca
    ]
    plan = nb.build_plan(rows)
    assert plan.total_rows == 7 and plan.legacy_rows == 4
    assert plan.delete_twin == [1]
    assert plan.delete_dup == [5]
    assert plan.rename == [(3, ISO_B), (4, "2026-06-01T10:00:00+00:00")]
    assert plan.rows_after == 5


def test_misma_hora_en_otra_ruta_no_es_gemela():
    """Una fila con la misma hora pero en otra ruta no es gemela y solo se renombra."""
    rows = [(1, LEGACY_A, "Msida", "Gzira"), (2, ISO_A, "Msida", "Sliema")]
    plan = nb.build_plan(rows)
    assert plan.delete_twin == [] and plan.rename == [(1, ISO_A)]


def test_base_sin_filas_antiguas_no_necesita_cambios():
    """Una base sin filas en formato antiguo no necesita cambios."""
    assert not nb.build_plan([(1, ISO_A, "Msida", "Gzira")]).needs_changes


# ---------------------------------------------------------------------------
# Ensayo (dry-run)
# ---------------------------------------------------------------------------

def test_el_ensayo_no_modifica_nada_ni_crea_archivos(db_mixta, capsys):
    """El ensayo (sin `--apply`) no modifica la base ni crea archivos, y lo dice en su salida."""
    antes = _sha(db_mixta)
    carpeta = set(p.name for p in db_mixta.parent.iterdir())

    assert nb.main(["--db", str(db_mixta)]) == 0

    assert _sha(db_mixta) == antes
    assert set(p.name for p in db_mixta.parent.iterdir()) == carpeta     # ni respaldo, ni -wal, ni -shm
    salida = capsys.readouterr().out
    assert "ENSAYO" in salida and "no se modificó nada" in salida
    assert "con separador antiguo" in salida


def test_main_con_base_inexistente_o_sin_tabla(tmp_path, capsys):
    """Con una base inexistente devuelve código 2; con una base sin tabla indica que no hay nada que normalizar."""
    assert nb.main(["--db", str(tmp_path / "no_existe.db")]) == 2
    vacia = tmp_path / "vacia.db"
    sqlite3.connect(vacia).close()
    assert nb.main(["--db", str(vacia)]) == 0
    assert "nada que normalizar" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# Aplicar
# ---------------------------------------------------------------------------

def test_aplicar_borra_duplicados_renombra_el_resto_y_deja_un_respaldo(db_mixta):
    """`--apply` borra las gemelas y duplicadas, renombra el resto al formato ISO y deja un respaldo de la base."""
    original = _filas(db_mixta)
    assert nb.main(["--db", str(db_mixta), "--apply"]) == 0

    despues = _filas(db_mixta)
    assert len(despues) == 4                                         # 6 - 1 (gemela) - 1 (duplicada)
    assert not any(nb.is_legacy(ts) for ts, _o, _d in despues)
    assert sorted(despues) == sorted([
        (ISO_A, "Msida", "Gzira"),
        (ISO_B, "Msida", "Sliema"),
        ("2026-06-01T10:00:00+00:00", "Valletta", "Sliema"),
        ("2026-07-01T08:00:00+00:00", "Msida", "Gzira"),
    ])

    respaldos = list(db_mixta.parent.glob("t.db.bak-*"))
    assert len(respaldos) == 1
    assert _filas(respaldos[0]) == original                          # el respaldo es la base de antes


def test_aplicar_es_idempotente(db_mixta, capsys):
    """Aplicar dos veces da el mismo resultado, la segunda dice que no hay nada que hacer y no crea otro respaldo."""
    nb.main(["--db", str(db_mixta), "--apply"])
    despues = _filas(db_mixta)
    capsys.readouterr()

    assert nb.main(["--db", str(db_mixta), "--apply"]) == 0
    assert _filas(db_mixta) == despues
    assert "Nada que hacer" in capsys.readouterr().out
    assert len(list(db_mixta.parent.glob("t.db.bak-*"))) == 1        # no hizo un segundo respaldo


def test_antes_de_correr_el_pipeline_solo_renombra(db_path):
    """Caso de la base real hoy: filas antiguas sin gemela ISO todavía."""
    _insertar(db_path, [(LEGACY_A, "Msida", "Gzira", 5.0), (LEGACY_B, "Msida", "Sliema", 7.0)])
    plan, _ = nb.apply_changes(db_path)
    assert plan.to_delete == [] and len(plan.rename) == 2
    assert sorted(_filas(db_path)) == sorted([(ISO_A, "Msida", "Gzira"), (ISO_B, "Msida", "Sliema")])


def test_despues_de_normalizar_reingerir_la_misma_medicion_no_duplica(db_path):
    """El objetivo del script: que correr el pipeline no reinserte las filas antiguas."""
    _insertar(db_path, [(LEGACY_A, "Msida", "Gzira", 5.0)])
    nb.apply_changes(db_path)

    df = pd.DataFrame([{"timestamp": ISO_A, "origin": "Msida", "destination": "Gzira", "travel_time_min": 5.0}])
    resultado = BronzeLayer(db_path).ingest(df)
    assert resultado["inserted_records"] == 0
    assert len(_filas(db_path)) == 1


def test_el_indice_unico_sigue_vigente(db_path):
    """Tras normalizar, el índice único de Bronze sigue vigente y rechaza una fila igual a una ya normalizada."""
    _insertar(db_path, [(LEGACY_A, "Msida", "Gzira", 5.0), (LEGACY_B, "Msida", "Sliema", 7.0)])
    nb.apply_changes(db_path)
    conn = sqlite3.connect(db_path)
    indices = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()
    assert "idx_bronze_unique" in indices
    # y sigue haciendo su trabajo: no admite una fila igual a una ya normalizada
    with pytest.raises(sqlite3.IntegrityError):
        _insertar(db_path, [(ISO_A, "Msida", "Gzira", 5.0)])


def test_no_toca_otras_tablas(db_mixta):
    """La normalización no modifica otras tablas, como `route_measurements`."""
    conn = sqlite3.connect(db_mixta)
    conn.execute("CREATE TABLE route_measurements (timestamp TEXT, origin TEXT)")
    conn.execute("INSERT INTO route_measurements VALUES ('2026-05-25 23:54:03+00:00', 'Msida')")
    conn.commit()
    conn.close()

    nb.apply_changes(db_mixta)

    conn = sqlite3.connect(db_mixta)
    assert conn.execute("SELECT timestamp FROM route_measurements").fetchone()[0] == "2026-05-25 23:54:03+00:00"
    conn.close()


# ---------------------------------------------------------------------------
# Seguridad
# ---------------------------------------------------------------------------

def test_si_la_base_esta_en_uso_aborta_sin_cambiar_nada(db_mixta):
    """Otro proceso (el collector) con una escritura abierta: no se aplica nada."""
    antes = _filas(db_mixta)
    otro = sqlite3.connect(db_mixta, isolation_level=None)
    otro.execute("BEGIN IMMEDIATE")           # toma el bloqueo de escritura
    try:
        with pytest.raises(RuntimeError, match="en uso"):
            nb.apply_changes(db_mixta, lock_timeout=0.2)
    finally:
        otro.execute("ROLLBACK")
        otro.close()
    assert _filas(db_mixta) == antes


def test_si_la_verificacion_falla_se_revierte_todo(db_mixta, monkeypatch):
    """Si la verificación final falla, se revierte todo y la base queda como estaba."""
    antes = _filas(db_mixta)

    def verificacion_que_falla(conn, expected_rows):
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(nb, "verify", verificacion_que_falla)
    with pytest.raises(RuntimeError, match="fallo simulado"):
        nb.apply_changes(db_mixta)
    assert _filas(db_mixta) == antes          # ROLLBACK: ni borrados ni renombrados


def test_el_respaldo_se_puede_omitir_solo_por_codigo(db_mixta):
    """La línea de comandos siempre respalda; `backup=False` existe solo para pruebas."""
    plan, respaldo = nb.apply_changes(db_mixta, backup=False)
    assert respaldo is None and plan.needs_changes
    assert list(db_mixta.parent.glob("t.db.bak-*")) == []
