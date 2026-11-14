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
    consulta pequeña de una zona muy editada con `out center meta` (el `timestamp` de cada elemento), comprobada por las dos caras:
    ningún elemento puede tener una versión posterior a la fecha (un espejo que ignora la fecha devuelve el mapa actual) y
    debe haber alguna de los 2 años anteriores (un espejo con una copia ANTIGUA de la base daría datos viejos como si fueran
    de 2024 u hoy). El espejo que falla se rechaza y se prueba el siguiente. (No se puede usar `osm3s.timestamp_osm_base`:
    medido en overpass-api.de, trae la hora ACTUAL del servidor aunque los datos sean de 2022, así que rechazaría
    respuestas históricas válidas.)
  - Solo se GUARDAN type, id, lat, lon, center y tags de cada elemento (lista blanca): aunque un espejo devolviera `user`,
    `uid`, `changeset`, `version` o `timestamp` (datos de colaboradores de OSM), no se escriben a disco ni al manifiesto.
  - Rechaza también una respuesta con HTTP 200 pero un `remark` de error, sin `elements`, o un cuerpo que no sea un JSON
    completo (un corte de red deja el JSON a medias y falla al leerlo). Una respuesta parcial pero JSON válido y sin `remark`
    no es un modo de fallo conocido de Overpass y no se puede distinguir de una legítima mirando solo la respuesta; por eso
    se detecta con `--verificar`: comprueba que cada archivo es el descrito por el manifiesto (sha256, instante, franja, fecha y
    número de elementos), repite su consulta como un recuento (`out count;`, que calcula el propio servidor) y compara con lo
    guardado (exacto para el pasado; 1 % para el estado actual, que cambia cada minuto), y anota el resultado en el manifiesto. El análisis debe usar solo archivos con `verificacion.estado == "completo"`.
    El manifiesto vive junto a los datos y por sí solo no detecta que se alteren ambos a la vez: por eso `--huella` escribe
    `docs/HUELLA_OSM_HISTORY.json` (solo hashes, recuentos y fechas, sin datos) para VERSIONARLA en git como ancla externa, y
    `--verificar` la exige si existe.
  - Los trozos ANCLADOS en la huella no se sobrescriben al volver a descargar (esos datos no están en git y se perderían):
    se omiten y se avisa, salvo con `--sobrescribir`. Para volver a anclar tras sobrescribir: `--sobrescribir`, luego
    `--verificar --sin-huella`, luego `--huella`, y versionar el cambio de la huella (queda visible en git). Los archivos se
    escriben de forma atómica y el manifiesto se guarda tras cada trozo, así que una interrupción no deja un «completo» caducado.
  - EL ANÁLISIS debe empezar llamando a `exigir_datos_verificados(out_dir, huella)`: solo devuelve las rutas si los 7 trozos
    son utilizables (completos, el archivo en disco es el verificado y coincide con la huella); si no, lanza `ValueError`.
  - Pausa entre peticiones, tiempo máximo de servidor y el área partida en franjas, como `download_osm_context.py`.
  - `--dry-run` muestra las consultas sin hacer NINGUNA llamada de red.

Uso (desde la raíz del proyecto):
    python tools/download_osm_history.py --dry-run
    python tools/download_osm_history.py
