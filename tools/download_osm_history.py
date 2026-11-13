"""
Descarga de Overpass (OpenStreetMap) el ESTADO HISTÓRICO de los locales del área, para la fase 4 de
docs/DISENO_ML_RECOMENDACION.md (§3.M, riesgo de cierre exploratorio).

Qué hace y qué NO hace:
  - Pide las siete categorías de `CATEGORY_TAGS` en tres instantes: 1-ene-2022, 1-ene-2024 y hoy; y, solo para hoy, los
    elementos con marca de ciclo de vida (`disused:*`, `was:*`, `abandoned:*`, `demolished:*`, `razed:*`), que son los
    cierres «fuertes».
  - Guarda JSON en `--out` (por defecto `data/osm_history/`, ignorado por git) y un `manifest.json` con la fecha de
    descarga, el espejo usado, la fecha base que Overpass dice haber usado y el sha256 de cada archivo. NO toca la base.
  - COMPRUEBA que Overpass respondió con la fecha pedida (`osm3s.timestamp_osm_base`): hay espejos que ignoran `[date:]`
    en silencio y devuelven el mapa actual; esa respuesta se rechaza y se prueba el siguiente espejo.
  - Pausa entre peticiones, tiempo máximo de servidor y el área partida en franjas, como `download_osm_context.py`.
  - `--dry-run` muestra las consultas sin hacer NINGUNA llamada de red.

Uso (desde la raíz del proyecto):
    python tools/download_osm_history.py --dry-run
    python tools/download_osm_history.py
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import grid  # noqa: E402
from src.poi_client import CATEGORY_TAGS, OverpassClient, _parse_spec  # noqa: E402

PAUSA_S = 12
TIMEOUT_SERVIDOR_S = 150
TIMEOUT_HTTP_S = 190
TIMEOUT_CONEXION_S = 15  # un espejo que no conecta en 15 s se salta; no hay que esperar 190 s para saberlo
RONDAS = 3  # veces que se recorren todos los espejos antes de rendirse (los públicos se saturan y se recuperan)
ESPERA_RONDAS_S = 90
FRANJAS = 2  # el área se parte en franjas de latitud para no cargar el servicio público

# Instante -> fecha ISO que se le pide a Overpass (None = el estado actual).
INSTANTES: Dict[str, Optional[str]] = {
    "2022-01-01": "2022-01-01T00:00:00Z",
    "2024-01-01": "2024-01-01T00:00:00Z",
    "hoy": None,
}
CLAVES_CICLO_DE_VIDA = ("amenity", "shop", "office", "leisure", "tourism")
PREFIJOS_CICLO_DE_VIDA = ("disused", "was", "abandoned", "demolished", "razed")
TEMA_CICLO_DE_VIDA = "ciclo_de_vida"
SALIDA_POR_DEFECTO = ROOT / "data" / "osm_history"


def clausulas_categorias() -> List[str]:
    """Una cláusula `node` y una `way` por cada etiqueta de CATEGORY_TAGS, con {bbox} por rellenar (mismas que usa
    `OverpassClient._build_query`: un test comprueba que no se desincronizan)."""
    clausulas = []
    for specs in CATEGORY_TAGS.values():
        for spec in specs:
            clave, valores = _parse_spec(spec)
            if valores is None:
                selector = f'["{clave}"]'
            elif len(valores) == 1:
                selector = f'["{clave}"="{valores[0]}"]'
            else:
                selector = f'["{clave}"~"^({"|".join(valores)})$"]'
            clausulas.append(f"node{selector}({{bbox}});")
            clausulas.append(f"way{selector}({{bbox}});")
    return clausulas


def clausulas_ciclo_de_vida() -> List[str]:
    """Elementos cuya etiqueta de categoría lleva un prefijo de cierre (`disused:amenity`, `was:shop`...)."""
    return [
        f'nwr["{prefijo}:{clave}"]({{bbox}});' for clave in CLAVES_CICLO_DE_VIDA for prefijo in PREFIJOS_CICLO_DE_VIDA
    ]


def bbox_franjas(n: int) -> List[Tuple[float, float, float, float]]:
    """`n` franjas de latitud contiguas (sur, oeste, norte, este) que cubren TODA la rejilla sin huecos ni solapes."""
    if n < 1:
        raise ValueError("n debe ser >= 1")
    alto = (grid.NORTH - grid.SOUTH) / n
    return [
        (grid.SOUTH + i * alto, grid.WEST, grid.SOUTH + (i + 1) * alto if i < n - 1 else grid.NORTH, grid.EAST)
        for i in range(n)
    ]


def construir_consulta(clausulas: List[str], bbox: Tuple[float, float, float, float], fecha: Optional[str]) -> str:
    """Overpass QL: salida JSON con centro y etiquetas; con `[date:"..."]` si se pide un instante pasado."""
    texto_bbox = ",".join(f"{v:.6f}" for v in bbox)
    cuerpo = "\n  ".join(c.format(bbox=texto_bbox) for c in clausulas)
    cabecera = f"[out:json][timeout:{TIMEOUT_SERVIDOR_S}]" + (f'[date:"{fecha}"]' if fecha else "")
    return f"{cabecera};\n(\n  {cuerpo}\n);\nout center tags;"


def plan(instantes: Optional[List[str]] = None) -> List[Tuple[str, int, Optional[str], str]]:
    """(instante o tema, franja, fecha pedida, consulta) de todo lo que habría que pedir."""
    instantes = instantes or list(INSTANTES)
    trabajo = []
    for nombre in instantes:
        fecha = INSTANTES[nombre]
        for i, bbox in enumerate(bbox_franjas(FRANJAS)):
            trabajo.append((nombre, i, fecha, construir_consulta(clausulas_categorias(), bbox, fecha)))
        if nombre == "hoy":  # los cierres «fuertes» solo se miran en el estado actual
            trabajo.append(
                (TEMA_CICLO_DE_VIDA, 0, None, construir_consulta(clausulas_ciclo_de_vida(), bbox_franjas(1)[0], None))
            )
    return trabajo


def fecha_aceptada(respuesta: dict, fecha_pedida: Optional[str]) -> bool:
    """Para un instante pasado, Overpass debe declarar una fecha base (`osm3s.timestamp_osm_base`) que NO sea posterior a la
    pedida. Si el espejo ignoró `[date:]` y devolvió el mapa actual, esa fecha sería la de hoy (posterior): se rechaza, y
    también si falta. Para «hoy» no hay nada que comprobar. Las fechas ISO `AAAA-MM-DDThh:mm:ssZ` se comparan como texto.
    """
    if fecha_pedida is None:
        return True
    base = (respuesta.get("osm3s") or {}).get("timestamp_osm_base")
    return isinstance(base, str) and base <= fecha_pedida


def pedir(
    cliente,
    consulta: str,
    fecha_pedida: Optional[str],
    rondas: Optional[int] = None,
    espera_s: Optional[float] = None,
    dormir=None,
) -> Tuple[dict, str]:
    """Envía la consulta probando cada espejo en orden; devuelve (JSON, espejo). Un espejo que responde pero con otra fecha
    base se descarta como si fallara. Si TODOS fallan se espera `espera_s` y se vuelve a empezar, hasta `rondas` rondas
    (los espejos públicos se saturan y se recuperan). Lanza RuntimeError con el motivo de CADA espejo en la última ronda.
    """
    rondas = RONDAS if rondas is None else rondas
    espera_s = ESPERA_RONDAS_S if espera_s is None else espera_s
    dormir = time.sleep if dormir is None else dormir
    errores: Dict[str, str] = {}
    for ronda in range(rondas):
        errores = {}
        for endpoint in cliente.endpoints:
            try:
                r = cliente.session.post(
                    endpoint, data={"data": consulta}, timeout=(TIMEOUT_CONEXION_S, TIMEOUT_HTTP_S)
                )
                r.raise_for_status()
                datos = r.json()
                if not fecha_aceptada(datos, fecha_pedida):
                    base = (datos.get("osm3s") or {}).get("timestamp_osm_base")
                    raise ValueError(f"el espejo ignoró la fecha: pedí {fecha_pedida} y usó {base}")
                return datos, endpoint
            except Exception as e:  # red, HTTP, JSON inválido o fecha ignorada: se prueba el siguiente espejo
                errores[endpoint] = f"{type(e).__name__}: {str(e)[:160]}"
        if ronda < rondas - 1:
            dormir(espera_s)
    detalle = "; ".join(f"{ep} -> {err}" for ep, err in errores.items())
    raise RuntimeError(f"Todos los espejos de Overpass fallaron en {rondas} rondas. {detalle}")


def sha256_de(ruta: Path) -> str:
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def descargar(
    cliente,
    out_dir: Path,
    instantes: Optional[List[str]] = None,
    pausa_s: float = PAUSA_S,
    log=print,
    rondas: Optional[int] = None,
    espera_s: Optional[float] = None,
) -> dict:
    """Descarga cada trozo a `out_dir/<instante>_<franja>.json` y escribe `manifest.json`. Devuelve el manifiesto.
    NO escribe nada fuera de `out_dir`."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    trabajo = plan(instantes)
    manifiesto = {
        "formato": 1,
        "descargado_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "area": {"sur": grid.SOUTH, "norte": grid.NORTH, "oeste": grid.WEST, "este": grid.EAST},
        "archivos": {},
        "fallidos": [],
    }
    for k, (nombre, franja, fecha, consulta) in enumerate(trabajo):
        t0 = time.perf_counter()
        archivo = f"{nombre}_{franja}.json"
        try:
            datos, endpoint = pedir(cliente, consulta, fecha, rondas, espera_s)
            elementos = datos.get("elements", [])
            ruta = out_dir / archivo
            ruta.write_text(
                json.dumps(
                    {
                        "instante": nombre,
                        "fecha_pedida": fecha,
                        "franja": franja,
                        "osm_base": (datos.get("osm3s") or {}).get("timestamp_osm_base"),
                        "espejo": endpoint,
                        "elements": elementos,
                    }
                ),
                encoding="utf-8",
            )
            manifiesto["archivos"][archivo] = {
                "elementos": len(elementos),
                "fecha_pedida": fecha,
                "osm_base": (datos.get("osm3s") or {}).get("timestamp_osm_base"),
                "espejo": endpoint,
                "sha256": sha256_de(ruta),
            }
            log(f"   {nombre} [{franja}]: {len(elementos):6} elementos ({time.perf_counter() - t0:.0f} s)")
        except RuntimeError as e:
            manifiesto["fallidos"].append({"archivo": archivo, "error": str(e)})
            log(f"   {nombre} [{franja}]: FALLÓ ({e})")
        if k < len(trabajo) - 1:
            time.sleep(pausa_s)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifiesto


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(SALIDA_POR_DEFECTO), help="directorio donde guardar los JSON (NO la base)")
    ap.add_argument("--instantes", nargs="+", choices=list(INSTANTES), default=list(INSTANTES))
    ap.add_argument("--dry-run", action="store_true", help="muestra las consultas sin hacer ninguna llamada de red")
    ap.add_argument("--pausa", type=float, default=PAUSA_S, help="segundos de pausa entre peticiones")
    ap.add_argument("--rondas", type=int, default=RONDAS, help="rondas por todos los espejos antes de rendirse")
    ap.add_argument("--espera", type=float, default=ESPERA_RONDAS_S, help="segundos entre rondas")
    args = ap.parse_args(argv)

    trabajo = plan(args.instantes)
    print(
        f"Área: lat {grid.SOUTH}-{grid.NORTH}, lon {grid.WEST}-{grid.EAST} | consultas a pedir: {len(trabajo)} | salida: {args.out}"
    )
    if args.dry_run:
        for nombre, franja, fecha, consulta in trabajo:
            print(f"\n--- {nombre} [{franja}] (fecha pedida: {fecha or 'hoy'}) ---\n{consulta}")
        print("\n(dry-run: no se hizo ninguna llamada de red)")
        return 0

    manifiesto = descargar(
        OverpassClient(timeout=TIMEOUT_HTTP_S, max_retries=1),
        Path(args.out),
        args.instantes,
        args.pausa,
        rondas=args.rondas,
        espera_s=args.espera,
    )
    print("\nResumen:")
    for archivo, d in manifiesto["archivos"].items():
        print(f"   {archivo:24} {d['elementos']:7} elementos | base {d['osm_base']} | {d['espejo']}")
    for f in manifiesto["fallidos"]:
        print(f"   FALLÓ {f['archivo']}: {f['error']}")
    return 0 if not manifiesto["fallidos"] else 1


if __name__ == "__main__":
    sys.exit(main())
