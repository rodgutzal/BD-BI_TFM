"""Etiquetas de «cierre» de la fase 4 (riesgo de cierre exploratorio) y puerta de tamaño muestral.

Implementa, SIN ninguna decisión nueva, el protocolo fijado antes de descargar los datos: sección 3.M de
`docs/DISENO_ML_RECOMENDACION.md` (v2.1). Cada función cita la regla del protocolo que aplica. Son funciones puras sobre
listas de elementos de OpenStreetMap (`{"type", "id", "lat"/"lon" o "center", "tags"}`); no leen archivos ni red. Quien las
llama (`tools/build_closure_labels.py`) es quien debe haber pasado `exigir_datos_verificados` antes de leer los datos.

Un local es el par **(tipo, id)**. Los niveles se evalúan en orden y decide el primero que se cumple:
fuerte → superviviente → dudoso → probable. **Cierre principal** = fuerte ∪ probable contra superviviente (los dudosos no
entran ni como positivo ni como negativo). **Sensibilidad A** (descriptiva) = solo fuertes contra superviviente.

Interpretaciones de detalle (fijadas al escribir el código, antes de mirar ningún recuento; se declaran en el protocolo):
- «Marca de ciclo de vida» = clave `prefijo:clave` con prefijo en `PREFIJOS_CICLO_DE_VIDA` y clave en `CLAVES_CICLO_DE_VIDA`
  (las mismas que descarga la herramienta); `was:name` por sí sola no es una marca.
- Los tags de «hoy» de un elemento son la unión de lo que traen los archivos de «hoy» y de ciclo de vida (el mismo elemento
  puede salir en los dos).
- Para el emparejamiento por nombre a ≤ 60 m solo cuentan elementos de «hoy» con categoría activa, nombre y que NO sean
  locales vacíos (`shop=vacant`, `disused=yes`...): un negocio re-mapeado tiene que estar abierto, igual que en la población.
- Nombre normalizado: minúsculas, sin tildes (NFKD), sin signos de puntuación (categoría Unicode P*) y espacios colapsados.
"""

import math
import unicodedata
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.ml import grid, validation
from src.poi_client import OverpassClient

# Marcas de ciclo de vida (las mismas que descarga `tools/download_osm_history.py`; un test lo fija).
CLAVES_CICLO_DE_VIDA = ("amenity", "shop", "office", "leisure", "tourism")
PREFIJOS_CICLO_DE_VIDA = ("disused", "was", "abandoned", "demolished", "razed")

# Un local con estas etiquetas no es un negocio abierto (protocolo: población de estudio y nivel «fuerte»).
MARCAS_DE_LOCAL_VACIO = (("shop", "vacant"), ("disused", "yes"), ("abandoned", "yes"), ("vacant", "yes"))

MARGEN_BORDE_M = 500.0  # la población excluye lo que está a ≤ 500 m del borde de la rejilla
UMBRAL_MISMO_NOMBRE_M = 60.0  # re-mapeo: mismo nombre normalizado a ≤ 60 m
MIN_CIERRES_PRINCIPALES = 60  # puerta de tamaño muestral
MIN_BLOQUES_CON_CIERRE = 30

NIVELES = ("fuerte", "superviviente", "dudoso", "probable")
LLAVE = Tuple[str, int]


def normalizar_nombre(nombre) -> str:
    """Minúsculas, sin tildes, sin signos de puntuación y con los espacios colapsados. Algo que no sea texto da ''."""
    if not isinstance(nombre, str):
        return ""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", nombre.lower()) if not unicodedata.combining(c))
    sin_signos = "".join(c for c in sin_tildes if not unicodedata.category(c).startswith("P"))
    return " ".join(sin_signos.split())


def categoria(tags: Optional[dict]) -> Optional[str]:
    """Una de las siete categorías (la misma clasificación del recolector) o None si el elemento no encaja en ninguna."""
    if not isinstance(tags, dict):
        return None
    clasificado = OverpassClient._classify(tags)
    return clasificado[0] if clasificado else None


def es_local_vacio(tags: Optional[dict]) -> bool:
    """`shop=vacant`, `disused=yes`, `abandoned=yes` o `vacant=yes`: no es un negocio abierto."""
    if not isinstance(tags, dict):
        return False
    return any(tags.get(clave) == valor for clave, valor in MARCAS_DE_LOCAL_VACIO)


def tiene_marca_de_ciclo(tags: Optional[dict]) -> bool:
    """¿Hay alguna clave `prefijo:clave` de ciclo de vida (p. ej. `disused:amenity`)?"""
    if not isinstance(tags, dict):
        return False
    return any(f"{p}:{c}" in tags for p in PREFIJOS_CICLO_DE_VIDA for c in CLAVES_CICLO_DE_VIDA)


