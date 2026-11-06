"""
Normaliza los timestamps ANTIGUOS de `bronze_measurements` (separador ' ' en
vez de 'T') para que coincidan con el formato ISO 8601 del resto del proyecto.

Por qué existe
--------------
Un bug anterior de bronze_layer.py guardaba `raw_timestamp` con un espacio
('2026-05-25 23:54:03.692522+00:00') en vez de 'T'
('2026-05-25T23:54:03.692522+00:00'). Las filas ya guardadas así siguen ahí, y
como el índice único de Bronze (`idx_bronze_unique`) compara texto, trata a la
fila antigua y a la misma medición en formato ISO como distintas. Efecto: la
primera vez que se corre `python -m src.run_medallion_pipeline`, Bronze
reinserta como "nuevas" esas mediciones (medido sobre una copia de la base real:
2.761 filas duplicadas). Silver y Gold NO se ven afectadas (Silver deduplica
sobre el timestamp ya normalizado); solo se infla el conteo de Bronze.

Qué hace
--------
Para cada fila de Bronze con separador ' ':
  1. si ya existe la MISMA medición en formato ISO (mismo timestamp normalizado,
     origen y destino)  ->  se BORRA la fila antigua (es un duplicado);
  2. si hay varias filas antiguas que normalizan a lo mismo  ->  se conserva la
     de menor id y se borran las demás;
  3. en cualquier otro caso  ->  se RENOMBRA al formato ISO.
Es válido tanto ANTES de correr el pipeline (solo renombra) como DESPUÉS (borra
los duplicados que ya se hayan generado). No toca ninguna otra tabla ni otras
filas de Bronze, y es idempotente: una segunda ejecución no encuentra nada.

Seguridad
---------
  - Por defecto es un ENSAYO (dry-run): solo lee y muestra qué haría. No
    modifica nada. (Se abre con `immutable=1`: no crea archivos -wal/-shm;
    solo es fiable con el collector APAGADO.)
  - Para aplicar hay que pasar --apply. Antes de tocar nada hace una COPIA DE
    RESPALDO consistente (API de backup de SQLite) junto a la base y la verifica.
  - Toma un bloqueo exclusivo: si otro proceso (el collector) tiene la base
    abierta para escribir, ABORTA sin cambiar nada.
  - Todo ocurre en UNA transacción; antes de confirmar verifica el resultado
    (sin filas antiguas, sin duplicados, integridad). Si algo falla, ROLLBACK.

Uso (desde la raíz del proyecto, con el stack apagado: `docker compose down`):
    python tools/normalize_bronze_timestamps.py                 # ensayo, no cambia nada
    python tools/normalize_bronze_timestamps.py --apply         # aplica (con respaldo)
    python tools/normalize_bronze_timestamps.py --db otra.db    # otra base
"""

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mobility.db"

# 'YYYY-MM-DD ' al inicio: fecha, UN espacio, y luego la hora.
_LEGACY = re.compile(r"^\d{4}-\d{2}-\d{2} ")


def is_legacy(raw_timestamp: str) -> bool:
    return bool(raw_timestamp) and _LEGACY.match(raw_timestamp) is not None


def normalize(raw_timestamp: str) -> str:
    """'2026-05-25 23:54:03+00:00' -> '2026-05-25T23:54:03+00:00' (solo el
    primer espacio, el que separa fecha y hora)."""
    return raw_timestamp[:10] + "T" + raw_timestamp[11:]


@dataclass
class Plan:
    total_rows: int = 0
    legacy_rows: int = 0
    delete_twin: List[int] = field(default_factory=list)      # ya existe su gemela ISO
    delete_dup: List[int] = field(default_factory=list)       # duplicada entre antiguas
    rename: List[Tuple[int, str]] = field(default_factory=list)   # (id, timestamp ISO)

    @property
    def to_delete(self) -> List[int]:
        return self.delete_twin + self.delete_dup

    @property
    def rows_after(self) -> int:
        return self.total_rows - len(self.to_delete)

    @property
    def needs_changes(self) -> bool:
        return bool(self.legacy_rows)


def load_rows(conn: sqlite3.Connection) -> List[Tuple[int, str, str, str]]:
    return conn.execute(
        "SELECT id, raw_timestamp, origin, destination FROM bronze_measurements ORDER BY id"
    ).fetchall()


def build_plan(rows: List[Tuple[int, str, str, str]]) -> Plan:
    """Decide qué hacer con cada fila. Función pura (sin acceso a la base)."""
    plan = Plan(total_rows=len(rows))
    iso_keys = {(ts, o, d) for _id, ts, o, d in rows if not is_legacy(ts)}
    seen_legacy = set()

    for _id, ts, o, d in rows:          # ya vienen ordenadas por id
        if not is_legacy(ts):
            continue
        plan.legacy_rows += 1
        key = (normalize(ts), o, d)
        if key in iso_keys:
            plan.delete_twin.append(_id)
        elif key in seen_legacy:
            plan.delete_dup.append(_id)
        else:
            seen_legacy.add(key)
            plan.rename.append((_id, key[0]))
    return plan


