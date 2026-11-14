"""Tests de las etiquetas de cierre y la puerta de tamaño muestral (fase 4, protocolo 3.M de docs/DISENO_ML_RECOMENDACION.md).

Datos sintéticos: cada test fija UNA regla del protocolo. Ningún test lee los datos reales de `data/osm_history/`.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import closure_labels as cl  # noqa: E402
from src.ml import grid  # noqa: E402
from tools import build_closure_labels as herramienta  # noqa: E402
from tools import download_osm_history as dh  # noqa: E402

# Un punto del centro de la rejilla (a > 5 km de cualquier borde) y desplazamientos conocidos en metros.
LAT0, LON0 = 35.890, 14.510
M_LAT = 111_320.0
M_LON = 111_320.0 * math.cos(math.radians(LAT0))


def mas_lejos(metros_norte=0.0, metros_este=0.0):
    return LAT0 + metros_norte / M_LAT, LON0 + metros_este / M_LON


def nodo(ident, punto=None, **tags):
    lat, lon = punto or (LAT0, LON0)
    return {"type": "node", "id": ident, "lat": lat, "lon": lon, "tags": tags}


def via(ident, punto=None, **tags):
    lat, lon = punto or (LAT0, LON0)
    return {"type": "way", "id": ident, "center": {"lat": lat, "lon": lon}, "tags": tags}


def niveles(antes, hoy, ciclo=()):
    """{id: nivel} de los locales de `antes` (los ids son únicos en estos tests)."""
    tabla, _ = cl.etiquetar(antes, hoy, ciclo)
    return {(f.tipo, f.id): str(f.nivel) for f in tabla.itertuples()}


def un_nivel(local_2022, hoy=(), ciclo=()):
    resultado = niveles([local_2022], hoy, ciclo)
    assert list(resultado) == [(local_2022["type"], local_2022["id"])]
    return resultado[(local_2022["type"], local_2022["id"])]


CAFE = dict(amenity="cafe", name="Café Luna")  # categoría food_drink


@pytest.fixture(autouse=True)
def sin_tocar_docs(tmp_path_factory, monkeypatch):
    """Ningún test puede escribir en `docs/` (una mutación llegó a dejar allí un resultado sintético): el destino por defecto
    de `--guardar` apunta a una carpeta temporal."""
    monkeypatch.setattr(
        herramienta, "RESULTADO_POR_DEFECTO", tmp_path_factory.mktemp("docs") / "PUERTA_RIESGO_CIERRE.json"
    )
    real = ROOT / "docs" / "PUERTA_RIESGO_CIERRE.json"
    antes = real.read_bytes() if real.exists() else None
    yield
    despues = real.read_bytes() if real.exists() else None
    assert despues == antes, "un test ha modificado docs/PUERTA_RIESGO_CIERRE.json"


# ---- nombre normalizado ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "crudo, esperado",
    [
        ("Café  Luna", "cafe luna"),
        ("CAFÉ LUNA", "cafe luna"),
        ("  Café\tLuna \n", "cafe luna"),
        ("McDonald's", "mcdonalds"),
        ("Bar-Restaurant, 'El Ñandú'!", "barrestaurant el nandu"),
        ("Il-Ħanut ta' Ġużè", "ilħanut ta guze"),  # la ħ no tiene descomposición: se conserva; la ġ pierde el punto
        ("Pizza & Pasta", "pizza pasta"),  # «&» es puntuación Unicode (Po): se quita y los espacios se colapsan
    ],
)
def test_normalizar_nombre(crudo, esperado):
    assert cl.normalizar_nombre(crudo) == esperado


@pytest.mark.parametrize("valor", [None, "", "   ", "!!!", 12, ["a"], {"a": 1}])
def test_un_nombre_vacio_o_que_no_es_texto_normaliza_a_vacio(valor):
    assert cl.normalizar_nombre(valor) == ""


def test_dos_nombres_son_el_mismo_solo_si_son_iguales_tras_normalizar_sin_coincidencia_aproximada():
    assert cl.normalizar_nombre("Café Luna") == cl.normalizar_nombre("cafe, luna")
    assert cl.normalizar_nombre("Café Luna") != cl.normalizar_nombre("Cafe Luna 2")
    assert cl.normalizar_nombre("Café Luna") != cl.normalizar_nombre("Café Lunas")


# ---- categoría, vacíos y marcas de ciclo de vida -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "tags, esperada",
    [
        ({"amenity": "cafe"}, "food_drink"),
        ({"amenity": "school"}, "school"),
        ({"amenity": "pharmacy"}, "hospital"),
        ({"leisure": "fitness_centre"}, "sport"),
        ({"tourism": "museum"}, "leisure"),
        ({"shop": "mall"}, "mall"),
        ({"shop": "bakery"}, "business"),
        ({"office": "lawyer"}, "business"),
        ({"amenity": "bench"}, None),
        ({"building": "yes"}, None),
        ({}, None),
        (None, None),
    ],
)
def test_categoria_usa_la_clasificacion_del_recolector(tags, esperada):
    assert cl.categoria(tags) == esperada


@pytest.mark.parametrize(
    "tags, vacio",
    [
        ({"shop": "vacant"}, True),
        ({"amenity": "cafe", "disused": "yes"}, True),
        ({"amenity": "cafe", "abandoned": "yes"}, True),
        ({"amenity": "cafe", "vacant": "yes"}, True),
        ({"amenity": "cafe", "disused": "no"}, False),
        ({"amenity": "cafe", "vacant": "no"}, False),
        ({"shop": "bakery"}, False),
        ({}, False),
        (None, False),
    ],
)
def test_local_vacio(tags, vacio):
    assert cl.es_local_vacio(tags) is vacio


@pytest.mark.parametrize("prefijo", ["disused", "was", "abandoned", "demolished", "razed"])
@pytest.mark.parametrize("clave", ["amenity", "shop", "office", "leisure", "tourism"])
def test_toda_combinacion_prefijo_clave_es_una_marca_de_ciclo_de_vida(prefijo, clave):
    assert cl.tiene_marca_de_ciclo({f"{prefijo}:{clave}": "cafe"}) is True


@pytest.mark.parametrize(
    "tags", [{"was:name": "Antiguo"}, {"disused:building": "yes"}, {"amenity": "cafe"}, {}, None, {"disused": "yes"}]
)
def test_lo_que_no_es_prefijo_y_clave_de_categoria_no_es_una_marca(tags):
    assert cl.tiene_marca_de_ciclo(tags) is False


def test_las_marcas_de_ciclo_de_vida_son_las_que_descarga_la_herramienta():
    """Si la descarga cambiase de claves o prefijos, las etiquetas dejarían de ver marcas: un test lo ata."""
    assert cl.CLAVES_CICLO_DE_VIDA == dh.CLAVES_CICLO_DE_VIDA
    assert cl.PREFIJOS_CICLO_DE_VIDA == dh.PREFIJOS_CICLO_DE_VIDA


# ---- punto representativo e identidad ----------------------------------------------------------------------------------
def test_el_punto_es_el_nodo_o_el_centro_del_way():
    assert cl.punto(nodo(1, (35.9, 14.5), amenity="cafe")) == (35.9, 14.5)
    assert cl.punto(via(2, (35.8, 14.4), amenity="cafe")) == (35.8, 14.4)


@pytest.mark.parametrize(
    "elemento",
    [
        {},
        {"lat": None, "lon": 14.5},
        {"lat": "x", "lon": 1},
        {"lat": float("nan"), "lon": 1.0},
        {"center": {}},
        {"center": 5},
        None,
    ],
)
def test_un_elemento_sin_coordenadas_validas_no_tiene_punto(elemento):
    assert cl.punto(elemento) is None


def test_un_nodo_y_un_way_con_el_mismo_numero_son_elementos_distintos():
    assert cl.llave(nodo(123)) != cl.llave(via(123))
    assert cl.llave({"type": "node", "id": True}) is None and cl.llave({"id": 1}) is None and cl.llave(None) is None


# ---- distancia al borde -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lado", ["sur", "norte", "oeste", "este"])
def test_la_distancia_al_borde_se_mide_contra_los_cuatro_lados(lado):
    cerca = {
        "sur": (grid.SOUTH + 300 / M_LAT, LON0),
        "norte": (grid.NORTH - 300 / M_LAT, LON0),
        "oeste": (LAT0, grid.WEST + 300 / M_LON),
        "este": (LAT0, grid.EAST - 300 / M_LON),
    }[lado]
    assert cl.distancia_al_borde_m(*cerca) == pytest.approx(300, abs=3)
    assert cl.distancia_al_borde_m(LAT0, LON0) > 4000


def test_fuera_de_la_rejilla_la_distancia_es_negativa():
    assert cl.distancia_al_borde_m(grid.SOUTH - 0.01, LON0) < 0


# ---- población de estudio ------------------------------------------------------------------------------------------------------
def test_la_poblacion_son_los_locales_de_las_siete_categorias_con_nombre_lejos_del_borde_y_abiertos():
    elementos = [
        nodo(1, **CAFE),  # entra
        via(2, mas_lejos(50, 0), shop="bakery", name="Pan"),  # entra (way)
        nodo(3, amenity="bench", name="Banco"),  # sin categoría
        nodo(4, amenity="cafe"),  # sin nombre
        nodo(5, amenity="cafe", name="!!!"),  # nombre que normaliza a vacío = sin nombre
        {"type": "node", "id": 6, "tags": {"amenity": "cafe", "name": "Sin posición"}},  # sin coordenadas
        nodo(7, (grid.SOUTH + 300 / M_LAT, LON0), amenity="cafe", name="Borde"),  # a 300 m del borde
        nodo(8, (grid.SOUTH - 0.01, LON0), amenity="cafe", name="Fuera"),  # fuera de la rejilla
        nodo(9, shop="vacant", name="Vacío"),
        nodo(10, amenity="cafe", name="Cerrado", disused="yes"),
        nodo(11, amenity="cafe", name="Abandonado", abandoned="yes"),
        nodo(12, amenity="cafe", name="Libre", vacant="yes"),
    ]
    tabla, descartados = cl.poblacion_2022(elementos)
    assert sorted(tabla["id"]) == [1, 2]
    assert descartados == {
        "sin_categoria": 1,
        "sin_nombre": 2,
        "sin_coordenadas": 1,
        "borde_o_fuera": 2,
        "local_vacio": 4,
    }
    assert (
        tabla.set_index("id").loc[2, "categoria"] == "business"
        and tabla.set_index("id").loc[1, "categoria"] == "food_drink"
    )


def test_el_margen_del_borde_es_estricto_a_500_m():
    dentro = nodo(1, (grid.SOUTH + 501 / M_LAT, LON0), **CAFE)
    justo = nodo(2, (grid.SOUTH + 499 / M_LAT, LON0), **CAFE)
    tabla, _ = cl.poblacion_2022([dentro, justo])
    assert list(tabla["id"]) == [1]


def test_los_elementos_repetidos_entre_franjas_cuentan_una_vez_y_nodo_y_way_con_el_mismo_id_son_dos():
    tabla, _ = cl.poblacion_2022([nodo(1, **CAFE), nodo(1, **CAFE), via(1, mas_lejos(10, 10), **CAFE)])
    assert sorted(zip(tabla["tipo"], tabla["id"])) == [("node", 1), ("way", 1)]


def test_una_poblacion_vacia_da_una_tabla_vacia_con_columnas():
    tabla, descartados = cl.poblacion_2022([])
    assert len(tabla) == 0 and list(tabla.columns) == ["tipo", "id", "lat", "lon", "categoria", "nombre_norm"]
    assert sum(descartados.values()) == 0


# ---- nivel 1: fuerte ---------------------------------------------------------------------------------------------------------
def test_fuerte_marca_de_ciclo_sin_categoria_activa():
    hoy_ciclo = [nodo(1, **{"disused:amenity": "cafe", "name": "Café Luna"})]
    assert un_nivel(nodo(1, **CAFE), ciclo=hoy_ciclo) == "fuerte"


def test_fuerte_tambien_con_la_marca_dentro_de_los_archivos_de_hoy_y_otro_prefijo():
    # shop=yes es una categoría activa (business): con la marca es «activa + marca», dudoso (no fuerte, y tampoco otro nivel)
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(1, shop="yes", **{"was:amenity": "cafe"})]) == "dudoso"
    assert un_nivel(nodo(1, **CAFE), ciclo=[nodo(1, **{"was:amenity": "cafe"})]) == "fuerte"
    assert un_nivel(nodo(1, **CAFE), ciclo=[nodo(1, **{"razed:amenity": "cafe"})]) == "fuerte"


@pytest.mark.parametrize(
    "hoy_tags",
    [
        {"shop": "vacant"},  # sin nombre ni categoría original
        {"shop": "vacant", "name": "Otro nombre"},
        {"amenity": "restaurant", "name": "Café Luna", "disused": "yes"},  # cambió de categoría
        {"amenity": "cafe", "name": "Otra cosa", "abandoned": "yes"},  # cambió de nombre
        {"amenity": "cafe", "name": "Café Luna", "vacant": "yes"},  # idéntico pero vacío
    ],
)
def test_fuerte_un_local_vacio_hoy_es_cierre_explicito_aunque_haya_cambiado_de_nombre_o_categoria(hoy_tags):
    """Por eso «fuerte» prevalece sobre «dudoso»."""
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(1, **hoy_tags)]) == "fuerte"


def test_vacio_y_marca_de_ciclo_a_la_vez_es_fuerte():
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(1, shop="vacant", **{"disused:amenity": "cafe"})]) == "fuerte"


def test_la_marca_de_ciclo_con_categoria_activa_y_sin_vacio_es_dudosa_no_fuerte():
    hoy = [nodo(1, amenity="cafe", name="Café Luna", **{"was:shop": "bakery"})]
    assert un_nivel(nodo(1, **CAFE), hoy=hoy) == "dudoso"


def test_los_tags_de_hoy_son_la_union_de_los_dos_archivos():
    """Con la categoría activa en «hoy» y la marca en el archivo de ciclo de vida, el elemento es activo+marca (dudoso), no fuerte."""
    antes = nodo(1, **CAFE)
    assert un_nivel(antes, hoy=[nodo(1, **CAFE)], ciclo=[nodo(1, **{"disused:shop": "yes"})]) == "dudoso"


# ---- nivel 2: superviviente --------------------------------------------------------------------------------------------------
def test_superviviente_misma_categoria_mismo_nombre_normalizado_y_sin_marca():
    assert (
        un_nivel(nodo(1, **CAFE), hoy=[nodo(1, amenity="restaurant", name="CAFE luna!")]) == "superviviente"
    )  # mismo food_drink


def test_el_superviviente_no_depende_de_otras_etiquetas_ni_del_valor_concreto_de_la_clave():
    hoy = [nodo(1, amenity="bar", name="Café Luna", website="https://x", **{"addr:street": "Triq"})]
    assert un_nivel(nodo(1, **CAFE), hoy=hoy) == "superviviente"


# ---- nivel 3: dudoso ---------------------------------------------------------------------------------------------------------
def test_dudoso_sigue_pero_cambio_de_nombre():
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(1, amenity="cafe", name="Café Sol")]) == "dudoso"


def test_dudoso_sigue_pero_perdio_el_nombre():
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(1, amenity="cafe")]) == "dudoso"


def test_dudoso_sigue_pero_cambio_de_categoria():
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(1, shop="bakery", name="Café Luna")]) == "dudoso"


def test_dudoso_ausente_pero_hay_un_elemento_con_el_mismo_nombre_a_menos_de_60_m_nodo_que_pasa_a_way():
    hoy = [via(900, mas_lejos(30, 0), amenity="cafe", name="Café Luna")]
    assert un_nivel(nodo(1, **CAFE), hoy=hoy) == "dudoso"


def test_la_distancia_de_60_m_es_inclusiva_y_mas_alla_es_probable():
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(900, mas_lejos(59, 0), **CAFE)]) == "dudoso"
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(900, mas_lejos(0, 59), **CAFE)]) == "dudoso"
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(900, mas_lejos(61, 0), **CAFE)]) == "probable"
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(900, mas_lejos(0, 61), **CAFE)]) == "probable"


def test_el_emparejamiento_por_nombre_vale_para_cualquiera_de_las_siete_categorias():
    hoy = [nodo(900, mas_lejos(20, 0), shop="bakery", name="Café Luna")]  # otra categoría, mismo nombre
    assert un_nivel(nodo(1, **CAFE), hoy=hoy) == "dudoso"


def test_otro_nombre_a_menos_de_60_m_no_basta():
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(900, mas_lejos(10, 0), amenity="cafe", name="Café Sol")]) == "probable"


def test_el_nombre_de_un_elemento_sin_categoria_activa_no_cuenta_como_remapeo():
    hoy = [nodo(900, mas_lejos(10, 0), building="yes", name="Café Luna")]
    assert un_nivel(nodo(1, **CAFE), hoy=hoy) == "probable"


@pytest.mark.parametrize("vacio", [{"shop": "vacant"}, {"amenity": "cafe", "disused": "yes"}])
def test_un_local_vacio_con_el_mismo_nombre_no_es_un_remapeo(vacio):
    """Interpretación declarada: un negocio re-mapeado tiene que estar abierto, igual que en la población de estudio."""
    hoy = [nodo(900, mas_lejos(10, 0), name="Café Luna", **vacio)]
    assert un_nivel(nodo(1, **CAFE), hoy=hoy) == "probable"


def test_el_remapeo_no_se_aplica_al_que_sigue_con_su_propio_id():
    """Un local que sigue con su (tipo, id) y mismo nombre no necesita emparejamiento: es superviviente aunque haya otro igual cerca."""
    hoy = [nodo(1, **CAFE), nodo(900, mas_lejos(10, 0), **CAFE)]
    assert un_nivel(nodo(1, **CAFE), hoy=hoy) == "superviviente"


def test_el_mismo_numero_pero_otro_tipo_no_es_el_mismo_local():
    """El nodo 1 de 2022 y un way 1 de hoy: son distintos. El nodo no figura hoy; el way, a 0 m con el mismo nombre → dudoso."""
    assert un_nivel(nodo(1, **CAFE), hoy=[via(1, **CAFE)]) == "dudoso"
    assert un_nivel(nodo(1, **CAFE), hoy=[via(1, mas_lejos(500, 0), **CAFE)]) == "probable"


# ---- nivel 4: probable ------------------------------------------------------------------------------------------------------
def test_probable_no_figura_hoy_ni_hay_nada_con_su_nombre_cerca():
    assert un_nivel(nodo(1, **CAFE)) == "probable"
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(2, mas_lejos(2000, 0), amenity="cafe", name="Otro")]) == "probable"


def test_el_mismo_nombre_lejos_no_evita_el_probable():
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(900, mas_lejos(3000, 0), **CAFE)]) == "probable"


def test_no_se_usa_foursquare_ni_ninguna_fuente_externa():
    """`etiquetar` solo recibe elementos de OSM: no hay parámetro para otra fuente (el protocolo la deja fuera de la principal)."""
    import inspect

    assert list(inspect.signature(cl.etiquetar).parameters) == ["elementos_2022", "elementos_hoy", "elementos_ciclo"]


# ---- columnas de cierre -----------------------------------------------------------------------------------------------------
def test_cierre_principal_y_sensibilidad_a():
    antes = [
        nodo(1, **CAFE),
        nodo(2, **{**CAFE, "name": "B"}),
        nodo(3, **{**CAFE, "name": "C"}),
        nodo(4, **{**CAFE, "name": "D"}),
    ]
    ciclo = [nodo(1, **{"disused:amenity": "cafe"})]  # 1: fuerte
    hoy = [
        nodo(3, amenity="cafe", name="C"),
        nodo(4, amenity="cafe", name="Otro"),
    ]  # 2: probable, 3: superviviente, 4: dudoso
    tabla, _ = cl.etiquetar(antes, hoy, ciclo)
    t = tabla.set_index("id")
    assert [str(t.loc[i, "nivel"]) for i in (1, 2, 3, 4)] == ["fuerte", "probable", "superviviente", "dudoso"]
    assert [t.loc[i, "cierre_principal"] for i in (1, 2, 3)] == [1.0, 1.0, 0.0] and math.isnan(
        t.loc[4, "cierre_principal"]
    )
    assert t.loc[1, "cierre_fuerte"] == 1.0 and t.loc[3, "cierre_fuerte"] == 0.0
    assert math.isnan(t.loc[2, "cierre_fuerte"]) and math.isnan(
        t.loc[4, "cierre_fuerte"]
    )  # probable y dudoso no entran en A


def test_el_orden_de_las_reglas_decide_la_primera_que_se_cumple_sin_solapes():
    """Cada local tiene exactamente un nivel, y la tabla recorre los cuatro."""
    antes = [nodo(i, **{**CAFE, "name": f"N{i}"}) for i in range(1, 5)]
    hoy = [nodo(2, amenity="cafe", name="N2"), nodo(3, amenity="cafe", name="distinto")]
    ciclo = [nodo(1, **{"was:amenity": "cafe"})]
    tabla, _ = cl.etiquetar(antes, hoy, ciclo)
    assert sorted(tabla["nivel"].astype(str)) == ["dudoso", "fuerte", "probable", "superviviente"]
    assert list(tabla["nivel"].cat.categories) == ["fuerte", "superviviente", "dudoso", "probable"]


# ---- puerta de tamaño muestral ----------------------------------------------------------------------------------------------
def _en_bloque(b):
    """Un punto en el bloque de 1 km número `b` (cuadrícula sin desplazar, 4 celdas = 1 km)."""
    filas_de_bloques = grid.N_ROWS // 4
    fila, col = (b % filas_de_bloques) * 4 + 1, (b // filas_de_bloques) * 4 + 1
    lat, lon = grid.cell_center(fila, col)
    return float(lat), float(lon)


def _tabla(cierres_por_bloque, otros=()):
    """Tabla de etiquetas sintética: `cierres_por_bloque` es la lista de bloques con un cierre principal cada uno (repetir un
    bloque da más cierres en él); `otros` son (nivel, bloque)."""
    filas = []
    for b in cierres_por_bloque:
        lat, lon = _en_bloque(b)
        filas.append({"lat": lat, "lon": lon, "nivel": "probable", "cierre_principal": 1.0})
    for nivel, b in otros:
        lat, lon = _en_bloque(b)
        filas.append(
            {"lat": lat, "lon": lon, "nivel": nivel, "cierre_principal": {"superviviente": 0.0}.get(nivel, np.nan)}
        )
    t = pd.DataFrame(filas, columns=["lat", "lon", "nivel", "cierre_principal"])
    t["nivel"] = pd.Categorical(t["nivel"], categories=list(cl.NIVELES))
    return t


def test_hay_bloques_de_sobra_en_la_rejilla_para_estos_tests():
    assert (grid.N_ROWS // 4) * (grid.N_COLS // 4) >= 60


def test_la_puerta_se_cumple_con_60_cierres_en_30_bloques_exactos():
    resultado = cl.puerta(_tabla(list(range(30)) * 2))
    assert (resultado["cierres_principales"], resultado["bloques_con_cierre"], resultado["pasa"]) == (60, 30, True)
    assert "se cumple" in resultado["veredicto"]


def test_con_59_cierres_no_pasa_aunque_haya_bloques_de_sobra():
    resultado = cl.puerta(_tabla(list(range(30)) + list(range(29))))
    assert (resultado["cierres_principales"], resultado["bloques_con_cierre"], resultado["pasa"]) == (59, 30, False)
    assert resultado["veredicto"] == "no concluyente: no se entrena"


def test_con_29_bloques_no_pasa_aunque_haya_cierres_de_sobra():
    resultado = cl.puerta(_tabla(list(range(29)) * 4))
    assert (resultado["cierres_principales"], resultado["bloques_con_cierre"], resultado["pasa"]) == (116, 29, False)


def test_los_bloques_se_cuentan_por_bloque_de_1_km_no_por_celda():
    """64 cierres en las 16 celdas de un mismo bloque de 1 km (filas y columnas 0-3): un único bloque."""
    filas = []
    for i in range(16):
        lat, lon = grid.cell_center(i // 4, i % 4)
        filas += [{"lat": float(lat), "lon": float(lon), "nivel": "probable", "cierre_principal": 1.0}] * 4
    t = pd.DataFrame(filas)
    t["nivel"] = pd.Categorical(t["nivel"], categories=list(cl.NIVELES))
    resultado = cl.puerta(t)
    assert (resultado["cierres_principales"], resultado["bloques_con_cierre"], resultado["pasa"]) == (64, 1, False)


def test_celdas_vecinas_de_bloques_distintos_son_bloques_distintos():
    """Las filas 3 y 4 están en bloques de 1 km diferentes (la cuadrícula de bloques no está desplazada)."""
    filas = []
    for fila in (3, 4):
        lat, lon = grid.cell_center(fila, 0)
        filas.append({"lat": float(lat), "lon": float(lon), "nivel": "probable", "cierre_principal": 1.0})
    t = pd.DataFrame(filas)
    t["nivel"] = pd.Categorical(t["nivel"], categories=list(cl.NIVELES))
    assert cl.puerta(t)["bloques_con_cierre"] == 2


def test_solo_cuentan_los_cierres_principales_no_los_superviviente_ni_dudosos():
    t = _tabla(
        list(range(30)), otros=[("superviviente", b) for b in range(40, 60)] + [("dudoso", b) for b in range(60, 70)]
    )
    resultado = cl.puerta(t)
    assert resultado["cierres_principales"] == 30 and resultado["bloques_con_cierre"] == 30 and not resultado["pasa"]
    assert resultado["por_nivel"] == {"fuerte": 0, "superviviente": 20, "dudoso": 10, "probable": 30}
    assert resultado["poblacion"] == 60


def test_sin_cierres_no_pasa_y_no_falla():
    vacia = pd.DataFrame(
        {"lat": [], "lon": [], "nivel": pd.Categorical([], categories=list(cl.NIVELES)), "cierre_principal": []}
    )
    resultado = cl.puerta(vacia)
    assert (resultado["cierres_principales"], resultado["bloques_con_cierre"], resultado["pasa"]) == (0, 0, False)


def test_los_minimos_de_la_puerta_son_los_del_protocolo():
    assert (cl.MIN_CIERRES_PRINCIPALES, cl.MIN_BLOQUES_CON_CIERRE) == (60, 30)
    assert cl.puerta(_tabla([0]))["minimos"] == {"cierres_principales": 60, "bloques_con_cierre": 30}


# ---- la herramienta ---------------------------------------------------------------------------------------------------------
def _escribe(carpeta, nombre, elementos):
    ruta = carpeta / nombre
    ruta.write_text(json.dumps({"elements": elementos}), encoding="utf-8")
    return ruta


def _entradas_falsas(tmp_path, monkeypatch, antes, hoy, ciclo):
    """Los 7 trozos del plan con datos sintéticos, y `exigir_datos_verificados` devolviéndolos (la verificación real se prueba en
    tests/test_download_osm_history.py)."""
    rutas = {
        "2022-01-01_0.json": _escribe(tmp_path, "2022-01-01_0.json", antes[0::2]),
        "2022-01-01_1.json": _escribe(tmp_path, "2022-01-01_1.json", antes[1::2]),
        "2024-01-01_0.json": _escribe(tmp_path, "2024-01-01_0.json", [nodo(999, **CAFE)]),  # no se usa en esta etapa
        "2024-01-01_1.json": _escribe(tmp_path, "2024-01-01_1.json", []),
        "hoy_0.json": _escribe(tmp_path, "hoy_0.json", hoy[0::2]),
        "hoy_1.json": _escribe(tmp_path, "hoy_1.json", hoy[1::2]),
        "ciclo_de_vida_0.json": _escribe(tmp_path, "ciclo_de_vida_0.json", ciclo),
    }
    manifiesto = {"archivos": {a: {"sha256": f"{i:064x}"} for i, a in enumerate(rutas)}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    llamadas = []
    monkeypatch.setattr(
        dh, "exigir_datos_verificados", lambda out_dir, huella=None: llamadas.append((out_dir, huella)) or rutas
    )
    monkeypatch.setattr(dh, "cargar_huella", lambda ruta: {"archivos": {}})
    return llamadas


def test_la_herramienta_verifica_antes_de_leer_e_imprime_la_puerta(tmp_path, monkeypatch, capsys):
    antes = [nodo(i, **{**CAFE, "name": f"N{i}"}) for i in range(1, 5)]
    llamadas = _entradas_falsas(tmp_path, monkeypatch, antes, hoy=[nodo(3, amenity="cafe", name="N3")], ciclo=[])
    assert herramienta.main(["--out", str(tmp_path)]) == 0
    salida = capsys.readouterr().out
    assert llamadas == [(tmp_path, {"archivos": {}})]  # se verificó con la huella
    assert "Población de estudio" in salida and "fuerte 0 | superviviente 1 | dudoso 0 | probable 3" in salida
    assert "PUERTA: no concluyente: no se entrena" in salida


def test_la_herramienta_se_niega_si_los_datos_no_estan_verificados_y_no_lee_nada(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(dh, "cargar_huella", lambda ruta: {"archivos": {}})

    def niega(out_dir, huella=None):
        raise ValueError("Los datos no son utilizables para el análisis: hoy_0.json: no está verificado")

    monkeypatch.setattr(dh, "exigir_datos_verificados", niega)
    leidos = []
    monkeypatch.setattr(herramienta, "leer_elementos", lambda ruta: leidos.append(ruta) or [])
    assert herramienta.main(["--out", str(tmp_path)]) == 1
    assert "no son utilizables" in capsys.readouterr().out and leidos == []


def test_la_herramienta_se_niega_sin_huella_versionada(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(dh, "cargar_huella", lambda ruta: None)
    monkeypatch.setattr(
        dh, "exigir_datos_verificados", lambda *a, **k: pytest.fail("no debe verificar ni leer sin huella")
    )
    assert herramienta.main(["--out", str(tmp_path)]) == 1
    assert "falta docs/HUELLA_OSM_HISTORY.json" in capsys.readouterr().out


def test_la_herramienta_con_una_huella_rota_sale_con_error_claro(tmp_path, monkeypatch, capsys):
    def rota(ruta):
        raise ValueError("huella ilegible: no se ignora en silencio")

    monkeypatch.setattr(dh, "cargar_huella", rota)
    assert herramienta.main(["--out", str(tmp_path)]) == 1
    assert "ERROR" in capsys.readouterr().out


def test_guardar_escribe_solo_agregados_y_nunca_etiquetas_por_local(tmp_path, monkeypatch, capsys):
    antes = [nodo(i, **{**CAFE, "name": f"Nombre{i}"}) for i in range(1, 6)]
    _entradas_falsas(tmp_path, monkeypatch, antes, hoy=[], ciclo=[nodo(1, **{"disused:amenity": "cafe"})])
    destino = tmp_path / "resultado.json"
    assert herramienta.main(["--out", str(tmp_path), "--guardar", "--destino", str(destino)]) == 0
    texto = destino.read_text(encoding="utf-8")
    datos = json.loads(texto)
    assert datos["poblacion"] == 5 and datos["por_nivel"] == {
        "fuerte": 1,
        "superviviente": 0,
        "dudoso": 0,
        "probable": 4,
    }
    assert datos["pasa"] is False and datos["protocolo"].startswith("docs/DISENO_ML_RECOMENDACION.md")
    assert set(datos["entradas_sha256"]) == {
        "2022-01-01_0.json",
        "2022-01-01_1.json",
        "2024-01-01_0.json",
        "2024-01-01_1.json",
        "hoy_0.json",
        "hoy_1.json",
        "ciclo_de_vida_0.json",
    }
    assert (
        "Nombre1" not in texto and '"lat"' not in texto and '"id"' not in texto
    )  # ni nombres, ni posiciones, ni identificadores


def test_sin_guardar_no_se_escribe_ningun_archivo_ni_en_el_destino_por_defecto(tmp_path, monkeypatch):
    por_defecto = tmp_path / "por_defecto" / "PUERTA.json"
    por_defecto.parent.mkdir()
    monkeypatch.setattr(herramienta, "RESULTADO_POR_DEFECTO", por_defecto)
    datos = tmp_path / "datos"
    datos.mkdir()
    _entradas_falsas(datos, monkeypatch, [nodo(1, **CAFE)], hoy=[], ciclo=[])
    antes = sorted(p.name for p in datos.iterdir())
    assert herramienta.main(["--out", str(datos)]) == 0
    assert sorted(p.name for p in datos.iterdir()) == antes and not por_defecto.exists()


def test_guardar_sin_destino_escribe_en_el_destino_por_defecto(tmp_path, monkeypatch):
    por_defecto = tmp_path / "por_defecto" / "PUERTA.json"
    por_defecto.parent.mkdir()
    monkeypatch.setattr(herramienta, "RESULTADO_POR_DEFECTO", por_defecto)
    datos = tmp_path / "datos"
    datos.mkdir()
    _entradas_falsas(datos, monkeypatch, [nodo(1, **CAFE)], hoy=[], ciclo=[])
    assert herramienta.main(["--out", str(datos), "--guardar"]) == 0
    assert json.loads(por_defecto.read_text(encoding="utf-8"))["poblacion"] == 1


def test_la_herramienta_agrupa_los_trozos_por_instante_y_no_usa_2024(tmp_path, monkeypatch):
    antes = [nodo(1, **CAFE)]
    _entradas_falsas(tmp_path, monkeypatch, antes, hoy=[], ciclo=[])
    fotos = herramienta.cargar_fotos(dh.exigir_datos_verificados(tmp_path, None))
    assert set(fotos) == {"2022", "hoy", "ciclo"} and [e["id"] for e in fotos["2022"]] == [1]
    assert all(e["id"] != 999 for g in fotos.values() for e in g)  # el elemento de 2024 no entra


def test_un_elements_que_no_es_lista_se_rechaza(tmp_path):
    ruta = tmp_path / "x.json"
    ruta.write_text(json.dumps({"elements": {"a": 1}}), encoding="utf-8")
    with pytest.raises(ValueError, match="no es una lista"):
        herramienta.leer_elementos(ruta)


# ---- casos límite que las mutaciones mostraron sin cubrir -----------------------------------------------------------------
def test_justo_a_500_m_del_borde_se_excluye_la_poblacion_es_a_MAS_de_500(monkeypatch):
    monkeypatch.setattr(cl, "distancia_al_borde_m", lambda lat, lon: 500.0)
    assert len(cl.poblacion_2022([nodo(1, **CAFE)])[0]) == 0
    monkeypatch.setattr(cl, "distancia_al_borde_m", lambda lat, lon: 500.01)
    assert len(cl.poblacion_2022([nodo(1, **CAFE)])[0]) == 1


def test_justo_a_60_m_es_el_mismo_sitio_el_umbral_es_inclusivo(monkeypatch):
    monkeypatch.setattr(cl.grid, "haversine_m", lambda *a: 60.0)
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(900, **CAFE)]) == "dudoso"
    monkeypatch.setattr(cl.grid, "haversine_m", lambda *a: 60.01)
    assert un_nivel(nodo(1, **CAFE), hoy=[nodo(900, **CAFE)]) == "probable"


def test_si_un_elemento_viene_repetido_con_datos_distintos_gana_el_primero():
    """Determinista: las franjas solapadas traen copias iguales, pero si no lo fueran no depende del azar."""
    tabla, _ = cl.poblacion_2022([nodo(1, amenity="cafe", name="Primero"), nodo(1, amenity="cafe", name="Segundo")])
    assert list(tabla["nombre_norm"]) == ["primero"]


def test_si_hoy_y_ciclo_de_vida_discrepan_en_un_tag_manda_hoy():
    """Hoy dice «Café Luna»; el archivo de ciclo de vida (otra consulta, otro instante) dice «Otro»: manda hoy, así que es superviviente."""
    assert (
        un_nivel(
            nodo(1, **CAFE), hoy=[nodo(1, **CAFE)], ciclo=[nodo(1, amenity="cafe", name="Otro", **{"was:shop": "x"})]
        )
        == "dudoso"
    )
    assert (
        un_nivel(nodo(1, **CAFE), hoy=[nodo(1, **CAFE)], ciclo=[nodo(1, amenity="cafe", name="Otro")])
        == "superviviente"
    )


def test_un_way_de_2022_se_empareja_con_el_way_de_hoy_y_no_con_un_nodo_del_mismo_numero():
    antes = via(7, **CAFE)
    assert un_nivel(antes, hoy=[via(7, **CAFE)]) == "superviviente"
    # el nodo 7 de hoy no es el way 7: el way no figura hoy, y el nodo (mismo nombre, a 0 m) lo convierte en un posible re-mapeo
    assert un_nivel(antes, hoy=[nodo(7, **CAFE)]) == "dudoso"
    assert un_nivel(antes, hoy=[nodo(7, mas_lejos(500, 0), **CAFE)]) == "probable"


# ---- guardas de la herramienta ---------------------------------------------------------------------------------------------
def _rutas_del_plan(tmp_path):
    rutas = {}
    for nombre, franja, _, _ in dh.plan():
        archivo = f"{nombre}_{franja}.json"
        rutas[archivo] = _escribe(tmp_path, archivo, [nodo(1, **CAFE)])
    return rutas


def test_cargar_fotos_asigna_todos_los_archivos_del_plan_real(tmp_path):
    """Los nombres salen de `dh.plan()`, no escritos a mano: si la descarga cambia de nombres, este test lo ve."""
    fotos = herramienta.cargar_fotos(_rutas_del_plan(tmp_path))
    assert len(fotos["2022"]) == 2 and len(fotos["hoy"]) == 2 and len(fotos["ciclo"]) == 1


@pytest.mark.parametrize("prefijo", ["2022-01-01_", "hoy_", "ciclo_de_vida_"])
def test_cargar_fotos_se_niega_si_un_grupo_queda_vacio(tmp_path, prefijo):
    """Sin «hoy», todos los locales saldrían «probables» y la puerta se cumpliría sin avisar."""
    rutas = {a: r for a, r in _rutas_del_plan(tmp_path).items() if not a.startswith(prefijo)}
    with pytest.raises(ValueError, match="No hay archivos verificados para"):
        herramienta.cargar_fotos(rutas)


def test_cargar_fotos_se_niega_ante_un_archivo_desconocido(tmp_path):
    rutas = _rutas_del_plan(tmp_path)
    rutas["actual_0.json"] = _escribe(tmp_path, "actual_0.json", [])
    with pytest.raises(ValueError, match="no encajan en ningún instante"):
        herramienta.cargar_fotos(rutas)


def test_la_herramienta_con_la_verificacion_real_se_niega_ante_datos_sin_verificar(tmp_path, monkeypatch, capsys):
    """Sin doble de `exigir_datos_verificados`: archivos y manifiesto sin `verificacion` deben ser rechazados por la función real."""
    rutas = _rutas_del_plan(tmp_path)
    manifiesto = {
        "archivos": {
            a: {"sha256": dh.sha256_de(r), "elementos": 1, "fecha_pedida": None, "espejo": "x"}
            for a, r in rutas.items()
        }
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    monkeypatch.setattr(dh, "cargar_huella", lambda ruta: {"archivos": {}})
    leidos = []
    monkeypatch.setattr(herramienta, "leer_elementos", lambda ruta: leidos.append(ruta) or [])
    assert herramienta.main(["--out", str(tmp_path)]) == 1
    assert "no está verificado como completo" in capsys.readouterr().out and leidos == []