def punto(elemento: dict) -> Optional[Tuple[float, float]]:
    """(lat, lon) representativo: el nodo, o el centro si es un way. None si no hay coordenadas válidas."""
    if not isinstance(elemento, dict):
        return None
    centro = elemento.get("center")
    lat, lon = (
        (centro.get("lat"), centro.get("lon"))
        if isinstance(centro, dict)
        else (elemento.get("lat"), elemento.get("lon"))
    )
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    return (lat, lon) if math.isfinite(lat) and math.isfinite(lon) else None


def llave(elemento: dict) -> Optional[LLAVE]:
    """(tipo, id): un nodo 123 y un way 123 son elementos distintos."""
    if not isinstance(elemento, dict):
        return None
    tipo, ident = elemento.get("type"), elemento.get("id")
    if not isinstance(tipo, str) or isinstance(ident, bool) or not isinstance(ident, int):
        return None
    return tipo, ident


def distancia_al_borde_m(lat: float, lon: float) -> float:
    """Metros hasta el borde más cercano de la rejilla (negativo si está fuera)."""
    m_lat = grid._M_PER_DEG_LAT
    m_lon = grid._M_PER_DEG_LAT * math.cos(math.radians(lat))
    return min(
        (lat - grid.SOUTH) * m_lat, (grid.NORTH - lat) * m_lat, (lon - grid.WEST) * m_lon, (grid.EAST - lon) * m_lon
    )


def _unicos(elementos: Iterable[dict]) -> Dict[LLAVE, dict]:
    """Un elemento por (tipo, id): las franjas de la descarga se solapan y el mismo elemento puede venir dos veces."""
    salida: Dict[LLAVE, dict] = {}
    for e in elementos:
        k = llave(e)
        if k is not None and k not in salida:
            salida[k] = e
    return salida