def describe(plan: Plan, db_path: Path, rows) -> str:
    por_mes = {}
    for _id, ts, _o, _d in rows:
        if is_legacy(ts):
            por_mes[ts[:7]] = por_mes.get(ts[:7], 0) + 1
    lineas = [
        f"Base: {db_path}",
        f"Filas en bronze_measurements:            {plan.total_rows:>8,}",
        f"  con separador antiguo (' '):           {plan.legacy_rows:>8,}   por mes: {por_mes or '-'}",
        f"    -> a BORRAR (su gemela ISO ya existe): {len(plan.delete_twin):>6,}",
        f"    -> a BORRAR (duplicada entre antiguas): {len(plan.delete_dup):>5,}",
        f"    -> a RENOMBRAR al formato ISO:        {len(plan.rename):>7,}",
        f"Filas en bronze_measurements tras aplicar: {plan.rows_after:>6,}",
    ]
    if plan.to_delete:
        por_id = {i: ts for i, ts, _o, _d in rows}
        primero = plan.to_delete[0]
        lineas.append(f"Ejemplo de fila a borrar: id={primero}  raw_timestamp={por_id[primero]!r}")
    if plan.rename:
        i, nuevo = plan.rename[0]
        lineas.append(f"Ejemplo de renombrado:    id={i}  -> {nuevo!r}")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Aplicar
# ---------------------------------------------------------------------------

def make_backup(db_path: Path) -> Path:
    """Copia consistente (API de backup de SQLite, correcta aunque la base esté
    en modo WAL) junto a la base, y la verifica. Devuelve la ruta."""
    destino = db_path.with_name(f"{db_path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(destino)
    try:
        src.backup(dst)
        n_src = src.execute("SELECT COUNT(*) FROM bronze_measurements").fetchone()[0]
        n_dst = dst.execute("SELECT COUNT(*) FROM bronze_measurements").fetchone()[0]
        check = dst.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        src.close()
        dst.close()
    if n_src != n_dst or check != "ok":
        destino.unlink(missing_ok=True)
        raise RuntimeError(f"El respaldo no pasó la verificación (filas {n_src} vs {n_dst}, quick_check={check}).")
    return destino


def verify(conn: sqlite3.Connection, expected_rows: int) -> None:
    """Comprobaciones antes de confirmar. Lanza RuntimeError si algo falla."""
    legacy = sum(1 for _i, ts, _o, _d in load_rows(conn) if is_legacy(ts))
    if legacy:
        raise RuntimeError(f"Quedan {legacy} filas con separador antiguo.")
    total = conn.execute("SELECT COUNT(*) FROM bronze_measurements").fetchone()[0]
    if total != expected_rows:
        raise RuntimeError(f"Se esperaban {expected_rows} filas y hay {total}.")
    dups = conn.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM bronze_measurements "
        "GROUP BY raw_timestamp, origin, destination HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    if dups:
        raise RuntimeError(f"Quedan {dups} grupos duplicados en Bronze.")
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(f"integrity_check: {integrity}")


def apply_changes(db_path: Path, backup: bool = True, lock_timeout: float = 3.0) -> Tuple[Plan, "Path | None"]:
    """Aplica la normalización. Devuelve (plan aplicado, ruta del respaldo).
    `lock_timeout`: segundos que espera el bloqueo exclusivo antes de abortar."""
    respaldo = make_backup(db_path) if backup else None

    conn = sqlite3.connect(db_path, timeout=lock_timeout, isolation_level=None)   # transacciones manuales
    try:
        try:
            conn.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as e:
            raise RuntimeError(
                f"La base está en uso por otro proceso ({e}). Apaga el collector "
                "(`docker compose down`) y vuelve a intentarlo. No se cambió nada."
            ) from e
        try:
            # El plan se calcula DENTRO del bloqueo: refleja el estado real de ahora.
            plan = build_plan(load_rows(conn))
            if plan.needs_changes:
                conn.executemany("DELETE FROM bronze_measurements WHERE id = ?", [(i,) for i in plan.to_delete])
                conn.executemany("UPDATE bronze_measurements SET raw_timestamp = ? WHERE id = ?",
                                 [(nuevo, i) for i, nuevo in plan.rename])
            verify(conn, plan.rows_after)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    return plan, respaldo


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB), help=f"ruta de la base (default: {DEFAULT_DB})")
    ap.add_argument("--apply", action="store_true", help="aplica los cambios (por defecto es solo un ensayo)")
    args = ap.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"No existe {db_path}", file=sys.stderr)
        return 2

    # Ensayo: solo lectura y sin crear archivos auxiliares (immutable=1).
    ro = sqlite3.connect(f"file:{db_path.as_posix()}?immutable=1", uri=True)
    try:
        existe = ro.execute("SELECT 1 FROM sqlite_master WHERE name='bronze_measurements'").fetchone()
        if not existe:
            print("La base no tiene la tabla bronze_measurements: nada que normalizar.")
            return 0
        rows = load_rows(ro)
    finally:
        ro.close()

    plan = build_plan(rows)
    print(describe(plan, db_path, rows))

    if not plan.needs_changes:
        print("\nNada que hacer: no hay timestamps con separador antiguo.")
        return 0
    if not args.apply:
        print("\nENSAYO: no se modificó nada. Con el collector apagado, para aplicar:")
        print(f"    python tools/normalize_bronze_timestamps.py --db \"{db_path}\" --apply")
        return 0

    print("\nAplicando (respaldo + bloqueo exclusivo + verificación)...")
    try:
        aplicado, respaldo = apply_changes(db_path)
    except Exception as e:
        print(f"\nERROR: {e}\nNo se aplicó ningún cambio (rollback).", file=sys.stderr)
        return 1
    print(f"Listo: {len(aplicado.to_delete):,} filas borradas, {len(aplicado.rename):,} renombradas; "
          f"Bronze queda con {aplicado.rows_after:,} filas.")
    print(f"Respaldo previo: {respaldo}")
    print("Cuando compruebes que todo está bien, puedes borrar el respaldo a mano.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