"""

import argparse
import hashlib
import json
import os
import re
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
# Ancla externa: solo hashes, recuentos y fechas (NO datos), versionada en git. Ver `escribir_huella`.
HUELLA_POR_DEFECTO = ROOT / "docs" / "HUELLA_OSM_HISTORY.json"
CAMPOS_DE_LA_HUELLA = ("sha256", "elementos", "fecha_pedida", "espejo", "descargado_utc")


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
_PATRON_MARCA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
# Verificación de integridad: para un instante pasado el recuento del servidor debe coincidir EXACTAMENTE con lo guardado (el
# pasado no cambia); para el estado actual («hoy», ciclo de vida) el mapa cambia cada minuto y se admite hasta un 1 %.
TOLERANCIA_ESTADO_ACTUAL = 0.01
# Campos de cada elemento que SE GUARDAN. `out meta` (solo el canario) devuelve además `user`, `uid`, `changeset`,
# `timestamp` y `version`, que son datos de colaboradores de OSM y no hacen falta: aunque un espejo los incluyera en una
# respuesta normal, no se escriben a disco.
CLAVES_ELEMENTO = ("type", "id", "lat", "lon", "center", "tags")


def consulta_canario(fecha: str) -> str:
    """Consulta pequeña con `out meta` (trae `timestamp` de cada elemento) en la fecha que se va a pedir."""
    b = ",".join(f"{v:.6f}" for v in CANARIO_BBOX)
    selector = '["amenity"~"^(restaurant|cafe|bar|pub|fast_food)$"]'
    return (
        f'[out:json][timeout:{TIMEOUT_SERVIDOR_S}][date:"{fecha}"];\n'
        f"(\n  node{selector}({b});\n  way{selector}({b});\n);\nout center meta;"
    )


def _marca_valida(marca) -> bool:
    """True si `marca` es una fecha ISO `AAAA-MM-DDThh:mm:ssZ` real (no solo con la forma: «2021-13-45T99:99:99Z» no vale)."""
    if not isinstance(marca, str) or not _PATRON_MARCA.match(marca):
        return False
    try:
        datetime.strptime(marca, FORMATO_FECHA)
    except ValueError:
        return False
    return True


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
    # Sin `timestamp`, o con uno que no es una fecha ISO `AAAA-MM-DDThh:mm:ssZ` válida (comparar como texto un valor malformado
    # daría un veredicto sin sentido): no admite `meta`, o respuesta defectuosa. No se sabe cuál de las dos, así que NO se
    # descarta de por vida.
    sin_marca = sum(1 for e in elementos if not _marca_valida(e.get("timestamp")))
    if sin_marca:
        raise ValueError(f"{sin_marca} de {len(elementos)} elementos del canario no traen un `timestamp` ISO válido")
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
    if not all(isinstance(e, dict) for e in respuesta["elements"]):
        return "`elements` contiene algo que no es un objeto"
    return None


def limpiar_elemento(elemento: dict) -> dict:
    """El elemento con solo los campos de `CLAVES_ELEMENTO` (lista blanca): sin `user`, `uid`, `changeset`..."""
    return {k: elemento[k] for k in CLAVES_ELEMENTO if k in elemento}


def pedir(
    cliente,
    consulta: str,
    fecha_pedida: Optional[str],
    rondas: Optional[int] = None,
    espera_s: Optional[float] = None,
    dormir=None,
    verificados: Optional[Dict[Tuple[str, str], Optional[str]]] = None,
    pausa_canario_s: Optional[float] = None,
) -> Tuple[dict, str]:
    """Envía la consulta probando cada espejo en orden; devuelve (JSON, espejo). Para un instante pasado, antes de usar un
    espejo se le pasa el canario de esa fecha (una sola vez: el resultado queda en `verificados`) y se descarta el que ignore la fecha.
    Si TODOS fallan se espera `espera_s` y se vuelve a empezar, hasta `rondas` rondas (los espejos públicos se saturan y se
    recuperan). Lanza RuntimeError con el motivo de CADA espejo en la última ronda."""
    rondas = RONDAS if rondas is None else rondas
    espera_s = ESPERA_RONDAS_S if espera_s is None else espera_s
    dormir = time.sleep if dormir is None else dormir
    verificados = {} if verificados is None else verificados
    pausa_canario_s = PAUSA_S if pausa_canario_s is None else pausa_canario_s
    errores: Dict[str, str] = {}
    for ronda in range(rondas):
        errores = {}
        for endpoint in cliente.endpoints:
            try:
                if fecha_pedida is not None:
                    clave = (endpoint, fecha_pedida)  # un canario por espejo y por fecha
                    if clave not in verificados:  # un problema pasajero sube como excepción y no se marca
                        verificados[clave] = verificar_espejo(cliente, endpoint, fecha_pedida)
                        if pausa_canario_s:  # el canario es una petición más: pausa antes de la consulta pesada
                            dormir(pausa_canario_s)
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


def _escribir_atomico(ruta: Path, texto: str) -> None:
    """Escribe el archivo entero o no lo escribe: primero a un temporal y luego `os.replace`. Una interrupción (Ctrl+C, disco
    lleno) no deja un JSON a medias con el nombre definitivo."""
    ruta = Path(ruta)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(texto, encoding="utf-8")
    os.replace(temporal, ruta)


def _guardar_manifiesto(out_dir: Path, manifiesto: dict) -> None:
    _escribir_atomico(
        Path(out_dir) / "manifest.json",
        json.dumps(manifiesto, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    )


def descargar(
    cliente,
    out_dir: Path,
    instantes: Optional[List[str]] = None,
    pausa_s: float = PAUSA_S,
    log=print,
    rondas: Optional[int] = None,
    espera_s: Optional[float] = None,
    huella: Optional[dict] = None,
    sobrescribir: bool = False,
) -> dict:
    """Descarga cada trozo a `out_dir/<instante>_<franja>.json` y escribe `manifest.json`. Devuelve el manifiesto.
    NO escribe nada fuera de `out_dir`.

    - Los archivos se escriben de forma ATÓMICA y el manifiesto se guarda tras CADA trozo; antes de reescribir un trozo se
      quita su entrada del manifiesto, de modo que una interrupción nunca deja un archivo nuevo junto a una entrada
      antigua que siga diciendo «completo».
    - Si se da la `huella` versionada, NO se sobrescribe un trozo ANCLADO en ella (esos datos no están en git y se perderían):
      se omite y se anota en `omitidos`, salvo con `sobrescribir=True` (`--sobrescribir`). Tras sobrescribir hay que volver a
      verificar (`--verificar --sin-huella`) y regenerar la huella (`--huella`), y el cambio de la huella queda visible en git.
    """
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
        "omitidos": [],
    }
    # (espejo, fecha) -> None si el espejo respeta esa fecha, o el motivo definitivo si no (se verifica una vez por par)
    verificados: Dict[Tuple[str, str], Optional[str]] = {}
    for k, (nombre, franja, fecha, consulta) in enumerate(trabajo):
        t0 = time.perf_counter()
        archivo = f"{nombre}_{franja}.json"
        ruta = out_dir / archivo
        if huella is not None and not sobrescribir and archivo in huella.get("archivos", {}) and ruta.exists():
            manifiesto["omitidos"].append(archivo)
            log(f"   {nombre} [{franja}]: ANCLADO en la huella, no se sobrescribe (usa --sobrescribir para forzarlo)")
            continue
        try:
            datos, endpoint = pedir(
                cliente, consulta, fecha, rondas, espera_s, verificados=verificados, pausa_canario_s=pausa_s
            )
            elementos = [limpiar_elemento(e) for e in datos["elements"]]  # solo los campos de la lista blanca
            # Se quita la entrada antigua ANTES de tocar el archivo: si algo se interrumpe, no queda un «completo» caducado.
            conservado = manifiesto["archivos"].pop(archivo, None)
            if conservado is not None:
                _guardar_manifiesto(out_dir, manifiesto)
            _escribir_atomico(
                ruta,
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
            )
            manifiesto["archivos"][archivo] = {
                "elementos": len(elementos),
                "fecha_pedida": fecha,
                "osm_base_servidor": (datos.get("osm3s") or {}).get("timestamp_osm_base"),  # solo informativa
                "espejo": endpoint,
                "descargado_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sha256": sha256_de(ruta),
            }
            _guardar_manifiesto(out_dir, manifiesto)  # tras CADA trozo, no solo al final
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
    _guardar_manifiesto(out_dir, manifiesto)
    return manifiesto


def consulta_de_recuento(consulta: str) -> str:
    """La misma consulta pero pidiendo solo CUÁNTOS elementos devuelve (`out count;`): el recuento lo calcula el propio servidor
    sobre los mismos datos, sin depender de que la respuesta de los datos llegara entera."""
    final = "out center tags;"
    cuerpo = consulta.rstrip()
    if not cuerpo.endswith(final):
        raise ValueError("la consulta no termina en `out center tags;`: no se sabe convertirla en un recuento")
    return cuerpo[: -len(final)] + "out count;"


def total_del_servidor(respuesta: dict) -> int:
    """El total que declara Overpass en una respuesta a `out count;` (un único elemento `count` con `tags.total`)."""
    elementos = respuesta["elements"]
    if len(elementos) != 1 or elementos[0].get("type") != "count":
        raise ValueError("la respuesta al recuento no trae un único elemento `count`")
    try:
        total = elementos[0]["tags"]["total"]
    except (KeyError, TypeError):
        raise ValueError("el elemento `count` no trae `tags.total`") from None
    # Overpass escribe el total como una cadena de dígitos ASCII (sin signo, espacios ni decimales). `int()` aceptaría
    # además «-5», «+5», « 5 » o dígitos de otros alfabetos, que no son un recuento válido.
    if not isinstance(total, str) or not re.fullmatch(r"[0-9]+", total):
        raise ValueError(f"el elemento `count` no trae un `tags.total` entero no negativo: {total!r}")
    return int(total)


def comprobar_identidad(
    ruta: Path, entrada: dict, nombre: str, franja: int, fecha: Optional[str], huella: Optional[dict] = None
) -> Optional[str]:
    """None si el archivo es EL QUE DESCRIBE el manifiesto; si no, el motivo. «Completo» solo tiene sentido para el archivo que
    se descargó: se comprueba el sha256 y que dentro diga el mismo instante, franja y fecha pedida y el mismo número de
    elementos (un JSON alterado a mano, de otra franja o de otra fecha, con la misma cantidad, no puede salir «completo»).

    El manifiesto vive junto a los datos, así que por sí solo no autentica nada: quien editara el archivo podría recalcular su
    hash en el manifiesto. Por eso, si se da la `huella` versionada en git (el ancla externa), la entrada del manifiesto
    debe coincidir con ella en sha256, elementos, fecha pedida, espejo y fecha de descarga.
    """
    if huella is not None:
        registrada = huella.get("archivos", {}).get(f"{nombre}_{franja}.json")
        if registrada is None:
            return "el archivo no figura en la huella versionada"
        for campo in CAMPOS_DE_LA_HUELLA:
            if entrada.get(campo) != registrada.get(campo):
                return f"el manifiesto no coincide con la huella versionada en `{campo}`"
    esperado = entrada.get("sha256")
    if not esperado:
        return "el manifiesto no trae el sha256 de este archivo"
    real = sha256_de(ruta)
    if real != esperado:
        return f"el sha256 del archivo ({real[:12]}…) no coincide con el del manifiesto ({esperado[:12]}…)"
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"))
        elementos = contenido["elements"]
    except (OSError, ValueError, KeyError, TypeError):
        return "el archivo no es un JSON legible con `elements`"
    if not isinstance(elementos, list):
        return "`elements` del archivo no es una lista"
    for campo, valor in (("instante", nombre), ("franja", franja), ("fecha_pedida", fecha)):
        if contenido.get(campo) != valor:
            return f"el archivo dice {campo}={contenido.get(campo)!r} y debería ser {valor!r}"
    if len(elementos) != entrada.get("elementos"):
        return f"el archivo tiene {len(elementos)} elementos y el manifiesto dice {entrada.get('elementos')}"
    return None


def verificar_descarga(
    cliente,
    out_dir: Path,
    instantes: Optional[List[str]] = None,
    pausa_s: float = PAUSA_S,
    log=print,
    rondas: Optional[int] = None,
    espera_s: Optional[float] = None,
    huella: Optional[dict] = None,
) -> dict:
    """Comprueba que cada archivo descargado está COMPLETO: repite su consulta como recuento y compara el total del servidor con
    los elementos guardados. Es la barrera contra una respuesta parcial pero JSON válido y sin `remark` (que de otro modo no se
    distinguiría de una legítima). Anota el resultado en `manifest.json` (`archivos[...]["verificacion"]`) y devuelve
    `{"correctos", "incorrectos", "sin_verificar", "sin_archivo", "alterados", "ok"}`. Antes de contar comprueba que el archivo
    es el descrito por el manifiesto (sha256, instante, franja, fecha y número de elementos) y, si se da `huella`, por la
    huella versionada en git (el ancla externa): si no, queda «MODIFICADO». Los instantes pasados deben coincidir
    exactamente; el estado actual admite `TOLERANCIA_ESTADO_ACTUAL`. NO toca los archivos de datos."""
    out_dir = Path(out_dir)
    ruta_manifiesto = out_dir / "manifest.json"
    if not ruta_manifiesto.exists():
        raise FileNotFoundError(f"No hay {ruta_manifiesto}: primero hay que descargar.")
    manifiesto = json.loads(ruta_manifiesto.read_text(encoding="utf-8"))
    verificados: Dict[Tuple[str, str], Optional[str]] = {}
    resumen: Dict[str, list] = {
        "correctos": [],
        "incorrectos": [],
        "sin_verificar": [],
        "sin_archivo": [],
        "alterados": [],
    }
    trabajo = plan(instantes)
    for k, (nombre, franja, fecha, consulta) in enumerate(trabajo):
        archivo = f"{nombre}_{franja}.json"
        ruta = out_dir / archivo
        if archivo not in manifiesto["archivos"] or not ruta.exists():
            resumen["sin_archivo"].append(archivo)
            log(f"   {archivo}: no está descargado")
            continue
        ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        alteracion = comprobar_identidad(ruta, manifiesto["archivos"][archivo], nombre, franja, fecha, huella)
        if alteracion:  # no es el archivo descargado: no se gasta una consulta ni se le da el visto bueno
            manifiesto["archivos"][archivo]["verificacion"] = {
                "estado": "MODIFICADO",
                "motivo": alteracion,
                "verificado_utc": ahora,
            }
            resumen["alterados"].append(archivo)
            log(f"   {archivo}: MODIFICADO ({alteracion})")
            continue
        en_archivo = manifiesto["archivos"][archivo]["elementos"]  # ya comprobado: coincide con el archivo
        try:
            datos, endpoint = pedir(
                cliente,
                consulta_de_recuento(consulta),
                fecha,
                rondas,
                espera_s,
                verificados=verificados,
                pausa_canario_s=pausa_s,
            )
            total = total_del_servidor(datos)
        except (RuntimeError, ValueError) as e:
            manifiesto["archivos"][archivo]["verificacion"] = {
                "estado": "sin_verificar",
                "error": str(e)[:300],
                "verificado_utc": ahora,
            }
            resumen["sin_verificar"].append(archivo)
            log(f"   {archivo}: NO SE PUDO VERIFICAR ({str(e)[:120]})")
        else:
            exacto = fecha is not None
            coincide = (
                total == en_archivo
                if exacto
                else abs(total - en_archivo) <= TOLERANCIA_ESTADO_ACTUAL * max(total, en_archivo)
            )
            manifiesto["archivos"][archivo]["verificacion"] = {
                "estado": "completo" if coincide else "INCOMPLETO",
                "total_servidor": total,
                "elementos_en_archivo": en_archivo,
                "criterio": (
                    "exacto" if exacto else f"tolerancia del {TOLERANCIA_ESTADO_ACTUAL:.0%} (el mapa actual cambia)"
                ),
                "sha256_verificado": manifiesto["archivos"][archivo]["sha256"],
                "espejo": endpoint,
                "verificado_utc": ahora,
            }
            resumen["correctos" if coincide else "incorrectos"].append(archivo)
            log(f"   {archivo}: servidor {total} | archivo {en_archivo} -> {'COMPLETO' if coincide else 'INCOMPLETO'}")
        if k < len(trabajo) - 1:
            time.sleep(pausa_s)
    ruta_manifiesto.write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    resumen["ok"] = bool(resumen["correctos"]) and not (
        resumen["incorrectos"] or resumen["sin_verificar"] or resumen["sin_archivo"] or resumen["alterados"]
    )
    return resumen


def cargar_huella(ruta: Path = HUELLA_POR_DEFECTO) -> Optional[dict]:
    """La huella versionada, o None si no existe. Si existe pero no se puede leer, es un error (no se ignora en silencio)."""
    ruta = Path(ruta)
    if not ruta.exists():
        return None
    try:
        huella = json.loads(ruta.read_text(encoding="utf-8"))
        if not isinstance(huella["archivos"], dict) or not all(
            isinstance(v, dict) for v in huella["archivos"].values()
        ):
            raise TypeError("`archivos` no es un objeto de objetos")
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ValueError(f"La huella {ruta} no se puede leer ({type(e).__name__}): no se ignora en silencio.") from None
    return huella


def escribir_huella(out_dir: Path, destino: Path = HUELLA_POR_DEFECTO) -> dict:
    """Escribe la HUELLA de la descarga: por archivo, solo sha256, elementos, fecha pedida, espejo y fecha de descarga (ningún
    dato de OSM). Se versiona en git como ancla externa: alterar un archivo Y el manifiesto ya no basta sin reescribir
    también la historia del repositorio. Solo se ancla lo verificado como `completo` y de los trozos del plan."""
    manifiesto = json.loads((Path(out_dir) / "manifest.json").read_text(encoding="utf-8"))
    esperados = [f"{nombre}_{franja}.json" for nombre, franja, _, _ in plan()]
    archivos: Dict[str, dict] = {}
    for archivo in esperados:
        entrada = manifiesto["archivos"].get(archivo)
        if entrada is None:
            raise ValueError(f"Falta {archivo} en el manifiesto: no se ancla una descarga incompleta.")
        verificacion = entrada.get("verificacion") or {}
        estado = verificacion.get("estado")
        if estado != "completo":
            raise ValueError(
                f"{archivo} no está verificado como completo (estado: {estado}): ejecuta --verificar antes."
            )
        # «completo» vale para el archivo que se verificó: si en disco hay otro (p. ej. una descarga interrumpida), no se ancla.
        en_disco = sha256_de(Path(out_dir) / archivo) if (Path(out_dir) / archivo).exists() else None
        if (
            en_disco is None
            or en_disco != entrada.get("sha256")
            or en_disco != verificacion.get("sha256_verificado", en_disco)
        ):
            raise ValueError(
                f"{archivo}: el archivo en disco no es el que se verificó como completo: ejecuta --verificar antes."
            )
        archivos[archivo] = {campo: entrada.get(campo) for campo in CAMPOS_DE_LA_HUELLA}
    huella = {
        "formato": 1,
        "nota": "Huella de data/osm_history/ (hashes, recuentos y fechas; sin datos). Ver tools/download_osm_history.py.",
        "area": manifiesto["area"],
        "archivos": archivos,
    }
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(huella, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return huella


def exigir_datos_verificados(out_dir: Path, huella: Optional[dict] = None) -> Dict[str, Path]:
    """LO QUE DEBE LLAMAR EL ANÁLISIS antes de leer los datos: devuelve `{archivo: ruta}` de los trozos del plan solo si TODOS
    son utilizables, y si no lanza `ValueError` listando los problemas. Un trozo es utilizable si está en el manifiesto con
    `verificacion.estado == "completo"`, el archivo existe y su sha256 EN DISCO es el que se verificó (y el del manifiesto) y,
    si se da la `huella`, coincide con ella. Así la regla «el análisis usa solo archivos completos» no depende de la memoria
    de nadie: una descarga interrumpida, un archivo cambiado o sin verificar no pasa."""
    out_dir = Path(out_dir)
    ruta_manifiesto = out_dir / "manifest.json"
    if not ruta_manifiesto.exists():
        raise ValueError(f"No hay {ruta_manifiesto}: primero hay que descargar y verificar.")
    manifiesto = json.loads(ruta_manifiesto.read_text(encoding="utf-8"))
    problemas: List[str] = []
    utilizables: Dict[str, Path] = {}
    for nombre, franja, fecha, _ in plan():
        archivo = f"{nombre}_{franja}.json"
        entrada = (manifiesto.get("archivos") or {}).get(archivo)
        ruta = out_dir / archivo
        if entrada is None or not ruta.exists():
            problemas.append(f"{archivo}: no está descargado")
            continue
        verificacion = entrada.get("verificacion") or {}
        if verificacion.get("estado") != "completo":
            problemas.append(f"{archivo}: no está verificado como completo (estado: {verificacion.get('estado')})")
            continue
        motivo = comprobar_identidad(ruta, entrada, nombre, franja, fecha, huella)
        if motivo:
            problemas.append(f"{archivo}: {motivo}")
            continue
        if verificacion.get("sha256_verificado", entrada["sha256"]) != entrada["sha256"]:
            problemas.append(f"{archivo}: se verificó otro archivo distinto del que hay ahora")
            continue
        utilizables[archivo] = ruta
    if problemas:
        raise ValueError("Los datos no son utilizables para el análisis:\n  " + "\n  ".join(problemas))
    return utilizables


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(SALIDA_POR_DEFECTO), help="directorio donde guardar los JSON (NO la base)")
    ap.add_argument("--instantes", nargs="+", choices=list(INSTANTES), default=list(INSTANTES))
    ap.add_argument("--dry-run", action="store_true", help="muestra las consultas sin hacer ninguna llamada de red")
    ap.add_argument("--pausa", type=float, default=PAUSA_S, help="segundos de pausa entre peticiones")
    ap.add_argument("--rondas", type=int, default=RONDAS, help="rondas por todos los espejos antes de rendirse")
    ap.add_argument("--espera", type=float, default=ESPERA_RONDAS_S, help="segundos entre rondas")
    ap.add_argument(
        "--verificar",
        action="store_true",
        help="no descarga: comprueba que lo ya descargado está completo comparando con el recuento que da el servidor",
    )
    ap.add_argument(
        "--sin-huella",
        action="store_true",
        help="con --verificar: no exige la huella versionada (necesario tras --sobrescribir, para poder volver a anclar)",
    )
    ap.add_argument(
        "--sobrescribir",
        action="store_true",
        help="descarga también los trozos que ya están anclados en la huella (si no, se omiten para no perder datos)",
    )
    ap.add_argument(
        "--huella",
        action="store_true",
        help="escribe la huella (hashes y recuentos, sin datos) para versionarla como ancla externa; "
        "solo si todo está verificado como completo",
    )
    ap.add_argument(
        "--huella-destino",
        default=None,
        help="dónde escribir la huella; por defecto docs/HUELLA_OSM_HISTORY.json, y solo con --out por defecto",
    )
    args = ap.parse_args(argv)

    if args.huella and (args.verificar or args.dry_run or args.sobrescribir or args.sin_huella):
        print(
            "--huella no se combina con --verificar, --dry-run, --sobrescribir ni --sin-huella: ejecútalos por separado."
        )
        return 1
    if args.sin_huella and not args.verificar:
        print("--sin-huella solo tiene sentido con --verificar.")
        return 1

    if args.huella:
        destino = Path(args.huella_destino) if args.huella_destino else HUELLA_POR_DEFECTO
        if not args.huella_destino and Path(args.out).resolve() != SALIDA_POR_DEFECTO.resolve():
            print(
                "--huella con un --out distinto del habitual no puede sobrescribir la huella real del repo: "
                "indica un destino explícito con --huella-destino."
            )
            return 1
        try:
            huella = escribir_huella(Path(args.out), destino)
        except (ValueError, OSError, KeyError) as e:
            print(f"No se escribió la huella: {e}")
            return 1
        print(f"Huella escrita en {destino} ({len(huella['archivos'])} archivos). Versiónala con git.")
        return 0

    trabajo = plan(args.instantes)
    print(
        f"Área: lat {grid.SOUTH}-{grid.NORTH}, lon {grid.WEST}-{grid.EAST} | consultas a pedir: {len(trabajo)} | salida: {args.out}"
    )
    if args.dry_run:
        for nombre, franja, fecha, consulta in trabajo:
            print(f"\n--- {nombre} [{franja}] (fecha pedida: {fecha or 'hoy'}) ---\n{consulta}")
        print("\n(dry-run: no se hizo ninguna llamada de red)")
        return 0

    try:
        huella = None if args.sin_huella else cargar_huella(HUELLA_POR_DEFECTO)
    except ValueError as e:  # huella rota: no se ignora en silencio ni sale como un traceback
        print(f"ERROR: {e}")
        return 1

    if args.verificar:
        if huella is None and not args.sin_huella:
            print(
                "AVISO: no hay huella versionada (docs/HUELLA_OSM_HISTORY.json): se comprueba contra el manifiesto, que vive "
                "junto a los datos y por sí solo no detecta una alteración conjunta."
            )
        try:
            resumen = verificar_descarga(
                OverpassClient(timeout=TIMEOUT_HTTP_S, max_retries=1),
                Path(args.out),
                args.instantes,
                args.pausa,
                rondas=args.rondas,
                espera_s=args.espera,
                huella=huella,
            )
        except (FileNotFoundError, ValueError, KeyError, OSError) as e:  # sin manifiesto, manifiesto ilegible...
            print(f"ERROR: no se pudo verificar: {type(e).__name__}: {e}")
            return 1
        print(
            f"\nVerificación: {len(resumen['correctos'])} completos, {len(resumen['incorrectos'])} INCOMPLETOS, "
            f"{len(resumen['sin_verificar'])} sin verificar, {len(resumen['sin_archivo'])} sin archivo, "
            f"{len(resumen['alterados'])} MODIFICADOS"
        )
        return 0 if resumen["ok"] else 1

    manifiesto = descargar(
        OverpassClient(timeout=TIMEOUT_HTTP_S, max_retries=1),
        Path(args.out),
        args.instantes,
        args.pausa,
        rondas=args.rondas,
        espera_s=args.espera,
        huella=huella,
        sobrescribir=args.sobrescribir,
    )
    print("\nResumen:")
    for archivo, d in manifiesto["archivos"].items():
        print(
            f"   {archivo:24} {d['elementos']:7} elementos | hora del servidor {d.get('osm_base_servidor', d.get('osm_base'))} | {d['espejo']}"
        )
    for archivo in manifiesto.get("omitidos", []):
        print(f"   OMITIDO {archivo}: anclado en la huella (usa --sobrescribir para volver a descargarlo)")
    for f in manifiesto["fallidos"]:
        print(f"   FALLÓ {f['archivo']}: {f['error']}")
    return 0 if not manifiesto["fallidos"] else 1


if __name__ == "__main__":
    sys.exit(main())