def poblacion_2022(elementos: Iterable[dict]) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Población de estudio (protocolo): elementos de 2022 en las siete categorías, con nombre, dentro de la rejilla y a más
    de 500 m de su borde, que no sean locales vacíos. Devuelve la tabla y cuántos se descartaron por cada motivo."""
    descartados = {"sin_categoria": 0, "sin_nombre": 0, "sin_coordenadas": 0, "borde_o_fuera": 0, "local_vacio": 0}
    filas: List[dict] = []
    for k, e in _unicos(elementos).items():
        tags = e.get("tags") if isinstance(e.get("tags"), dict) else {}
        cat = categoria(tags)
        nombre = normalizar_nombre(tags.get("name"))
        p = punto(e)
        if cat is None:
            descartados["sin_categoria"] += 1
        elif not nombre:
            descartados["sin_nombre"] += 1
        elif p is None:
            descartados["sin_coordenadas"] += 1
        elif distancia_al_borde_m(*p) <= MARGEN_BORDE_M:
            descartados["borde_o_fuera"] += 1
        elif es_local_vacio(tags):
            descartados["local_vacio"] += 1
        else:
            filas.append({"tipo": k[0], "id": k[1], "lat": p[0], "lon": p[1], "categoria": cat, "nombre_norm": nombre})
    columnas = ["tipo", "id", "lat", "lon", "categoria", "nombre_norm"]
    return pd.DataFrame(filas, columns=columnas), descartados


def _foto_de_hoy(elementos_hoy: Iterable[dict], elementos_ciclo: Iterable[dict]) -> Dict[LLAVE, dict]:
    """(tipo, id) → {"tags": unión de los tags de «hoy» y de ciclo de vida, "punto": ...}. Si un mismo elemento sale en los dos
    archivos, los tags de «hoy» mandan en caso de choque."""
    hoy, ciclo = _unicos(elementos_hoy), _unicos(elementos_ciclo)
    salida: Dict[LLAVE, dict] = {}
    for k in {**ciclo, **hoy}:
        tags: dict = {}
        for fuente in (ciclo.get(k), hoy.get(k)):
            if fuente is not None and isinstance(fuente.get("tags"), dict):
                tags.update(fuente["tags"])
        salida[k] = {"tags": tags, "punto": punto(hoy.get(k) or ciclo[k])}
    return salida


def _candidatos_por_nombre(foto: Dict[LLAVE, dict]) -> Dict[str, List[Tuple[float, float]]]:
    """Elementos de «hoy» con los que un local ausente puede ser un re-mapeo: categoría activa, nombre, no vacíos."""
    por_nombre: Dict[str, List[Tuple[float, float]]] = {}
    for dato in foto.values():
        tags = dato["tags"]
        nombre = normalizar_nombre(tags.get("name"))
        if nombre and dato["punto"] is not None and categoria(tags) is not None and not es_local_vacio(tags):
            por_nombre.setdefault(nombre, []).append(dato["punto"])
    return por_nombre


def _hay_mismo_nombre_cerca(
    p: Tuple[float, float], nombre: str, candidatos: Dict[str, List[Tuple[float, float]]]
) -> bool:
    return any(
        float(grid.haversine_m(p[0], p[1], lat, lon)) <= UMBRAL_MISMO_NOMBRE_M
        for lat, lon in candidatos.get(nombre, ())
    )


def nivel_de_cierre(local: dict, foto: Dict[LLAVE, dict], candidatos: Dict[str, List[Tuple[float, float]]]) -> str:
    """Nivel de un local de 2022 (`tipo`, `id`, `lat`, `lon`, `categoria`, `nombre_norm`) frente a la foto de «hoy».
    Orden del protocolo: la primera regla que se cumple decide."""
    dato = foto.get((local["tipo"], local["id"]))
    tags = dato["tags"] if dato else None
    activa = categoria(tags) if dato else None
    marca = tiene_marca_de_ciclo(tags) if dato else False
    if dato and (es_local_vacio(tags) or (marca and activa is None)):
        return "fuerte"  # 1: vacío explícito (aunque haya cambiado de nombre o categoría), o marca sin categoría activa
    if dato and activa is not None:
        if not marca and activa == local["categoria"] and normalizar_nombre(tags.get("name")) == local["nombre_norm"]:
            return "superviviente"  # 2: misma categoría, mismo nombre, ninguna marca
        return "dudoso"  # 3: sigue pero cambió de nombre o categoría, o categoría activa con marca de ciclo de vida
    # El (tipo, id) no figura hoy: ¿hay un elemento con el mismo nombre normalizado a ≤ 60 m (re-mapeo, nodo → way)?
    if _hay_mismo_nombre_cerca((local["lat"], local["lon"]), local["nombre_norm"], candidatos):
        return "dudoso"
    return "probable"  # 4: todo el resto


def etiquetar(elementos_2022: Iterable[dict], elementos_hoy: Iterable[dict], elementos_ciclo: Iterable[dict]):
    """Etiqueta cada local de la población de 2022. Devuelve (tabla, descartados de la población). La tabla añade `nivel`,
    `cierre_principal` (1 fuerte/probable, 0 superviviente, NaN dudoso) y `cierre_fuerte` (sensibilidad A: 1 fuerte, 0
    superviviente, NaN el resto). **No se versiona por local** (protocolo): solo agregados."""
    poblacion, descartados = poblacion_2022(elementos_2022)
    foto = _foto_de_hoy(elementos_hoy, elementos_ciclo)
    candidatos = _candidatos_por_nombre(foto)
    niveles = [nivel_de_cierre(fila, foto, candidatos) for fila in poblacion.to_dict("records")]
    poblacion["nivel"] = pd.Categorical(niveles, categories=list(NIVELES))
    nivel = poblacion["nivel"].astype(str)
    poblacion["cierre_principal"] = np.where(
        nivel.isin(["fuerte", "probable"]), 1.0, np.where(nivel == "superviviente", 0.0, np.nan)
    )
    poblacion["cierre_fuerte"] = np.where(nivel == "fuerte", 1.0, np.where(nivel == "superviviente", 0.0, np.nan))
    return poblacion, descartados


def puerta(etiquetas: pd.DataFrame) -> dict:
    """Puerta de tamaño muestral (protocolo): se entrena y se evalúa solo si hay ≥ 60 cierres principales y ≥ 30 bloques de
    1 km (cuadrícula SIN desplazar) con algún cierre. Si no: «no concluyente: no se entrena»."""
    cierres = etiquetas[etiquetas["cierre_principal"] == 1.0]
    if len(cierres):
        filas, cols = grid.cell_index(cierres["lat"].to_numpy(), cierres["lon"].to_numpy())
        bloques = int(len(np.unique(validation.block_labels(filas, cols))))
    else:
        bloques = 0
    n_cierres = int(len(cierres))
    pasa = n_cierres >= MIN_CIERRES_PRINCIPALES and bloques >= MIN_BLOQUES_CON_CIERRE
    por_nivel = {n: int((etiquetas["nivel"].astype(str) == n).sum()) for n in NIVELES}
    return {
        "poblacion": int(len(etiquetas)),
        "por_nivel": por_nivel,
        "cierres_principales": n_cierres,
        "bloques_con_cierre": bloques,
        "minimos": {"cierres_principales": MIN_CIERRES_PRINCIPALES, "bloques_con_cierre": MIN_BLOQUES_CON_CIERRE},
        "pasa": bool(pasa),
        "veredicto": "la puerta se cumple: se puede entrenar y evaluar" if pasa else "no concluyente: no se entrena",
    }
