"""
Descarga de Overpass (OpenStreetMap) el ESTADO HISTÓRICO de los locales del área, para la fase 4 de
docs/DISENO_ML_RECOMENDACION.md (§3.M, riesgo de cierre exploratorio).

Qué hace y qué NO hace:
  - Pide las siete categorías de `CATEGORY_TAGS` en tres instantes: 1-ene-2022, 1-ene-2024 y hoy; y, solo para hoy, los
    elementos con marca de ciclo de vida (`disused:*`, `was:*`, `abandoned:*`, `demolished:*`, `razed:*`), que son los
    cierres «fuertes».
  - Guarda JSON en `--out` (por defecto `data/osm_history/`, ignorado por git) y un `manifest.json` con la fecha de
    descarga, el espejo usado, la hora base del servidor (solo informativa) y el sha256 de cada archivo. NO toca la base.
  - COMPRUEBA que cada espejo respeta cada fecha `[date:]` que se le pide, con un CANARIO por espejo y por fecha: una
    consulta pequeña de una zona muy editada con `out meta` (el `timestamp` de cada elemento), comprobada por las dos caras:
    ningún elemento puede tener una versión posterior a la fecha (un espejo que ignora la fecha devuelve el mapa actual) y
    debe haber alguna de los 2 años anteriores (un espejo con una copia ANTIGUA de la base daría datos viejos como si fueran
    de 2024 u hoy). El espejo que falla se rechaza y se prueba el siguiente. (No se puede usar `osm3s.timestamp_osm_base`:
    medido en overpass-api.de, trae la hora ACTUAL del servidor aunque los datos sean de 2022, así que rechazaría
    respuestas históricas válidas.)
  - Rechaza también una respuesta con HTTP 200 pero un `remark` de error, sin `elements`, o un cuerpo que no sea un JSON
    completo (un corte de red deja el JSON a medias y falla al leerlo). Una respuesta parcial pero JSON válido y sin `remark`
    no es un modo de fallo conocido de Overpass, y no se puede distinguir de una legítima con certeza: por eso el análisis
    comprobará la coherencia entre instantes antes de usar los datos.
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
from datetime import datetime, timedelta, timezone
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


# Canario para saber si un espejo respeta `[date:]`. Zona del centro de Sliema/Gzira, editada sin parar: se pide UNA VEZ POR
# FECHA que se vaya a pedir y se comprueba por las dos caras (medido en overpass-api.de: con el mapa actual, 243 de 283
# elementos de esta zona tienen una versión posterior a 2022).
CANARIO_BBOX = (35.895, 14.480, 35.915, 14.510)
CANARIO_MIN_ELEMENTOS = 20
# Debe haber alguna versión de los 2 años anteriores a la fecha; si no, el espejo va atrasado.
CANARIO_VENTANA_DIAS = 730
FORMATO_FECHA = "%Y-%m-%dT%H:%M:%SZ"


def consulta_canario(fecha: str) -> str:
    """Consulta pequeña con `out meta` (trae `timestamp` de cada elemento) en la fecha que se va a pedir."""
    b = ",".join(f"{v:.6f}" for v in CANARIO_BBOX)
    selector = '["amenity"~"^(restaurant|cafe|bar|pub|fast_food)$"]'
    return (
        f'[out:json][timeout:{TIMEOUT_SERVIDOR_S}][date:"{fecha}"];\n'
        f"(\n  node{selector}({b});\n  way{selector}({b});\n);\nout center meta;"
    )


def canario_respeta_la_fecha(respuesta, fecha: str) -> Optional[str]:
    """None si la respuesta al canario es del estado de `fecha`; si no, el motivo DEFINITIVO. Se comprueba por las dos caras:

    - COTA SUPERIOR: ningún elemento puede tener una versión (`timestamp`) posterior a `fecha`. Un espejo que ignora `[date:]`
      devuelve el mapa actual, con muchas versiones recientes.
    - COTA INFERIOR: debe haber alguna versión de los `CANARIO_VENTANA_DIAS` días anteriores. Un espejo con una copia
      ANTIGUA de la base (que ignora la fecha o no llega a ella) devolvería versiones viejas y pasaría la cota superior
      para una fecha reciente (2024 u hoy).

    Las fechas ISO `AAAA-MM-DDThh:mm:ssZ` se comparan como texto. Distingue dos clases de problema: los DEFINITIVOS, que
    PRUEBAN que el espejo no sirve para esa fecha (ignora la fecha, va atrasado), se devuelven como motivo y el espejo queda
    descartado; todo lo demás es PASAJERO (HTTP 200 con `remark` de saturación, respuesta recortada o con menos elementos de
    los esperados, elementos sin `timestamp` por una respuesta defectuosa o por no admitir `meta`) y se lanza como
    `ValueError`, que no se recuerda: no se sabe si el espejo se recuperará en la ronda siguiente, y descartarlo de por vida
    por algo que no prueba nada sobre la fecha podría dejarnos sin el único espejo con historia. Un espejo que no admite
    `meta` simplemente no pasa nunca el canario y falla, a la vista, tras agotar las rondas."""
    motivo = respuesta_valida(respuesta)
    if motivo:
        raise ValueError(motivo)
    elementos = respuesta["elements"]
    if len(elementos) < CANARIO_MIN_ELEMENTOS:
        raise ValueError(
            f"el canario devolvió solo {len(elementos)} elementos (se esperaban al menos {CANARIO_MIN_ELEMENTOS})"
        )
    sin_marca = sum(1 for e in elementos if not isinstance(e.get("timestamp"), str))
    if sin_marca:  # no admite `meta`, o respuesta defectuosa: no se sabe cuál, así que NO se descarta de por vida
        raise ValueError(f"{sin_marca} de {len(elementos)} elementos del canario no traen `timestamp`")
    marcas = [e["timestamp"] for e in elementos]
    posteriores = [t for t in marcas if t > fecha]
    if posteriores:
        return (
            f"el espejo ignoró la fecha: {len(posteriores)} de {len(elementos)} elementos tienen una versión posterior a "
            f"{fecha} (la más reciente, {max(posteriores)})"
        )
    desde = (datetime.strptime(fecha, FORMATO_FECHA) - timedelta(days=CANARIO_VENTANA_DIAS)).strftime(FORMATO_FECHA)
    if max(marcas) < desde:
        return (
            f"el espejo va atrasado: ninguna versión de los {CANARIO_VENTANA_DIAS} días anteriores a {fecha} "
            f"(la más reciente, {max(marcas)})"
        )
    return None


def verificar_espejo(cliente, endpoint: str, fecha: str) -> Optional[str]:
    """Pide el canario de `fecha` a un espejo y devuelve None si respeta la fecha o el motivo DEFINITIVO si no. Cualquier
    problema pasajero (red, HTTP, JSON, `remark`, respuesta recortada) sube como excepción y el espejo no queda marcado: se
    podrá volver a probar en la ronda siguiente."""
    r = cliente.session.post(
        endpoint, data={"data": consulta_canario(fecha)}, timeout=(TIMEOUT_CONEXION_S, TIMEOUT_HTTP_S)
    )
    r.raise_for_status()
    return canario_respeta_la_fecha(r.json(), fecha)


def respuesta_valida(respuesta) -> Optional[str]:
    """None si la respuesta de Overpass es una respuesta completa; si no, el motivo para descartarla.

    Cuando Overpass se queda sin tiempo o sin memoria contesta con HTTP 200 y un JSON con `remark` («runtime error: Query
    timed out...»), con `elements` vacío o PARCIAL y la fecha base ya escrita. Darlo por bueno guardaría un trozo vacío o
    truncado, que en una comparación 2022-hoy parecería una ola de cierres. Por eso cualquier `remark`, un `elements`
    ausente o que no sea una lista se trata como fallo (y se ve, en vez de pasar en silencio)."""
    if not isinstance(respuesta, dict):
        return "la respuesta no es un objeto JSON"
    if respuesta.get("remark"):
        return f"Overpass avisa de un error en la consulta: {str(respuesta['remark'])[:140]}"
    if not isinstance(respuesta.get("elements"), list):
        return "la respuesta no trae la lista `elements`"
    return None


def pedir(
    cliente,
    consulta: str,
    fecha_pedida: Optional[str],
    rondas: Optional[int] = None,
    espera_s: Optional[float] = None,
    dormir=None,
    verificados: Optional[Dict[Tuple[str, str], Optional[str]]] = None,
) -> Tuple[dict, str]:
    """Envía la consulta probando cada espejo en orden; devuelve (JSON, espejo). Para un instante pasado, antes de usar un
    espejo se le pasa el canario de esa fecha (una sola vez: el resultado queda en `verificados`) y se descarta el que ignore la fecha.
    Si TODOS fallan se espera `espera_s` y se vuelve a empezar, hasta `rondas` rondas (los espejos públicos se saturan y se
    recuperan). Lanza RuntimeError con el motivo de CADA espejo en la última ronda."""
    rondas = RONDAS if rondas is None else rondas
    espera_s = ESPERA_RONDAS_S if espera_s is None else espera_s
    dormir = time.sleep if dormir is None else dormir
    verificados = {} if verificados is None else verificados
    errores: Dict[str, str] = {}
    for ronda in range(rondas):
        errores = {}
        for endpoint in cliente.endpoints:
            try:
                if fecha_pedida is not None:
                    clave = (endpoint, fecha_pedida)  # un canario por espejo y por fecha
                    if clave not in verificados:  # un problema pasajero sube como excepción y no se marca
                        verificados[clave] = verificar_espejo(cliente, endpoint, fecha_pedida)
                        if PAUSA_S:  # el canario es una petición más: pausa antes de la consulta pesada
                            dormir(PAUSA_S)
                    if verificados[clave]:
                        raise ValueError(verificados[clave])
                r = cliente.session.post(
                    endpoint, data={"data": consulta}, timeout=(TIMEOUT_CONEXION_S, TIMEOUT_HTTP_S)
                )
                r.raise_for_status()
                datos = r.json()
                motivo = respuesta_valida(datos)
                if motivo:
                    raise ValueError(motivo)
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
    ruta_manifiesto = out_dir / "manifest.json"
    # Se FUSIONA con el manifiesto anterior: relanzar un subconjunto (p. ej. `--instantes hoy` para reintentar) no debe
    # borrar el hash, la fecha base y el espejo de lo ya descargado, cuyos archivos siguen en disco.
    previos: Dict[str, dict] = {}
    if ruta_manifiesto.exists():
        try:
            previos = json.loads(ruta_manifiesto.read_text(encoding="utf-8")).get("archivos", {})
        except (OSError, ValueError, AttributeError):
            previos = {}
    manifiesto = {
        "formato": 1,
        "descargado_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "area": {"sur": grid.SOUTH, "norte": grid.NORTH, "oeste": grid.WEST, "este": grid.EAST},
        "archivos": {a: d for a, d in previos.items() if (out_dir / a).exists()},
        "fallidos": [],
    }
    # (espejo, fecha) -> None si el espejo respeta esa fecha, o el motivo definitivo si no (se verifica una vez por par)
    verificados: Dict[Tuple[str, str], Optional[str]] = {}
    for k, (nombre, franja, fecha, consulta) in enumerate(trabajo):
        t0 = time.perf_counter()
        archivo = f"{nombre}_{franja}.json"
        try:
            datos, endpoint = pedir(cliente, consulta, fecha, rondas, espera_s, verificados=verificados)
            elementos = datos.get("elements", [])
            ruta = out_dir / archivo
            ruta.write_text(
                json.dumps(
                    {
                        "instante": nombre,
                        "fecha_pedida": fecha,
                        "franja": franja,
                        "osm_base_servidor": (datos.get("osm3s") or {}).get("timestamp_osm_base"),  # solo informativa
                        "espejo": endpoint,
                        "elements": elementos,
                    }
                ),
                encoding="utf-8",
            )
            manifiesto["archivos"][archivo] = {
                "elementos": len(elementos),
                "fecha_pedida": fecha,
                "osm_base_servidor": (datos.get("osm3s") or {}).get("timestamp_osm_base"),  # solo informativa
                "espejo": endpoint,
                "descargado_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sha256": sha256_de(ruta),
            }
            log(f"   {nombre} [{franja}]: {len(elementos):6} elementos ({time.perf_counter() - t0:.0f} s)")
        except RuntimeError as e:
            conservado = archivo in manifiesto["archivos"]  # de una ejecución anterior, sigue siendo válido
            manifiesto["fallidos"].append(
                {
                    "archivo": archivo,
                    "error": str(e),
                    "se_conserva_el_de_una_ejecucion_anterior": conservado,
                }
            )
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
        print(
            f"   {archivo:24} {d['elementos']:7} elementos | hora del servidor {d.get('osm_base_servidor', d.get('osm_base'))} | {d['espejo']}"
        )
    for f in manifiesto["fallidos"]:
        print(f"   FALLÓ {f['archivo']}: {f['error']}")
    return 0 if not manifiesto["fallidos"] else 1


if __name__ == "__main__":
    sys.exit(main())
