"""Pruebas de la descarga del estado histórico de OpenStreetMap (tools/download_osm_history.py, fase 4 §3.M).

Sin red: se usa un cliente falso. Lo más importante que comprueban: que un espejo de Overpass que IGNORA la fecha pedida
(y devuelve el mapa actual) se rechaza, porque si no, el «estado de 2022» sería en realidad el de hoy y no habría cierres.

OJO con cómo se detecta: medido contra overpass-api.de, `osm3s.timestamp_osm_base` trae SIEMPRE la hora actual del servidor,
también en una respuesta con datos de 2022. Por eso la fecha se comprueba con un canario (`out meta`: el `timestamp` de cada
elemento) y NO con esa hora base; una prueba de regresión fija que una respuesta histórica con hora base actual se acepta.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.poi_client import CATEGORY_TAGS, OverpassClient  # noqa: E402
from tools import download_osm_history as dh  # noqa: E402

HORA_ACTUAL_DEL_SERVIDOR = "2026-11-13T21:38:33Z"  # lo que overpass-api.de pone en `osm3s` incluso para datos de 2022
ANTIGUO = "2021-06-01T10:00:00Z"  # versión de un elemento anterior al canario (2022-01-01)
RECIENTE = "2026-05-01T10:00:00Z"  # versión posterior: la de un mapa actual


class CuerpoTruncado(Exception):
    """Marca: el servidor responde HTTP 200 pero el cuerpo es un JSON cortado a la mitad (se rompe al leerlo)."""


class Respuesta:
    def __init__(self, datos, error=None, json_roto=False):
        self.datos, self.error, self.json_roto = datos, error, json_roto

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        if self.json_roto:
            raise ValueError("Expecting ',' delimiter: line 1 column 4096 (char 4095)")
        return self.datos


class SesionFalsa:
    """Responde a cada espejo con lo que se le configure: {endpoint: JSON, excepción, función(consulta) -> JSON, o una LISTA
    de ellos que se va consumiendo en cada llamada (la última se repite)}."""

    def __init__(self, respuestas):
        self.respuestas, self.llamadas, self.timeouts = respuestas, [], []

    def post(self, endpoint, data=None, timeout=None):
        self.llamadas.append((endpoint, data["data"]))
        self.timeouts.append(timeout)
        r = self.respuestas[endpoint]
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        if callable(r):
            r = r(data["data"])
        if isinstance(r, CuerpoTruncado):
            return Respuesta(None, json_roto=True)
        return Respuesta(None, r) if isinstance(r, Exception) else Respuesta(r)


class ClienteFalso:
    def __init__(self, respuestas):
        self.endpoints = list(respuestas)
        self.session = SesionFalsa(respuestas)

    def canarios(self, endpoint=None):
        """Cuántas veces se pidió el canario (`out center meta`), a un espejo o a todos."""
        return sum(1 for e, q in self.session.llamadas if "meta" in q and endpoint in (None, e))

    def consultas_reales(self, endpoint=None):
        return sum(1 for e, q in self.session.llamadas if "meta" not in q and endpoint in (None, e))


def respuesta(n=2, remark=None):
    """Una respuesta de Overpass con `n` elementos; la hora base es SIEMPRE la actual, como en el servidor real."""
    r = {
        "osm3s": {"timestamp_osm_base": HORA_ACTUAL_DEL_SERVIDOR},
        "elements": [{"type": "node", "id": i} for i in range(n)],
    }
    if remark:
        r["remark"] = remark
    return r


def _fecha_de(consulta):
    """La fecha `[date:"..."]` de una consulta."""
    return consulta.split('[date:"')[1].split('"')[0]


def servidor(respeta_fecha=True, n=3, remark=None, atrasado=False):
    """Un espejo de mentira. Ante el canario (`meta`) responde con 30 elementos cuyas versiones dependen de la fecha pedida:
    de unos meses ANTES de la fecha si respeta la fecha; de 2026 si la ignora (mapa actual); de hace 5 años si va atrasado
    (copia antigua de la base). Ante cualquier otra consulta, `n` elementos (con `remark` si se indica)."""

    def responder(consulta):
        if "meta" in consulta:
            fecha = _fecha_de(consulta)
            if not respeta_fecha:
                ts = RECIENTE
            elif atrasado:
                ts = "%04d%s" % (int(fecha[:4]) - 5, fecha[4:])
            else:
                ts = "%04d%s" % (int(fecha[:4]) - 1, "-09-01T10:00:00Z")  # unos meses antes de la fecha
            return {
                "osm3s": {"timestamp_osm_base": HORA_ACTUAL_DEL_SERVIDOR},
                "elements": [{"type": "node", "id": i, "timestamp": ts} for i in range(30)],
            }
        return respuesta(n, remark)

    return responder


FECHA = "2022-01-01T00:00:00Z"


@pytest.fixture(autouse=True)
def sin_pausas_reales(monkeypatch):
    """La pausa tras el canario (12 s) no debe ralentizar los tests; el que comprueba que existe la fija a su valor."""
    monkeypatch.setattr(dh, "PAUSA_S", 0)


# ---- las consultas ------------------------------------------------------------------------------------------------
def test_el_plan_pide_tres_instantes_en_dos_franjas_y_el_ciclo_de_vida_solo_para_hoy():
    """2022, 2024 y hoy, cada uno en 2 franjas (6 consultas), más una de ciclo de vida del estado actual: 7."""
    p = dh.plan()
    assert len(p) == 7
    assert [(n, i) for n, i, _, _ in p] == [
        ("2022-01-01", 0),
        ("2022-01-01", 1),
        ("2024-01-01", 0),
        ("2024-01-01", 1),
        ("hoy", 0),
        ("hoy", 1),
        ("ciclo_de_vida", 0),
    ]


def test_las_consultas_pasadas_llevan_la_fecha_y_las_actuales_no():
    """Solo 2022 y 2024 llevan `[date:...]`; «hoy» y el ciclo de vida piden el estado actual."""
    por_nombre = {(n, i): q for n, i, _, q in dh.plan()}
    assert '[date:"2022-01-01T00:00:00Z"]' in por_nombre[("2022-01-01", 0)]
    assert '[date:"2024-01-01T00:00:00Z"]' in por_nombre[("2024-01-01", 1)]
    assert "[date:" not in por_nombre[("hoy", 0)] and "[date:" not in por_nombre[("ciclo_de_vida", 0)]
    assert all(q.rstrip().endswith("out center tags;") for q in por_nombre.values())


def test_las_clausulas_de_categorias_son_las_mismas_que_las_del_cliente_de_overpass():
    """Si CATEGORY_TAGS o el cliente cambian, este archivo no se queda pidiendo otra cosa que el resto del proyecto."""
    bbox = (35.84, 14.44, 35.94, 14.58)
    del_cliente = OverpassClient._build_query(bbox, CATEGORY_TAGS, 150)
    propias = [c.format(bbox="35.84,14.44,35.94,14.58") for c in dh.clausulas_categorias()]
    assert len(propias) == 20 and all(c in del_cliente for c in propias)


def test_las_siete_categorias_estan_en_la_consulta():
    """Cada etiqueta de cada categoría aparece en la consulta (nada se queda sin pedir)."""
    texto = "\n".join(dh.clausulas_categorias())
    for categoria, specs in CATEGORY_TAGS.items():
        for spec in specs:
            clave = spec.split("=")[0]
            assert f'["{clave}"' in texto, (categoria, spec)


def test_las_clausulas_de_ciclo_de_vida_cubren_cinco_prefijos_por_cinco_claves():
    """`disused:`, `was:`, `abandoned:`, `demolished:` y `razed:` sobre amenity, shop, office, leisure y tourism."""
    c = dh.clausulas_ciclo_de_vida()
    assert len(c) == 25 and 'nwr["disused:amenity"]({bbox});' in c and 'nwr["razed:tourism"]({bbox});' in c


def test_las_franjas_cubren_toda_el_area_sin_huecos_ni_solapes():
    """Las franjas de latitud son contiguas y suman toda la rejilla."""
    f = dh.bbox_franjas(2)
    assert f[0][0] == dh.grid.SOUTH and f[-1][2] == dh.grid.NORTH and f[0][2] == f[1][0]
    with pytest.raises(ValueError):
        dh.bbox_franjas(0)


# ---- la fecha de Overpass: el canario -----------------------------------------------------------------------------
FECHA_2024 = "2024-01-01T00:00:00Z"


def _canario(timestamps):
    return {"elements": [{"type": "node", "id": i, "timestamp": t} for i, t in enumerate(timestamps)]}


def test_la_consulta_del_canario_lleva_la_fecha_que_se_va_a_pedir_y_pide_meta():
    """El canario es una consulta pequeña en LA FECHA PEDIDA con `out center meta` (para ver el `timestamp` de cada
    elemento); hay uno por fecha, no uno fijo."""
    for fecha in (FECHA, FECHA_2024):
        q = dh.consulta_canario(fecha)
        assert f'[date:"{fecha}"]' in q and q.rstrip().endswith("out center meta;")
    s, w, n, e = dh.CANARIO_BBOX
    assert f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}" in dh.consulta_canario(FECHA)


def test_el_canario_acepta_un_espejo_que_respeta_la_fecha():
    """Todas las versiones son anteriores a la fecha y alguna es de los 2 años previos: es un estado de esa fecha."""
    assert dh.canario_respeta_la_fecha(_canario([ANTIGUO] * 30), FECHA) is None


def test_el_canario_acepta_una_version_justo_en_la_fecha():
    """El límite superior es inclusivo: una versión con la fecha exacta no es posterior."""
    assert dh.canario_respeta_la_fecha(_canario([ANTIGUO] * 29 + [FECHA]), FECHA) is None


def test_el_canario_rechaza_un_espejo_que_ignora_la_fecha():
    """Con el mapa actual hay versiones recientes: se rechaza y el motivo dice cuántas y la más reciente."""
    motivo = dh.canario_respeta_la_fecha(_canario([ANTIGUO] * 20 + [RECIENTE] * 10), FECHA)
    assert "ignoró la fecha" in motivo and "10 de 30" in motivo and RECIENTE in motivo


def test_una_sola_version_posterior_basta_para_rechazar():
    """Aunque casi todo sea antiguo, una versión posterior a la fecha delata un mapa que no es de esa fecha."""
    assert "ignoró la fecha" in dh.canario_respeta_la_fecha(_canario([ANTIGUO] * 29 + ["2022-01-01T00:00:01Z"]), FECHA)


def test_el_canario_rechaza_un_espejo_con_una_copia_antigua_de_la_base():
    """COTA INFERIOR: un espejo atrasado (última versión de hace 5 años) pasaría la cota superior para una fecha reciente
    y serviría datos viejos como si fueran de 2024 u hoy. Se detecta porque no hay ninguna versión de los 2 años previos.
    """
    motivo = dh.canario_respeta_la_fecha(_canario(["2018-05-01T00:00:00Z"] * 30), FECHA_2024)
    assert "va atrasado" in motivo and "730 días" in motivo and "2018-05-01" in motivo


def test_la_cota_inferior_del_canario_es_inclusiva_en_el_borde_de_la_ventana():
    """Una versión justo 730 días antes de la fecha cuenta como «reciente»; un segundo antes, no."""
    from datetime import datetime, timedelta

    borde = (datetime.strptime(FECHA_2024, dh.FORMATO_FECHA) - timedelta(days=dh.CANARIO_VENTANA_DIAS)).strftime(
        dh.FORMATO_FECHA
    )
    assert dh.canario_respeta_la_fecha(_canario(["2010-01-01T00:00:00Z"] * 29 + [borde]), FECHA_2024) is None
    fuera = (datetime.strptime(borde, dh.FORMATO_FECHA) - timedelta(seconds=1)).strftime(dh.FORMATO_FECHA)
    assert "va atrasado" in dh.canario_respeta_la_fecha(_canario([fuera] * 30), FECHA_2024)


def test_el_canario_exige_un_minimo_de_elementos_y_lo_trata_como_pasajero():
    """Una respuesta vacía o recortada no se da por buena (no hay nada que comprobar), pero NO es un motivo definitivo:
    lanza una excepción, que no se recuerda y se puede reintentar."""
    with pytest.raises(ValueError, match="solo 5 elementos"):
        dh.canario_respeta_la_fecha(_canario([ANTIGUO] * 5), FECHA)
    with pytest.raises(ValueError, match="solo 0 elementos"):
        dh.canario_respeta_la_fecha(_canario([]), FECHA)


@pytest.mark.parametrize("sin_marca", [30, 1])
def test_elementos_sin_timestamp_en_el_canario_son_un_problema_pasajero_no_definitivo(sin_marca):
    """Sin `timestamp` no se puede comprobar la fecha: no se acepta, pero tampoco se prueba que el espejo ignore la fecha
    (puede ser una respuesta defectuosa, no solo que no admita `meta`): lanza una excepción en vez de un motivo definitivo,
    tanto si faltan en todos los elementos como si falta solo en uno."""
    elementos = [{"type": "node", "id": i, "timestamp": ANTIGUO} for i in range(30)]
    for e in elementos[:sin_marca]:
        del e["timestamp"]
    with pytest.raises(ValueError, match=f"{sin_marca} de 30 elementos del canario no traen un `timestamp` ISO válido"):
        dh.canario_respeta_la_fecha({"elements": elementos}, FECHA)


def test_un_canario_sin_timestamp_no_descarta_el_espejo_y_la_ronda_siguiente_lo_recupera():
    """A nivel de `pedir`: un espejo que contesta una vez sin `timestamp` (respuesta defectuosa) y luego bien NO queda
    marcado de por vida; se reintenta en la ronda siguiente y se usa."""

    def sin_timestamp(consulta):
        return {"osm3s": {}, "elements": [{"type": "node", "id": i} for i in range(30)]}

    cliente = ClienteFalso({"https://a": [sin_timestamp, servidor(n=4)]})
    verificados, esperas = {}, []
    datos, espejo = dh.pedir(cliente, "q", FECHA, rondas=3, espera_s=90, dormir=esperas.append, verificados=verificados)
    assert espejo == "https://a" and len(datos["elements"]) == 4
    assert verificados == {("https://a", FECHA): None} and esperas == [90]


def test_un_espejo_que_nunca_admite_meta_falla_a_la_vista_tras_agotar_las_rondas():
    """Un espejo que de verdad no admite `meta` nunca pasa el canario: no se le piden datos y el error final lo dice."""

    def sin_timestamp(consulta):
        return {"osm3s": {}, "elements": [{"type": "node", "id": i} for i in range(30)]}

    cliente = ClienteFalso({"https://a": sin_timestamp})
    with pytest.raises(RuntimeError, match="no traen un `timestamp` ISO válido"):
        dh.pedir(cliente, "q", FECHA, rondas=2, espera_s=0, dormir=lambda s: None)
    assert cliente.consultas_reales() == 0 and cliente.canarios() == 2


def test_el_canario_con_remark_de_error_es_un_problema_pasajero():
    """Un error de Overpass con HTTP 200 (servidor saturado) no es un canario válido, pero tampoco prueba que el espejo
    ignore la fecha: lanza una excepción en vez de devolver un motivo definitivo."""
    r = _canario([ANTIGUO] * 30)
    r["remark"] = "runtime error: out of memory"
    with pytest.raises(ValueError, match="avisa de un error"):
        dh.canario_respeta_la_fecha(r, FECHA)


def test_la_hora_base_del_servidor_es_la_actual_y_aun_asi_una_respuesta_historica_valida_se_acepta():
    """REGRESIÓN del hallazgo real: overpass-api.de pone la hora ACTUAL en `osm3s.timestamp_osm_base` aunque los datos
    sean de 2022. La versión anterior de la herramienta comparaba esa hora con la fecha pedida y habría rechazado TODAS las
    respuestas históricas válidas."""
    cliente = ClienteFalso({"https://a": servidor(respeta_fecha=True, n=4)})
    datos, espejo = dh.pedir(cliente, "consulta", FECHA, espera_s=0)
    assert espejo == "https://a" and len(datos["elements"]) == 4
    assert datos["osm3s"]["timestamp_osm_base"] > FECHA  # la hora base es posterior y no importa


def test_un_espejo_que_ignora_la_fecha_se_rechaza_y_se_prueba_el_siguiente():
    """El primer espejo devuelve el mapa actual para una consulta de 2022: se descarta tras el canario y se usa el
    segundo. Al espejo malo no se le pide ningún dato real."""
    cliente = ClienteFalso({"https://malo": servidor(respeta_fecha=False), "https://bueno": servidor(n=3)})
    datos, espejo = dh.pedir(cliente, "consulta", FECHA, espera_s=0)
    assert espejo == "https://bueno" and len(datos["elements"]) == 3
    assert cliente.canarios("https://malo") == 1 and cliente.consultas_reales("https://malo") == 0


def test_si_todos_los_espejos_ignoran_la_fecha_falla_en_vez_de_devolver_el_presente():
    """Nunca se devuelve en silencio el mapa actual como si fuera el de 2022."""
    cliente = ClienteFalso({"https://a": servidor(respeta_fecha=False), "https://b": servidor(respeta_fecha=False)})
    with pytest.raises(RuntimeError, match="ignoró la fecha"):
        dh.pedir(cliente, "consulta", FECHA, espera_s=0)
    assert cliente.consultas_reales() == 0


def test_el_canario_se_pide_una_sola_vez_por_espejo_y_se_recuerda():
    """Con el mismo diccionario de verificados, varias consultas al mismo espejo solo gastan un canario."""
    cliente = ClienteFalso({"https://a": servidor()})
    verificados = {}
    for _ in range(3):
        dh.pedir(cliente, "consulta", FECHA, espera_s=0, verificados=verificados)
    assert cliente.canarios() == 1 and cliente.consultas_reales() == 3 and verificados == {("https://a", FECHA): None}


def test_un_espejo_marcado_como_que_ignora_la_fecha_no_se_vuelve_a_consultar():
    """Tras fallar el canario por ignorar la fecha, el espejo queda descartado: no se repite el canario en cada consulta."""
    cliente = ClienteFalso({"https://malo": servidor(respeta_fecha=False), "https://bueno": servidor()})
    verificados = {}
    for _ in range(3):
        dh.pedir(cliente, "consulta", FECHA, espera_s=0, verificados=verificados)
    assert cliente.canarios("https://malo") == 1 and "ignoró la fecha" in verificados[("https://malo", FECHA)]


def test_si_falla_la_red_en_el_canario_el_espejo_no_queda_marcado_y_se_puede_reintentar():
    """Un error de red durante el canario no es «ignora la fecha»: se reintenta en la ronda siguiente y entonces se acepta."""
    cliente = ClienteFalso({"https://a": [OSError("sin capacidad"), servidor()]})
    verificados = {}
    datos, espejo = dh.pedir(cliente, "q", FECHA, rondas=2, espera_s=0, dormir=lambda s: None, verificados=verificados)
    assert espejo == "https://a" and verificados == {("https://a", FECHA): None}


def _canario_saturado(consulta):
    """Un servidor saturado que contesta al canario con HTTP 200 y un `remark` de tiempo agotado."""
    return {
        "osm3s": {},
        "elements": [],
        "remark": 'runtime error: Query timed out in "query" at line 3 after 151 seconds.',
    }


def _canario_recortado(consulta):
    """Un servidor que contesta al canario con solo 5 elementos (respuesta recortada)."""
    return {"osm3s": {}, "elements": [{"type": "node", "id": i, "timestamp": ANTIGUO} for i in range(5)]}


@pytest.mark.parametrize("canario_pasajero", [_canario_saturado, _canario_recortado])
def test_un_canario_pasajero_no_descarta_el_espejo_y_la_ronda_siguiente_lo_recupera(canario_pasajero):
    """El único espejo con historia está saturado justo en el canario (remark o respuesta recortada) y responde bien en la
    ronda 2: no se le debe marcar como «ignora la fecha» de por vida. Es el caso que las rondas existen para cubrir."""
    cliente = ClienteFalso({"https://a": [canario_pasajero, servidor(n=6)]})
    verificados, esperas = {}, []
    datos, espejo = dh.pedir(cliente, "q", FECHA, rondas=3, espera_s=90, dormir=esperas.append, verificados=verificados)
    assert espejo == "https://a" and len(datos["elements"]) == 6
    assert verificados == {("https://a", FECHA): None} and esperas == [90]


def test_un_canario_pasajero_no_deja_marcado_el_espejo_mientras_dure_el_fallo():
    """Mientras el canario siga fallando de forma pasajera, `verificados` queda vacío (nada se recuerda)."""
    cliente = ClienteFalso({"https://a": _canario_saturado})
    verificados = {}
    with pytest.raises(RuntimeError, match="avisa de un error"):
        dh.pedir(cliente, "q", FECHA, rondas=2, espera_s=0, dormir=lambda s: None, verificados=verificados)
    assert verificados == {} and cliente.canarios() == 2 and cliente.consultas_reales() == 0


def test_tras_un_canario_nuevo_se_hace_una_pausa_y_con_el_espejo_ya_verificado_no(monkeypatch):
    """El canario es una petición más: se espera `PAUSA_S` antes de la consulta pesada, una sola vez por espejo."""
    monkeypatch.setattr(dh, "PAUSA_S", 5)
    cliente = ClienteFalso({"https://a": servidor()})
    verificados, pausas = {}, []
    for _ in range(3):
        dh.pedir(cliente, "q", FECHA, espera_s=0, dormir=pausas.append, verificados=verificados)
    assert pausas == [5]


def test_hay_un_canario_por_cada_fecha_que_se_pide_y_se_recuerda_por_separado():
    """Pedir 2022 y 2024 al mismo espejo gasta DOS canarios (uno por fecha), y cada uno se recuerda aparte; con la misma
    fecha varias veces solo se gasta uno."""
    cliente = ClienteFalso({"https://a": servidor()})
    verificados = {}
    for fecha in (FECHA, FECHA_2024, FECHA, FECHA_2024):
        dh.pedir(cliente, "q", fecha, espera_s=0, verificados=verificados)
    assert cliente.canarios() == 2 and cliente.consultas_reales() == 4
    assert verificados == {("https://a", FECHA): None, ("https://a", FECHA_2024): None}
    fechas_de_los_canarios = [_fecha_de(q) for _, q in cliente.session.llamadas if "meta" in q]
    assert fechas_de_los_canarios == [FECHA, FECHA_2024]


def test_un_espejo_atrasado_se_rechaza_para_2024_aunque_hubiera_pasado_el_canario_de_2022():
    """Un espejo con una copia vieja pasa el canario de 2022 pero no el de 2024: no se le piden los datos de 2024."""

    def solo_hasta_2022(consulta):
        # respeta 2022 (versiones de 2021) y, para 2024, sigue devolviendo lo mismo: sin versiones de 2022-2023
        if "meta" in consulta:
            return {"osm3s": {}, "elements": [{"type": "node", "id": i, "timestamp": ANTIGUO} for i in range(30)]}
        return respuesta(5)

    cliente = ClienteFalso({"https://viejo": solo_hasta_2022})
    verificados = {}
    datos, _ = dh.pedir(cliente, "q", FECHA, espera_s=0, verificados=verificados)  # 2022: bien
    assert len(datos["elements"]) == 5
    with pytest.raises(RuntimeError, match="va atrasado"):
        dh.pedir(cliente, "q", FECHA_2024, rondas=1, espera_s=0, verificados=verificados)
    assert verificados[("https://viejo", FECHA)] is None and "va atrasado" in verificados[("https://viejo", FECHA_2024)]
    assert cliente.consultas_reales() == 1  # los datos de 2024 nunca se le pidieron


def test_el_resumen_final_no_falla_con_un_manifiesto_de_la_version_anterior(monkeypatch, tmp_path, capsys):
    """Un `manifest.json` heredado con la clave antigua `osm_base` (sin `osm_base_servidor`) no hace reventar el resumen."""
    manifiesto = {
        "archivos": {
            "hoy_0.json": {"elementos": 7, "osm_base": "2026-11-13T21:00:00Z", "espejo": "https://x"},
            "2022-01-01_0.json": {"elementos": 9, "osm_base_servidor": "2026-11-13T21:01:00Z", "espejo": "https://x"},
        },
        "fallidos": [],
    }
    monkeypatch.setattr(dh, "OverpassClient", lambda **kw: object())
    monkeypatch.setattr(dh, "descargar", lambda *a, **kw: manifiesto)
    assert dh.main(["--out", str(tmp_path)]) == 0
    salida = capsys.readouterr().out
    assert "2026-11-13T21:00:00Z" in salida and "2026-11-13T21:01:00Z" in salida


def test_una_consulta_actual_no_pide_canario():
    """Para «hoy» (sin fecha) no hay nada que comprobar: no se gasta una consulta de canario."""
    cliente = ClienteFalso({"https://a": servidor()})
    dh.pedir(cliente, "q", None, espera_s=0)
    assert cliente.canarios() == 0 and cliente.consultas_reales() == 1


def test_un_error_de_red_en_un_espejo_pasa_al_siguiente():
    """Un fallo HTTP no detiene la descarga mientras otro espejo responda."""
    cliente = ClienteFalso({"https://a": OSError("sin red"), "https://b": servidor()})
    assert dh.pedir(cliente, "q", FECHA)[1] == "https://b"


# ---- la descarga y su manifiesto ---------------------------------------------------------------------------------
def test_descargar_escribe_los_json_y_un_manifiesto_con_hora_del_servidor_y_hash(tmp_path):
    """Cada trozo queda en su archivo; el manifiesto guarda recuento, sha256 y la hora del servidor solo como informativa."""
    cliente = ClienteFalso({"https://x": servidor(n=4)})
    m = dh.descargar(cliente, tmp_path, ["2022-01-01"], pausa_s=0, log=lambda *_: None)
    assert m["fallidos"] == [] and sorted(m["archivos"]) == ["2022-01-01_0.json", "2022-01-01_1.json"]
    a = m["archivos"]["2022-01-01_0.json"]
    contenido = json.loads((tmp_path / "2022-01-01_0.json").read_text(encoding="utf-8"))
    assert a["elementos"] == 4 and a["sha256"] == dh.sha256_de(tmp_path / "2022-01-01_0.json")
    assert a["osm_base_servidor"] == HORA_ACTUAL_DEL_SERVIDOR and "osm_base" not in a  # informativa, no valida nada
    assert contenido["instante"] == "2022-01-01" and contenido["osm_base_servidor"] == HORA_ACTUAL_DEL_SERVIDOR
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["descargado_utc"].endswith("Z")


def test_descargar_pide_un_canario_por_espejo_y_por_fecha_en_toda_la_descarga(tmp_path):
    """Con 2022 y 2024 (4 consultas fechadas) hay 2 canarios (uno por fecha) y 4 consultas reales, no uno por consulta."""
    cliente = ClienteFalso({"https://x": servidor()})
    dh.descargar(cliente, tmp_path, ["2022-01-01", "2024-01-01"], pausa_s=0, log=lambda *_: None)
    assert cliente.canarios() == 2 and cliente.consultas_reales() == 4


def test_un_trozo_que_falla_se_anota_y_los_demas_siguen(tmp_path):
    """Si ningún espejo respeta la fecha, esos trozos quedan en `fallidos` y no se escribe su archivo."""
    cliente = ClienteFalso({"https://x": servidor(respeta_fecha=False)})
    m = dh.descargar(cliente, tmp_path, ["2022-01-01"], pausa_s=0, log=lambda *_: None, espera_s=0)
    assert len(m["fallidos"]) == 2 and m["archivos"] == {}
    assert "ignoró la fecha" in m["fallidos"][0]["error"]
    assert not (tmp_path / "2022-01-01_0.json").exists()


def test_descargar_solo_escribe_dentro_del_directorio_de_salida(tmp_path):
    """No toca nada fuera de `out_dir` (ni la base de datos)."""
    salida = tmp_path / "out"
    dh.descargar(ClienteFalso({"https://x": servidor()}), salida, ["2022-01-01"], pausa_s=0, log=lambda *_: None)
    assert {p.name for p in tmp_path.iterdir()} == {"out"}


def test_el_dry_run_no_hace_ninguna_llamada_de_red(monkeypatch, capsys):
    """`--dry-run` imprime las consultas y no crea ni usa el cliente de Overpass."""

    def prohibido(*args, **kwargs):
        raise AssertionError("el dry-run no debe crear el cliente de red")

    monkeypatch.setattr(dh, "OverpassClient", prohibido)
    assert dh.main(["--dry-run"]) == 0
    salida = capsys.readouterr().out
    assert "consultas a pedir: 7" in salida and '[date:"2022-01-01T00:00:00Z"]' in salida and "dry-run" in salida


def test_los_datos_descargados_estan_ignorados_por_git():
    """El estado histórico se regenera y no se versiona: `data/osm_history/` está en .gitignore."""
    assert "data/osm_history/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


# ---- servicios públicos saturados: rondas, motivo de cada espejo y timeout de conexión -------------------------------
def test_si_todos_fallan_en_la_primera_ronda_se_espera_y_se_reintenta():
    """Los espejos públicos se saturan y se recuperan: tras una ronda en la que todos fallan se espera y se vuelve a
    empezar; aquí el primero está «al límite de capacidad» en la ronda 1 y responde en la 2."""
    cliente = ClienteFalso({"https://a": [OSError("502 al límite de capacidad"), servidor(n=5)]})
    esperas = []
    datos, espejo = dh.pedir(cliente, "q", FECHA, rondas=3, espera_s=90, dormir=esperas.append)
    assert len(datos["elements"]) == 5 and espejo == "https://a"
    assert esperas == [90]  # una sola espera, entre la ronda 1 y la 2


def test_se_rinde_tras_las_rondas_indicadas_y_solo_espera_entre_ellas():
    """Con 3 rondas fallidas hay 2 esperas (no una tras la última) y 3 intentos por espejo."""
    cliente = ClienteFalso({"https://a": OSError("sin red")})
    esperas = []
    with pytest.raises(RuntimeError, match="3 rondas"):
        dh.pedir(cliente, "q", None, rondas=3, espera_s=7, dormir=esperas.append)
    assert esperas == [7, 7] and len(cliente.session.llamadas) == 3


def test_el_error_final_dice_por_que_fallo_cada_espejo():
    """Antes solo se veía el motivo del ÚLTIMO espejo y se ocultaba el de los demás."""
    cliente = ClienteFalso({"https://a": OSError("502 sin capacidad"), "https://b": ValueError("respuesta inválida")})
    with pytest.raises(RuntimeError) as e:
        dh.pedir(cliente, "q", None, rondas=1, espera_s=0)
    texto = str(e.value)
    assert "https://a -> OSError: 502 sin capacidad" in texto and "https://b -> ValueError: respuesta inválida" in texto


def test_el_timeout_de_conexion_es_corto_y_el_de_lectura_largo_tambien_en_el_canario():
    """Un espejo que no conecta se salta en segundos; solo la lectura (la consulta pesada) puede tardar. Vale para la
    consulta real y para el canario."""
    cliente = ClienteFalso({"https://a": servidor()})
    dh.pedir(cliente, "q", FECHA)
    assert len(cliente.session.timeouts) == 2  # canario + consulta
    for conexion, lectura in cliente.session.timeouts:
        assert conexion <= 20 and lectura >= 150


def test_descargar_respeta_las_rondas_y_la_espera_que_se_le_indican(tmp_path, monkeypatch):
    """`descargar` pasa `rondas` y `espera_s` a `pedir`: con 2 rondas y un espejo caído hay 2 intentos por trozo (4 en
    total para los 2 trozos de 2022) y una espera de 5 s por trozo, entre la ronda 1 y la 2."""
    esperas = []
    monkeypatch.setattr(dh.time, "sleep", esperas.append)
    cliente = ClienteFalso({"https://x": OSError("sin capacidad")})
    m = dh.descargar(cliente, tmp_path, ["2022-01-01"], pausa_s=0, log=lambda *_: None, rondas=2, espera_s=5)
    assert len(cliente.session.llamadas) == 4 and esperas.count(5) == 2 and len(m["fallidos"]) == 2
    assert (
        "2 rondas" in m["fallidos"][0]["error"] and "https://x -> OSError: sin capacidad" in m["fallidos"][0]["error"]
    )


# ---- respuestas con HTTP 200 que en realidad son un error de Overpass ------------------------------------------------
ERROR_DE_TIEMPO = 'runtime error: Query timed out in "query" at line 3 after 151 seconds.'


def test_una_respuesta_http_200_con_remark_de_error_no_se_da_por_buena():
    """Si Overpass se queda sin tiempo o memoria responde 200 con `remark` y `elements` vacío o parcial. Guardarlo como
    éxito daría un 2022 vacío, que parecería una ola de cierres: se descarta y se prueba otro espejo."""
    cliente = ClienteFalso({"https://a": servidor(remark=ERROR_DE_TIEMPO), "https://b": servidor(n=3)})
    datos, espejo = dh.pedir(cliente, "q", FECHA, rondas=1, espera_s=0)
    assert espejo == "https://b" and len(datos["elements"]) == 3


def test_si_todos_los_espejos_devuelven_un_error_de_overpass_no_se_escribe_nada(tmp_path):
    """El trozo queda en `fallidos` con el motivo y no se crea su archivo (ni un JSON vacío que parezca bueno)."""
    cliente = ClienteFalso({"https://a": servidor(remark=ERROR_DE_TIEMPO)})
    m = dh.descargar(cliente, tmp_path, ["2022-01-01"], pausa_s=0, log=lambda *_: None, rondas=1, espera_s=0)
    assert m["archivos"] == {} and len(m["fallidos"]) == 2
    assert "Overpass avisa de un error en la consulta" in m["fallidos"][0]["error"]
    assert not list(tmp_path.glob("2022-01-01_*.json"))


@pytest.mark.parametrize(
    "datos, motivo",
    [
        ({"osm3s": {}, "remark": "runtime error: out of memory", "elements": []}, "avisa de un error"),
        ({"osm3s": {}}, "elements"),  # falta la lista
        ({"osm3s": {}, "elements": None}, "elements"),  # no es una lista
        ({"osm3s": {}, "elements": {"a": 1}}, "elements"),
        ([1, 2, 3], "objeto JSON"),
    ],
)
def test_respuesta_valida_rechaza_lo_que_no_es_una_respuesta_completa(datos, motivo):
    """Un `remark`, un `elements` ausente o que no es una lista, o un JSON que no es un objeto, son fallos visibles."""
    assert motivo in dh.respuesta_valida(datos)


def test_una_respuesta_correcta_sin_elementos_si_es_valida():
    """Una lista `elements` vacía sin `remark` es una respuesta legítima (un trozo sin locales), no un error."""
    assert dh.respuesta_valida({"osm3s": {}, "elements": []}) is None


# ---- el manifiesto se fusiona al relanzar -----------------------------------------------------------------------------
def _descargar(tmp_path, instantes, cliente=None, **kw):
    cliente = cliente or ClienteFalso({"https://x": servidor()})
    return dh.descargar(cliente, tmp_path, instantes, pausa_s=0, log=lambda *_: None, espera_s=0, **kw)


def test_relanzar_un_subconjunto_no_borra_lo_ya_descargado_del_manifiesto(tmp_path):
    """Tras bajar 2022 y luego solo 2024, el manifiesto trae los cuatro archivos con su hash y su fecha de descarga."""
    _descargar(tmp_path, ["2022-01-01"])
    m = _descargar(tmp_path, ["2024-01-01"])
    assert sorted(m["archivos"]) == ["2022-01-01_0.json", "2022-01-01_1.json", "2024-01-01_0.json", "2024-01-01_1.json"]
    escrito = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert sorted(escrito["archivos"]) == sorted(m["archivos"])
    assert all(d["sha256"] and d["osm_base_servidor"] and d["descargado_utc"] for d in escrito["archivos"].values())


def test_si_el_reintento_de_un_trozo_falla_se_conserva_el_archivo_anterior_y_se_avisa(tmp_path):
    """El JSON de la ejecución anterior sigue siendo válido: se mantiene en el manifiesto, y el fallo queda anotado con
    que se conserva el anterior (no queda un archivo en disco sin registrar)."""
    _descargar(tmp_path, ["2022-01-01"])
    caido = ClienteFalso({"https://x": OSError("sin capacidad")})
    m = _descargar(tmp_path, ["2022-01-01"], caido, rondas=1)
    assert sorted(m["archivos"]) == ["2022-01-01_0.json", "2022-01-01_1.json"]
    assert [f["se_conserva_el_de_una_ejecucion_anterior"] for f in m["fallidos"]] == [True, True]
    assert (tmp_path / "2022-01-01_0.json").exists()


def test_el_manifiesto_se_ignora_si_el_anterior_esta_roto_o_apunta_a_archivos_borrados(tmp_path):
    """Un manifiesto ilegible no impide descargar, y no se heredan entradas de archivos que ya no existen."""
    (tmp_path / "manifest.json").write_text("{ no es json", encoding="utf-8")
    assert sorted(_descargar(tmp_path, ["2022-01-01"])["archivos"]) == ["2022-01-01_0.json", "2022-01-01_1.json"]
    (tmp_path / "2022-01-01_0.json").unlink()
    m = _descargar(tmp_path, ["2024-01-01"])
    assert "2022-01-01_0.json" not in m["archivos"] and "2022-01-01_1.json" in m["archivos"]


# ---- cuerpo cortado a la mitad (HTTP 200 pero JSON incompleto) -------------------------------------------------------
def test_un_cuerpo_json_cortado_a_la_mitad_es_un_fallo_y_se_prueba_otro_espejo():
    """Un corte de red deja el JSON a medias y `r.json()` falla: es un fallo del espejo, no una respuesta parcial que se
    guarde. (Es la forma realista de «respuesta truncada»; con un `remark` o sin `elements` ya se rechazaba.)"""
    cliente = ClienteFalso({"https://a": CuerpoTruncado(), "https://b": servidor(n=3)})
    datos, espejo = dh.pedir(cliente, "q", None, rondas=1, espera_s=0)
    assert espejo == "https://b" and len(datos["elements"]) == 3


def test_si_el_cuerpo_llega_cortado_en_todos_los_espejos_no_se_escribe_nada(tmp_path):
    """El trozo queda en `fallidos` con el motivo y no se crea su archivo (nunca un JSON a medias o vacío)."""
    cliente = ClienteFalso({"https://a": [servidor(), CuerpoTruncado()]})
    m = dh.descargar(cliente, tmp_path, ["hoy"], pausa_s=0, log=lambda *_: None, rondas=1, espera_s=0)
    # «hoy» son 3 trozos (2 franjas y el ciclo de vida): el primero llega entero y los otros dos, cortados
    assert sorted(m["archivos"]) == ["hoy_0.json"]
    assert [f["archivo"] for f in m["fallidos"]] == ["hoy_1.json", "ciclo_de_vida_0.json"]
    assert all("ValueError" in f["error"] for f in m["fallidos"])
    assert not (tmp_path / "hoy_1.json").exists() and not (tmp_path / "ciclo_de_vida_0.json").exists()


# ---- timestamps malformados: pasajeros, no definitivos --------------------------------------------------------------
@pytest.mark.parametrize(
    "marca",
    [
        "hace dos años",  # texto cualquiera
        "2021-06-01 10:00:00",  # sin T ni Z
        "2021-06-01T10:00:00",  # sin Z
        "2021-06-01T10:00:00.123Z",  # con milisegundos (no es el formato de Overpass)
        "2021-13-45T99:99:99Z",  # con la forma pero no es una fecha real
        "2021-6-1T10:0:0Z",  # `strptime` la acepta, pero sin ceros no se ordena bien como texto
        "",
        None,
        20210601,
    ],
)
def test_un_timestamp_malformado_en_el_canario_es_un_problema_pasajero(marca):
    """Comparar como texto un valor que no es una fecha ISO válida daría un veredicto sin sentido (aceptar o rechazar un
    espejo por una cadena rara): se trata como respuesta defectuosa, pasajera, igual que la falta de `timestamp`."""
    elementos = [{"type": "node", "id": i, "timestamp": ANTIGUO} for i in range(29)] + [
        {"type": "node", "id": 99, "timestamp": marca}
    ]
    with pytest.raises(ValueError, match="1 de 30 elementos del canario no traen un `timestamp` ISO válido"):
        dh.canario_respeta_la_fecha({"elements": elementos}, FECHA)


def test_un_timestamp_malformado_no_descarta_el_espejo_y_la_ronda_siguiente_lo_recupera():
    """A nivel de `pedir`: una respuesta defectuosa con un timestamp raro no deja marcado el espejo; la ronda siguiente
    (con el canario bien) lo acepta."""

    def con_marca_rara(consulta):
        return {
            "osm3s": {},
            "elements": [{"type": "node", "id": i, "timestamp": "no es una fecha"} for i in range(30)],
        }

    cliente = ClienteFalso({"https://a": [con_marca_rara, servidor(n=2)]})
    verificados, esperas = {}, []
    datos, espejo = dh.pedir(cliente, "q", FECHA, rondas=3, espera_s=90, dormir=esperas.append, verificados=verificados)
    assert espejo == "https://a" and len(datos["elements"]) == 2
    assert verificados == {("https://a", FECHA): None} and esperas == [90]


def test_una_marca_valida_se_acepta_y_una_inventada_con_la_forma_correcta_no():
    """`_marca_valida` exige una fecha real, no solo el aspecto `AAAA-MM-DDThh:mm:ssZ`."""
    assert dh._marca_valida("2021-12-28T07:25:11Z") and not dh._marca_valida("2021-02-30T07:25:11Z")


# ---- elementos que no son objetos ------------------------------------------------------------------------------------
def test_elements_con_algo_que_no_es_un_objeto_es_una_respuesta_invalida():
    """Si `elements` trae números o cadenas en vez de objetos no se puede guardar ni interpretar: fallo visible."""
    assert "no es un objeto" in dh.respuesta_valida({"osm3s": {}, "elements": [{"type": "node", "id": 1}, 7]})
    assert dh.respuesta_valida({"osm3s": {}, "elements": [{"type": "node", "id": 1}]}) is None


# ---- privacidad: lista blanca de campos al escribir ------------------------------------------------------------------
CON_METADATOS = {
    "osm3s": {"timestamp_osm_base": HORA_ACTUAL_DEL_SERVIDOR},
    "elements": [
        {
            "type": "node",
            "id": 7,
            "lat": 35.9,
            "lon": 14.5,
            "tags": {"amenity": "cafe", "name": "Café Prueba"},
            "version": 3,
            "timestamp": "2021-06-01T10:00:00Z",
            "changeset": 123456,
            "uid": 424242,
            "user": "colaborador_secreto",
        },
        {
            "type": "way",
            "id": 8,
            "center": {"lat": 35.91, "lon": 14.51},
            "tags": {"amenity": "bar"},
            "user": "otro_colaborador",
            "uid": 99,
        },
    ],
}


def test_limpiar_elemento_conserva_solo_los_campos_de_la_lista_blanca():
    """Se quedan tipo, id, posición y etiquetas; se van versión, fecha, conjunto de cambios, uid y nombre de usuario."""
    limpio = dh.limpiar_elemento(CON_METADATOS["elements"][0])
    assert limpio == {
        "type": "node",
        "id": 7,
        "lat": 35.9,
        "lon": 14.5,
        "tags": {"amenity": "cafe", "name": "Café Prueba"},
    }
    assert dh.limpiar_elemento(CON_METADATOS["elements"][1]) == {
        "type": "way",
        "id": 8,
        "center": {"lat": 35.91, "lon": 14.51},
        "tags": {"amenity": "bar"},
    }


def test_los_datos_guardados_no_contienen_datos_de_colaboradores_aunque_el_espejo_los_envie(tmp_path, capsys):
    """Aunque un espejo devolviera `user`/`uid` en una respuesta normal, no llegan al JSON del disco, ni al manifiesto, ni
    a lo que se imprime. Es una garantía explícita, no un efecto de usar `out center tags`."""
    cliente = ClienteFalso(
        {"https://x": lambda consulta: CON_METADATOS if "meta" not in consulta else servidor()(consulta)}
    )
    m = dh.descargar(cliente, tmp_path, ["2022-01-01"], pausa_s=0, log=print)
    salida = capsys.readouterr().out
    assert m["fallidos"] == []
    textos = [p.read_text(encoding="utf-8") for p in tmp_path.glob("*.json")] + [salida]
    for texto in textos:
        for prohibido in (
            "colaborador_secreto",
            "otro_colaborador",
            "424242",
            "changeset",
            '"uid"',
            '"user"',
            "version",
        ):
            assert prohibido not in texto, prohibido
    guardado = json.loads((tmp_path / "2022-01-01_0.json").read_text(encoding="utf-8"))
    assert [sorted(e) for e in guardado["elements"]] == [
        ["id", "lat", "lon", "tags", "type"],
        ["center", "id", "tags", "type"],
    ]
    assert m["archivos"]["2022-01-01_0.json"]["elementos"] == 2  # el recuento no cambia por limpiar


def test_el_canario_no_guarda_nada_en_disco(tmp_path):
    """El canario (el único con `out meta`, con usuarios y uid) solo se comprueba en memoria: ningún archivo lo contiene."""
    pedido = {"n": 0}

    def con_usuarios(consulta):
        if "meta" in consulta:
            pedido["n"] += 1
            return {
                "osm3s": {},
                "elements": [
                    {"type": "node", "id": i, "timestamp": ANTIGUO, "user": "colaborador_secreto", "uid": 1}
                    for i in range(30)
                ],
            }
        return respuesta(2)

    dh.descargar(ClienteFalso({"https://x": con_usuarios}), tmp_path, ["2022-01-01"], pausa_s=0, log=lambda *_: None)
    assert pedido["n"] == 1
    assert all("colaborador_secreto" not in p.read_text(encoding="utf-8") for p in tmp_path.iterdir())


# ---- verificación de integridad: el recuento del servidor frente a lo guardado -----------------------------------------
def servidor_con_recuento(total=None, n=4, respeta_fecha=True):
    """Como `servidor`, pero además contesta a `out count;` con el total que se indique (por defecto, `n`: coincide)."""
    base = servidor(respeta_fecha=respeta_fecha, n=n)

    def responder(consulta):
        if "out count;" in consulta:
            t = n if total is None else total
            tags = {"nodes": str(t), "ways": "0", "relations": "0", "total": str(t)}
            return {"osm3s": {}, "elements": [{"type": "count", "id": 0, "tags": tags}]}
        return base(consulta)

    return responder


def _descargado(tmp_path, n=4, instantes=("2022-01-01",)):
    """Descarga con un servidor falso que da `n` elementos por trozo; devuelve el cliente de la descarga."""
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=n)})
    dh.descargar(cliente, tmp_path, list(instantes), pausa_s=0, log=lambda *_: None)
    return cliente


def _verificar(tmp_path, total=None, n=4, instantes=("2022-01-01",), **kw):
    cliente = ClienteFalso({"https://x": servidor_con_recuento(total=total, n=n)})
    return dh.verificar_descarga(cliente, tmp_path, list(instantes), pausa_s=0, log=lambda *_: None, espera_s=0, **kw)


def test_la_consulta_de_recuento_es_la_misma_consulta_pidiendo_solo_cuantos():
    """Mismas cláusulas, misma zona y misma fecha; solo cambia la salida: `out count;` en vez de `out center tags;`."""
    for nombre, franja, fecha, consulta in dh.plan():
        recuento = dh.consulta_de_recuento(consulta)
        assert recuento.rstrip().endswith("out count;") and "out center tags;" not in recuento
        assert recuento.replace("out count;", "out center tags;") == consulta.rstrip()


def test_la_consulta_de_recuento_se_niega_a_convertir_lo_que_no_es_una_consulta_de_datos():
    """Si la consulta no termina en `out center tags;` no se inventa un recuento."""
    with pytest.raises(ValueError, match="out center tags"):
        dh.consulta_de_recuento("[out:json];node(1);out meta;")


@pytest.mark.parametrize(
    "respuesta_mala",
    [
        {"elements": []},
        {"elements": [{"type": "node", "id": 1}]},  # no es un `count`
        {"elements": [{"type": "count", "id": 0, "tags": {"total": "7"}}, {"type": "count", "id": 1, "tags": {}}]},
        {"elements": [{"type": "count", "id": 0}]},  # sin tags
        {"elements": [{"type": "count", "id": 0, "tags": {"total": "muchos"}}]},  # no numérico
    ],
)
def test_total_del_servidor_rechaza_respuestas_que_no_son_un_recuento_valido(respuesta_mala):
    """Un recuento ausente, doble o no numérico no se interpreta: es un error (la verificación queda «sin verificar»)."""
    with pytest.raises(ValueError):
        dh.total_del_servidor(respuesta_mala)


def test_total_del_servidor_lee_el_total_que_declara_overpass():
    assert dh.total_del_servidor({"elements": [{"type": "count", "id": 0, "tags": {"total": "1370"}}]}) == 1370


def test_una_descarga_completa_se_verifica_y_queda_anotado_en_el_manifiesto(tmp_path):
    """Si el recuento del servidor coincide con lo guardado, el archivo es `completo` y el manifiesto lo registra con el
    criterio, las dos cifras y el espejo. Los archivos de datos no se tocan."""
    _descargado(tmp_path, n=4)
    antes = {p.name: dh.sha256_de(p) for p in tmp_path.glob("2022-01-01_*.json")}
    r = _verificar(tmp_path, n=4)
    assert r["ok"] and sorted(r["correctos"]) == ["2022-01-01_0.json", "2022-01-01_1.json"]
    v = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["archivos"]["2022-01-01_0.json"][
        "verificacion"
    ]
    assert v["estado"] == "completo" and v["total_servidor"] == 4 and v["elementos_en_archivo"] == 4
    assert v["criterio"] == "exacto" and v["espejo"] == "https://x" and v["verificado_utc"].endswith("Z")
    assert {p.name: dh.sha256_de(p) for p in tmp_path.glob("2022-01-01_*.json")} == antes  # datos intactos


def test_un_archivo_con_menos_elementos_que_el_servidor_es_incompleto_aunque_su_json_sea_valido(tmp_path):
    """El caso que no se podía detectar de otro modo: una respuesta parcial pero JSON válido y sin `remark`. El servidor
    dice 10 y el archivo tiene 4: INCOMPLETO, `ok` falso, y queda anotado."""
    _descargado(tmp_path, n=4)
    r = _verificar(tmp_path, total=10)
    assert not r["ok"] and len(r["incorrectos"]) == 2 and r["correctos"] == []
    v = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["archivos"]["2022-01-01_0.json"][
        "verificacion"
    ]
    assert v["estado"] == "INCOMPLETO" and v["total_servidor"] == 10 and v["elementos_en_archivo"] == 4


def test_para_un_instante_pasado_la_coincidencia_es_exacta_sin_tolerancia(tmp_path):
    """El pasado no cambia: una diferencia de UN solo elemento ya es un fallo (también por arriba)."""
    _descargado(tmp_path, n=100)
    assert not _verificar(tmp_path, total=101, n=100)["ok"]
    assert not _verificar(tmp_path, total=99, n=100)["ok"]
    assert _verificar(tmp_path, total=100, n=100)["ok"]


def test_para_el_estado_actual_se_admite_una_diferencia_del_uno_por_ciento(tmp_path):
    """«Hoy» cambia cada minuto: 1000 guardados frente a 1005 en el servidor (0,5 %) vale; 1030 (3 %) no."""
    _descargado(tmp_path, n=1000, instantes=("hoy",))
    assert _verificar(tmp_path, total=1005, n=1000, instantes=("hoy",))["ok"]
    r = _verificar(tmp_path, total=1030, n=1000, instantes=("hoy",))
    assert not r["ok"] and r["incorrectos"]
    v = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["archivos"]["hoy_0.json"]["verificacion"]
    assert "tolerancia" in v["criterio"] and v["estado"] == "INCOMPLETO"


def test_un_recuento_ilegible_deja_el_archivo_sin_verificar_y_no_lo_da_por_bueno(tmp_path):
    """Si el servidor no contesta un recuento válido, el archivo queda `sin_verificar` (no `completo`) y `ok` es falso."""
    _descargado(tmp_path, n=4)

    def sin_count(consulta):
        return (
            {"osm3s": {}, "elements": [{"type": "node", "id": 1}]} if "out count;" in consulta else servidor()(consulta)
        )

    cliente = ClienteFalso({"https://x": sin_count})
    r = dh.verificar_descarga(cliente, tmp_path, ["2022-01-01"], pausa_s=0, log=lambda *_: None, rondas=1, espera_s=0)
    assert not r["ok"] and len(r["sin_verificar"]) == 2 and r["correctos"] == []
    v = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["archivos"]["2022-01-01_0.json"][
        "verificacion"
    ]
    assert v["estado"] == "sin_verificar" and "count" in v["error"]


def test_un_archivo_que_falta_se_informa_y_no_se_da_por_verificado(tmp_path):
    """Si algún trozo no está descargado, `ok` es falso aunque los demás estén completos."""
    _descargado(tmp_path, n=4)
    (tmp_path / "2022-01-01_1.json").unlink()
    r = _verificar(tmp_path, n=4)
    assert not r["ok"] and r["sin_archivo"] == ["2022-01-01_1.json"] and r["correctos"] == ["2022-01-01_0.json"]


def test_sin_manifiesto_no_hay_nada_que_verificar(tmp_path):
    """Verificar una carpeta sin descargar da un error claro, no un informe vacío «correcto»."""
    with pytest.raises(FileNotFoundError, match="primero hay que descargar"):
        _verificar(tmp_path)


def test_no_hay_verificacion_correcta_sin_ningun_archivo_verificado(tmp_path):
    """`ok` exige al menos un archivo completo: una verificación que no comprobó nada no puede dar luz verde."""
    (tmp_path / "manifest.json").write_text(json.dumps({"archivos": {}, "fallidos": []}), encoding="utf-8")
    r = _verificar(tmp_path)
    assert not r["ok"] and r["correctos"] == [] and len(r["sin_archivo"]) == 2


def test_el_canario_tambien_protege_la_verificacion_de_los_instantes_pasados(tmp_path):
    """Los recuentos fechados se piden con el mismo control de fecha: un espejo que ignora la fecha no puede 'verificar'."""
    _descargado(tmp_path, n=4)
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=4, respeta_fecha=False)})
    r = dh.verificar_descarga(cliente, tmp_path, ["2022-01-01"], pausa_s=0, log=lambda *_: None, rondas=1, espera_s=0)
    assert not r["ok"] and len(r["sin_verificar"]) == 2
    assert (
        "ignoró la fecha"
        in json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["archivos"]["2022-01-01_0.json"][
            "verificacion"
        ]["error"]
    )


def test_main_con_verificar_no_descarga_y_su_codigo_de_salida_refleja_el_resultado(tmp_path, monkeypatch, capsys):
    """`--verificar` solo verifica (no hace la descarga) y sale con 0 si todo está completo y con 1 si no."""
    _descargado(tmp_path, n=4)
    argumentos = [
        "--verificar",
        "--out",
        str(tmp_path),
        "--instantes",
        "2022-01-01",
        "--pausa",
        "0",
        "--rondas",
        "1",
        "--espera",
        "0",
    ]
    monkeypatch.setattr(dh, "OverpassClient", lambda **kw: ClienteFalso({"https://x": servidor_con_recuento(n=4)}))
    monkeypatch.setattr(dh, "descargar", lambda *a, **k: pytest.fail("--verificar no debe descargar"))
    assert dh.main(argumentos) == 0 and "2 completos, 0 INCOMPLETOS" in capsys.readouterr().out
    monkeypatch.setattr(
        dh, "OverpassClient", lambda **kw: ClienteFalso({"https://x": servidor_con_recuento(total=9, n=4)})
    )
    assert dh.main(argumentos) == 1 and "0 completos, 2 INCOMPLETOS" in capsys.readouterr().out


def _verificar_mixto(tmp_path, segundo):
    """Verifica 2022 (2 trozos): el canario y el recuento del primer trozo salen bien; el del segundo lo decide `segundo`."""
    _descargado(tmp_path, n=4)
    bien = servidor_con_recuento(n=4)
    cliente = ClienteFalso({"https://x": [bien, bien, segundo]})  # 1.º canario, 2.º trozo 0, 3.º trozo 1
    return dh.verificar_descarga(
        cliente, tmp_path, ["2022-01-01"], pausa_s=0, log=lambda *_: None, rondas=1, espera_s=0
    )


def test_un_solo_archivo_incompleto_basta_para_que_la_verificacion_no_sea_correcta(tmp_path):
    """Caso realista: uno completo y otro INCOMPLETO. `ok` debe ser falso aunque haya algún archivo correcto."""
    r = _verificar_mixto(tmp_path, servidor_con_recuento(total=9, n=4))
    assert r["correctos"] == ["2022-01-01_0.json"] and r["incorrectos"] == ["2022-01-01_1.json"] and not r["ok"]


def test_un_solo_archivo_sin_verificar_basta_para_que_la_verificacion_no_sea_correcta(tmp_path):
    """Uno completo y otro cuyo recuento no se pudo leer: `ok` es falso (lo no verificado no se da por bueno)."""

    def sin_count(consulta):
        return {"osm3s": {}, "elements": []}

    r = _verificar_mixto(tmp_path, sin_count)
    assert r["correctos"] == ["2022-01-01_0.json"] and r["sin_verificar"] == ["2022-01-01_1.json"] and not r["ok"]


# ---- «completo» va ligado a la identidad del archivo --------------------------------------------------------------------
def _reescribir_con_sha_nuevo(tmp_path, archivo, cambiar):
    """Altera el contenido de un archivo descargado y pone el sha256 NUEVO en el manifiesto (como si el manifiesto hubiera
    sido reescrito a juego), para probar que lo que se comprueba no es solo el hash."""
    ruta = tmp_path / archivo
    contenido = json.loads(ruta.read_text(encoding="utf-8"))
    cambiar(contenido)
    ruta.write_text(json.dumps(contenido), encoding="utf-8")
    manifiesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifiesto["archivos"][archivo]["sha256"] = dh.sha256_de(ruta)
    (tmp_path / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")


def _estado(tmp_path, archivo):
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    return m["archivos"][archivo]["verificacion"]


def test_un_archivo_alterado_con_el_mismo_numero_de_elementos_no_sale_completo(tmp_path):
    """Si el JSON cambia después de descargarlo (mismo número de elementos, distinto contenido) el sha256 ya no coincide con
    el manifiesto: queda MODIFICADO, `ok` es falso y ni siquiera se gasta una consulta de recuento para ese archivo."""
    _descargado(tmp_path, n=4)
    ruta = tmp_path / "2022-01-01_0.json"
    contenido = json.loads(ruta.read_text(encoding="utf-8"))
    contenido["elements"][0]["tags"] = {"amenity": "bar", "name": "Inventado"}  # misma cantidad, otros datos
    ruta.write_text(json.dumps(contenido), encoding="utf-8")
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=4)})
    r = dh.verificar_descarga(cliente, tmp_path, ["2022-01-01"], pausa_s=0, log=lambda *_: None, rondas=1, espera_s=0)
    assert r["alterados"] == ["2022-01-01_0.json"] and r["correctos"] == ["2022-01-01_1.json"] and not r["ok"]
    assert _estado(tmp_path, "2022-01-01_0.json")["estado"] == "MODIFICADO"
    assert "sha256" in _estado(tmp_path, "2022-01-01_0.json")["motivo"]
    assert cliente.consultas_reales() == 1  # solo se pidió el recuento del archivo íntegro


@pytest.mark.parametrize(
    "campo, valor",
    [("instante", "2024-01-01"), ("franja", 1), ("fecha_pedida", "2024-01-01T00:00:00Z"), ("fecha_pedida", None)],
)
def test_un_archivo_que_dice_ser_de_otro_instante_franja_o_fecha_queda_modificado(tmp_path, campo, valor):
    """Aunque el manifiesto lleve el sha256 del archivo cambiado, si DENTRO dice otro instante, otra franja u otra fecha
    pedida que la que le corresponde, no puede salir «completo» (p. ej. un trozo de 2024 copiado como si fuera de 2022).
    """
    _descargado(tmp_path, n=4)
    _reescribir_con_sha_nuevo(tmp_path, "2022-01-01_0.json", lambda c: c.__setitem__(campo, valor))
    r = _verificar(tmp_path, n=4)
    assert r["alterados"] == ["2022-01-01_0.json"] and not r["ok"]
    assert campo in _estado(tmp_path, "2022-01-01_0.json")["motivo"]


def test_un_archivo_con_distinto_numero_de_elementos_que_el_manifiesto_queda_modificado(tmp_path):
    """El manifiesto dice 4 elementos; si el archivo tiene otros, no es el descargado (aunque el sha256 se hubiera puesto a
    juego)."""
    _descargado(tmp_path, n=4)
    _reescribir_con_sha_nuevo(tmp_path, "2022-01-01_0.json", lambda c: c["elements"].pop())
    r = _verificar(tmp_path, n=4)
    assert r["alterados"] == ["2022-01-01_0.json"] and "3 elementos" in _estado(tmp_path, "2022-01-01_0.json")["motivo"]


def test_un_archivo_sin_sha256_en_el_manifiesto_no_se_puede_dar_por_completo(tmp_path):
    """Un manifiesto sin el hash del archivo no permite asegurar que sea el descargado: MODIFICADO, no «completo»."""
    _descargado(tmp_path, n=4)
    manifiesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    del manifiesto["archivos"]["2022-01-01_0.json"]["sha256"]
    (tmp_path / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    r = _verificar(tmp_path, n=4)
    assert (
        r["alterados"] == ["2022-01-01_0.json"]
        and "no trae el sha256" in _estado(tmp_path, "2022-01-01_0.json")["motivo"]
    )


def test_un_archivo_que_no_es_un_json_legible_queda_modificado(tmp_path):
    """Un archivo corrupto cuyo hash se pusiera a juego tampoco pasa: se comprueba que se pueda leer con `elements`."""
    _descargado(tmp_path, n=4)
    (tmp_path / "2022-01-01_0.json").write_text("{ esto no es json", encoding="utf-8")
    manifiesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifiesto["archivos"]["2022-01-01_0.json"]["sha256"] = dh.sha256_de(tmp_path / "2022-01-01_0.json")
    (tmp_path / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    r = _verificar(tmp_path, n=4)
    assert r["alterados"] == ["2022-01-01_0.json"] and "legible" in _estado(tmp_path, "2022-01-01_0.json")["motivo"]


def test_un_archivo_intacto_deja_anotado_el_sha256_que_se_verifico(tmp_path):
    """«Completo» queda ligado al hash del archivo verificado (trazabilidad: qué archivo exacto se comprobó)."""
    _descargado(tmp_path, n=4)
    _verificar(tmp_path, n=4)
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["archivos"]["2022-01-01_0.json"]
    assert m["verificacion"]["sha256_verificado"] == m["sha256"] == dh.sha256_de(tmp_path / "2022-01-01_0.json")


def test_el_resumen_de_main_cuenta_los_archivos_modificados(tmp_path, monkeypatch, capsys):
    """`--verificar` informa también de los MODIFICADOS y sale con 1."""
    _descargado(tmp_path, n=4)
    (tmp_path / "2022-01-01_0.json").write_text(json.dumps({"instante": "x", "elements": []}), encoding="utf-8")
    monkeypatch.setattr(dh, "OverpassClient", lambda **kw: ClienteFalso({"https://x": servidor_con_recuento(n=4)}))
    argumentos = ["--verificar", "--out", str(tmp_path), "--instantes", "2022-01-01", "--pausa", "0", "--rondas", "1"]
    assert dh.main(argumentos + ["--espera", "0"]) == 1
    assert "1 MODIFICADOS" in capsys.readouterr().out


# ---- el total del servidor debe ser un entero no negativo en el formato de Overpass ----------------------------------------
@pytest.mark.parametrize("total", ["-5", "+5", " 5", "5 ", "5.0", "1e3", "٥", "", "cinco", None, 7, 7.0, True])
def test_el_total_del_servidor_debe_ser_una_cadena_de_digitos_ascii(total):
    """`int()` aceptaría «-5», «+5», « 5 » o dígitos de otros alfabetos: un recuento así no es válido y no se interpreta."""
    with pytest.raises(ValueError, match="count"):
        dh.total_del_servidor({"elements": [{"type": "count", "id": 0, "tags": {"total": total}}]})


@pytest.mark.parametrize("total, esperado", [("0", 0), ("1370", 1370), ("007", 7)])
def test_el_total_del_servidor_acepta_cadenas_de_digitos_ascii(total, esperado):
    assert dh.total_del_servidor({"elements": [{"type": "count", "id": 0, "tags": {"total": total}}]}) == esperado


def test_un_archivo_cuyo_elements_no_es_una_lista_queda_modificado_aunque_tenga_la_longitud_esperada(tmp_path):
    """`elements` como cadena de 4 caracteres tiene `len` 4, como los 4 elementos del manifiesto: se comprueba el tipo."""
    _descargado(tmp_path, n=4)
    _reescribir_con_sha_nuevo(tmp_path, "2022-01-01_0.json", lambda c: c.__setitem__("elements", "abcd"))
    r = _verificar(tmp_path, n=4)
    assert (
        r["alterados"] == ["2022-01-01_0.json"]
        and "no es una lista" in _estado(tmp_path, "2022-01-01_0.json")["motivo"]
    )


# ---- la huella versionada: el ancla externa ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def huella_en_tmp(tmp_path, monkeypatch):
    """En TODOS los tests la huella va a una carpeta temporal: nunca se lee ni se escribe docs/HUELLA_OSM_HISTORY.json (que es
    la real y versionada: si un test la recogiera, compararía datos falsos con hashes reales)."""
    ruta = tmp_path / "huella" / "HUELLA.json"
    monkeypatch.setattr(dh, "HUELLA_POR_DEFECTO", ruta)
    return ruta


def _descargado_y_verificado(tmp_path, n=4):
    """Descarga los 7 trozos del plan y los verifica como completos (lo que hace falta para poder anclar)."""
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=n)})
    dh.descargar(cliente, tmp_path, None, pausa_s=0, log=lambda *_: None)
    dh.verificar_descarga(cliente, tmp_path, None, pausa_s=0, log=lambda *_: None, rondas=1, espera_s=0)
    return cliente


def test_la_huella_solo_contiene_hashes_recuentos_y_fechas_no_datos(tmp_path):
    """Es lo que se versiona en git: por archivo, sha256, elementos, fecha pedida, espejo y fecha de descarga. Ningún elemento
    de OSM, ni etiquetas, ni posiciones."""
    _descargado_y_verificado(tmp_path)
    destino = tmp_path / "H.json"
    huella = dh.escribir_huella(tmp_path, destino)
    assert sorted(huella["archivos"]) == sorted(f"{n}_{f}.json" for n, f, _, _ in dh.plan())
    for entrada in huella["archivos"].values():
        assert sorted(entrada) == sorted(dh.CAMPOS_DE_LA_HUELLA)
    texto = destino.read_text(encoding="utf-8")
    assert "elements" not in texto and '"tags"' not in texto and '"lat"' not in texto
    assert json.loads(texto) == huella and dh.cargar_huella(destino) == huella


def test_la_huella_coincide_con_el_manifiesto_archivo_por_archivo(tmp_path):
    """Los valores anclados son los del manifiesto verificado (sha256 incluido)."""
    _descargado_y_verificado(tmp_path)
    huella = dh.escribir_huella(tmp_path, tmp_path / "H.json")
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["archivos"]
    for archivo, entrada in huella["archivos"].items():
        assert entrada["sha256"] == m[archivo]["sha256"] == dh.sha256_de(tmp_path / archivo)
        assert entrada["elementos"] == m[archivo]["elementos"]


def test_no_se_ancla_lo_que_no_esta_verificado_como_completo(tmp_path):
    """Sin `--verificar` previo (o con algún archivo incompleto) la huella se niega: no se ancla lo no comprobado."""
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=4)})
    dh.descargar(cliente, tmp_path, None, pausa_s=0, log=lambda *_: None)  # descargado pero SIN verificar
    with pytest.raises(ValueError, match="no está verificado como completo"):
        dh.escribir_huella(tmp_path, tmp_path / "H.json")
    assert not (tmp_path / "H.json").exists()


def test_no_se_ancla_una_descarga_incompleta(tmp_path):
    """Si falta algún trozo del plan en el manifiesto, no se escribe la huella."""
    _descargado_y_verificado(tmp_path)
    manifiesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    del manifiesto["archivos"]["hoy_1.json"]
    (tmp_path / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    with pytest.raises(ValueError, match="Falta hoy_1.json"):
        dh.escribir_huella(tmp_path, tmp_path / "H.json")


def test_no_se_ancla_un_archivo_con_verificacion_incompleta(tmp_path):
    """Un solo archivo INCOMPLETO impide anclar toda la descarga."""
    _descargado_y_verificado(tmp_path)
    manifiesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifiesto["archivos"]["2022-01-01_0.json"]["verificacion"]["estado"] = "INCOMPLETO"
    (tmp_path / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    with pytest.raises(ValueError, match="2022-01-01_0.json no está verificado como completo"):
        dh.escribir_huella(tmp_path, tmp_path / "H.json")


def _alterar_archivo_y_manifiesto_a_juego(tmp_path):
    """El caso del hallazgo de la ronda 7: se cambian las etiquetas de un archivo Y se recalcula su sha256 en el manifiesto."""
    _reescribir_con_sha_nuevo(
        tmp_path, "2022-01-01_0.json", lambda c: c["elements"][0].__setitem__("tags", {"amenity": "bar", "name": "X"})
    )


def test_alterar_un_archivo_y_el_manifiesto_a_juego_se_detecta_con_la_huella(tmp_path):
    """Sin ancla externa, un archivo cambiado con el manifiesto recalculado pasa todas las comprobaciones locales; con la
    huella versionada, el sha256 del manifiesto ya no coincide con el anclado y queda MODIFICADO."""
    _descargado_y_verificado(tmp_path)
    huella = dh.escribir_huella(tmp_path, tmp_path / "H.json")
    _alterar_archivo_y_manifiesto_a_juego(tmp_path)
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=4)})
    r = dh.verificar_descarga(
        cliente, tmp_path, ["2022-01-01"], pausa_s=0, log=lambda *_: None, rondas=1, espera_s=0, huella=huella
    )
    assert r["alterados"] == ["2022-01-01_0.json"] and not r["ok"]
    assert "huella versionada en `sha256`" in _estado(tmp_path, "2022-01-01_0.json")["motivo"]


def test_sin_huella_una_alteracion_conjunta_de_archivo_y_manifiesto_no_se_detecta_y_esta_declarado(tmp_path):
    """LÍMITE DECLARADO (y probado, para que nadie crea lo contrario): sin ancla externa, un manifiesto que vive junto a los
    datos no puede detectar que se alteraron ambos a la vez. Por eso se avisa y se recomienda versionar la huella."""
    _descargado_y_verificado(tmp_path)
    _alterar_archivo_y_manifiesto_a_juego(tmp_path)
    r = _verificar(tmp_path, n=4)  # sin huella
    assert r["ok"] and r["alterados"] == []


@pytest.mark.parametrize("campo", ["elementos", "fecha_pedida", "espejo", "descargado_utc"])
def test_cada_campo_de_la_huella_se_comprueba(tmp_path, campo):
    """Si el manifiesto difiere de la huella en cualquiera de sus campos, el archivo queda MODIFICADO."""
    _descargado_y_verificado(tmp_path)
    huella = dh.escribir_huella(tmp_path, tmp_path / "H.json")
    huella["archivos"]["2022-01-01_0.json"][campo] = "otro" if campo != "elementos" else 999
    r = dh.verificar_descarga(
        ClienteFalso({"https://x": servidor_con_recuento(n=4)}),
        tmp_path,
        ["2022-01-01"],
        pausa_s=0,
        log=lambda *_: None,
        rondas=1,
        espera_s=0,
        huella=huella,
    )
    assert r["alterados"] == ["2022-01-01_0.json"] and campo in _estado(tmp_path, "2022-01-01_0.json")["motivo"]


def test_un_archivo_que_no_figura_en_la_huella_queda_modificado(tmp_path):
    """Un trozo que no está anclado no puede darse por íntegro."""
    _descargado_y_verificado(tmp_path)
    huella = dh.escribir_huella(tmp_path, tmp_path / "H.json")
    del huella["archivos"]["2022-01-01_1.json"]
    r = dh.verificar_descarga(
        ClienteFalso({"https://x": servidor_con_recuento(n=4)}),
        tmp_path,
        ["2022-01-01"],
        pausa_s=0,
        log=lambda *_: None,
        rondas=1,
        espera_s=0,
        huella=huella,
    )
    assert r["alterados"] == ["2022-01-01_1.json"] and r["correctos"] == ["2022-01-01_0.json"]
    assert "no figura en la huella" in _estado(tmp_path, "2022-01-01_1.json")["motivo"]


def test_una_huella_intacta_deja_pasar_los_archivos_intactos(tmp_path):
    """Con la huella correcta y los datos sin tocar, todo sale completo (no hay falsos positivos)."""
    _descargado_y_verificado(tmp_path)
    huella = dh.escribir_huella(tmp_path, tmp_path / "H.json")
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=4)})
    r = dh.verificar_descarga(
        cliente, tmp_path, None, pausa_s=0, log=lambda *_: None, rondas=1, espera_s=0, huella=huella
    )
    assert r["ok"] and len(r["correctos"]) == 7 and r["alterados"] == []


def test_cargar_huella_sin_archivo_devuelve_none_y_con_archivo_roto_falla_a_la_vista(tmp_path):
    """Que no exista la huella es un caso normal (aviso); que exista y esté rota no se ignora en silencio."""
    assert dh.cargar_huella(tmp_path / "no_existe.json") is None
    for contenido in ("{ no es json", json.dumps({"formato": 1}), json.dumps({"archivos": [1, 2]}), json.dumps([1])):
        (tmp_path / "rota.json").write_text(contenido, encoding="utf-8")
        with pytest.raises(ValueError, match="no se ignora en silencio"):
            dh.cargar_huella(tmp_path / "rota.json")


def test_main_huella_escribe_la_huella_y_se_niega_si_no_esta_verificado(tmp_path, huella_en_tmp, capsys):
    """`--huella` escribe docs/HUELLA_OSM_HISTORY.json solo con todo verificado; si no, sale con 1 y lo explica."""
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=4)})
    dh.descargar(cliente, tmp_path, None, pausa_s=0, log=lambda *_: None)
    destino = ["--huella-destino", str(huella_en_tmp)]
    assert dh.main(["--huella", "--out", str(tmp_path)] + destino) == 1 and not huella_en_tmp.exists()
    assert "No se escribió la huella" in capsys.readouterr().out
    dh.verificar_descarga(cliente, tmp_path, None, pausa_s=0, log=lambda *_: None, rondas=1, espera_s=0)
    assert dh.main(["--huella", "--out", str(tmp_path)] + destino) == 0 and huella_en_tmp.exists()
    assert "7 archivos" in capsys.readouterr().out


def test_main_verificar_usa_la_huella_si_existe_y_avisa_si_no(tmp_path, huella_en_tmp, monkeypatch, capsys):
    """Sin huella versionada, `--verificar` avisa de que se comprueba solo contra el manifiesto; con huella, la usa."""
    _descargado_y_verificado(tmp_path)
    monkeypatch.setattr(dh, "OverpassClient", lambda **kw: ClienteFalso({"https://x": servidor_con_recuento(n=4)}))
    base = ["--verificar", "--out", str(tmp_path), "--pausa", "0", "--rondas", "1", "--espera", "0"]
    assert dh.main(base) == 0
    assert "AVISO: no hay huella versionada" in capsys.readouterr().out
    dh.escribir_huella(tmp_path, huella_en_tmp)
    _alterar_archivo_y_manifiesto_a_juego(tmp_path)
    assert dh.main(base) == 1  # ahora la huella detecta la alteración conjunta
    salida = capsys.readouterr().out
    assert "AVISO" not in salida and "1 MODIFICADOS" in salida


def test_la_huella_real_versionada_tiene_la_forma_prometida():
    """`docs/HUELLA_OSM_HISTORY.json` (la real, en git) cubre exactamente los 7 trozos del plan, solo con los campos
    permitidos y sin ningún dato de OSM. En el CI no están los datos descargados, así que aquí solo se comprueba la forma;
    el contenido se contrasta con `--verificar` donde estén los datos."""
    ruta = ROOT / "docs" / "HUELLA_OSM_HISTORY.json"
    huella = json.loads(ruta.read_text(encoding="utf-8"))
    assert sorted(huella["archivos"]) == sorted(f"{n}_{f}.json" for n, f, _, _ in dh.plan())
    for archivo, entrada in huella["archivos"].items():
        assert sorted(entrada) == sorted(dh.CAMPOS_DE_LA_HUELLA), archivo
        assert len(entrada["sha256"]) == 64 and int(entrada["sha256"], 16) >= 0 and entrada["elementos"] > 0
    texto = ruta.read_text(encoding="utf-8")
    assert '"elements"' not in texto and '"tags"' not in texto and '"lat"' not in texto


# ---- no perder datos anclados; escritura atómica; manifiesto tras cada trozo ---------------------------------------------
def test_una_nueva_descarga_no_sobrescribe_los_trozos_anclados_en_la_huella(tmp_path):
    """Esos datos NO están en git: volver a descargar (`--instantes hoy` o la descarga completa) los pisaría sin remedio y,
    además, los dejaría «MODIFICADOS» frente a la huella. Con la huella dada, se omiten y se anotan en `omitidos`."""
    _descargado_y_verificado(tmp_path, n=4)
    huella = dh.escribir_huella(tmp_path, tmp_path / "H.json")
    antes = {p.name: dh.sha256_de(p) for p in tmp_path.glob("*.json") if p.name not in ("manifest.json", "H.json")}
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=9)})  # datos DISTINTOS (9 elementos por trozo)
    m = dh.descargar(cliente, tmp_path, ["hoy"], pausa_s=0, log=lambda *_: None, huella=huella)
    assert sorted(m["omitidos"]) == ["ciclo_de_vida_0.json", "hoy_0.json", "hoy_1.json"] and m["fallidos"] == []
    assert cliente.session.llamadas == []  # ni siquiera se les pidió nada al servidor
    despues = {p.name: dh.sha256_de(p) for p in tmp_path.glob("*.json") if p.name not in ("manifest.json", "H.json")}
    assert despues == antes


def test_con_sobrescribir_si_se_vuelve_a_descargar_lo_anclado(tmp_path):
    """`sobrescribir=True` (`--sobrescribir`) es la salida explícita para forzar la descarga de lo anclado."""
    _descargado_y_verificado(tmp_path, n=4)
    huella = dh.escribir_huella(tmp_path, tmp_path / "H.json")
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=9)})
    m = dh.descargar(cliente, tmp_path, ["hoy"], pausa_s=0, log=lambda *_: None, huella=huella, sobrescribir=True)
    assert m["omitidos"] == [] and m["archivos"]["hoy_0.json"]["elementos"] == 9


def test_un_trozo_que_no_esta_anclado_si_se_descarga_aunque_haya_huella(tmp_path):
    """Solo se protege lo que figura en la huella y existe en disco: un trozo ausente se descarga normalmente."""
    _descargado_y_verificado(tmp_path, n=4)
    huella = dh.escribir_huella(tmp_path, tmp_path / "H.json")
    (tmp_path / "hoy_1.json").unlink()
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=4)})
    m = dh.descargar(cliente, tmp_path, ["hoy"], pausa_s=0, log=lambda *_: None, huella=huella)
    assert "hoy_1.json" not in m["omitidos"] and (tmp_path / "hoy_1.json").exists()


def test_el_procedimiento_para_reanclar_tras_sobrescribir_tiene_salida(tmp_path, huella_en_tmp):
    """Sin esta salida era un callejón: tras sobrescribir, la huella vieja marca MODIFICADO y no se podía volver a anclar.
    Con `--verificar --sin-huella` se verifica sin exigirla, y entonces `--huella` ancla lo nuevo."""
    _descargado_y_verificado(tmp_path, n=4)
    huella = dh.escribir_huella(tmp_path, huella_en_tmp)
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=9)})
    dh.descargar(cliente, tmp_path, ["hoy"], pausa_s=0, log=lambda *_: None, huella=huella, sobrescribir=True)
    con_huella = dh.verificar_descarga(
        cliente, tmp_path, ["hoy"], pausa_s=0, log=lambda *_: None, rondas=1, espera_s=0, huella=huella
    )
    assert not con_huella["ok"] and len(con_huella["alterados"]) == 3  # la huella vieja ya no describe estos datos
    assert dh.verificar_descarga(cliente, tmp_path, ["hoy"], pausa_s=0, log=lambda *_: None, rondas=1, espera_s=0)["ok"]
    assert dh.main(["--huella", "--out", str(tmp_path), "--huella-destino", str(huella_en_tmp)]) == 0
    assert dh.cargar_huella(huella_en_tmp)["archivos"]["hoy_0.json"]["elementos"] == 9


def test_main_verificar_con_sin_huella_no_exige_la_huella(tmp_path, huella_en_tmp, monkeypatch, capsys):
    """`--sin-huella` verifica sin comparar con la huella (y sin el aviso de que no existe)."""
    _descargado_y_verificado(tmp_path)
    dh.escribir_huella(tmp_path, huella_en_tmp)
    _alterar_archivo_y_manifiesto_a_juego(tmp_path)
    monkeypatch.setattr(dh, "OverpassClient", lambda **kw: ClienteFalso({"https://x": servidor_con_recuento(n=4)}))
    base = ["--verificar", "--out", str(tmp_path), "--pausa", "0", "--rondas", "1", "--espera", "0"]
    assert dh.main(base) == 1  # con huella: detecta la alteración conjunta
    assert dh.main(base + ["--sin-huella"]) == 0  # sin ella: no la exige
    assert "AVISO" not in capsys.readouterr().out.split("Verificación:")[-1]


def test_una_interrupcion_al_escribir_no_deja_un_archivo_a_medias_ni_un_completo_caducado(tmp_path, monkeypatch):
    """Ctrl+C o un fallo de disco mientras se reescribe un trozo: el archivo antiguo queda íntegro (escritura atómica) o, si
    ya se había quitado su entrada, el manifiesto no lo da por «completo»: nunca archivo nuevo + entrada antigua."""
    _descargado_y_verificado(tmp_path, n=4)
    original = (tmp_path / "hoy_0.json").read_text(encoding="utf-8")

    def interrumpe(ruta, texto):
        if Path(ruta).name == "hoy_0.json":
            (Path(ruta).with_name("hoy_0.json.tmp")).write_text(
                texto[:20], encoding="utf-8"
            )  # a medias, en el temporal
            raise KeyboardInterrupt
        return real(ruta, texto)

    real = dh._escribir_atomico
    monkeypatch.setattr(dh, "_escribir_atomico", interrumpe)
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=9)})
    with pytest.raises(KeyboardInterrupt):
        dh.descargar(cliente, tmp_path, ["hoy"], pausa_s=0, log=lambda *_: None)
    assert (tmp_path / "hoy_0.json").read_text(encoding="utf-8") == original  # el archivo definitivo sigue entero
    manifiesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert "hoy_0.json" not in manifiesto["archivos"]  # y no queda una entrada «completo» caducada
    with pytest.raises(ValueError, match="hoy_0.json: no está descargado"):
        dh.exigir_datos_verificados(tmp_path)


def test_el_manifiesto_se_guarda_tras_cada_trozo_y_no_solo_al_final(tmp_path, monkeypatch):
    """Si la descarga muere a mitad (aquí, al tercer trozo), el manifiesto ya recoge los dos primeros."""
    llamadas = {"n": 0}
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=4)})
    real = dh.pedir

    def pedir_que_muere(*a, **k):
        llamadas["n"] += 1
        if llamadas["n"] == 3:
            raise KeyboardInterrupt
        return real(*a, **k)

    monkeypatch.setattr(dh, "pedir", pedir_que_muere)
    with pytest.raises(KeyboardInterrupt):
        dh.descargar(cliente, tmp_path, ["2022-01-01", "2024-01-01"], pausa_s=0, log=lambda *_: None)
    manifiesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert sorted(manifiesto["archivos"]) == ["2022-01-01_0.json", "2022-01-01_1.json"]


# ---- lo que debe llamar el análisis ---------------------------------------------------------------------------------
def test_exigir_datos_verificados_devuelve_las_rutas_si_todo_esta_completo(tmp_path):
    """Con los 7 trozos completos, intactos y que coinciden con la huella, devuelve `{archivo: ruta}`."""
    _descargado_y_verificado(tmp_path)
    huella = dh.escribir_huella(tmp_path, tmp_path / "H.json")
    rutas = dh.exigir_datos_verificados(tmp_path, huella)
    assert sorted(rutas) == sorted(f"{n}_{f}.json" for n, f, _, _ in dh.plan())
    assert all(p.exists() for p in rutas.values())


def test_exigir_datos_verificados_se_niega_si_algo_no_esta_verificado(tmp_path):
    """Descargado pero sin `--verificar`: el análisis no puede usarlo."""
    dh.descargar(
        ClienteFalso({"https://x": servidor_con_recuento(n=4)}), tmp_path, None, pausa_s=0, log=lambda *_: None
    )
    with pytest.raises(ValueError, match="no está verificado como completo"):
        dh.exigir_datos_verificados(tmp_path)


def test_exigir_datos_verificados_se_niega_si_el_archivo_en_disco_ya_no_es_el_verificado(tmp_path):
    """Una descarga interrumpida (archivo nuevo junto a un manifiesto antiguo «completo») no pasa: se compara el sha256 del
    archivo EN DISCO con el verificado."""
    _descargado_y_verificado(tmp_path)
    ruta = tmp_path / "2022-01-01_0.json"
    contenido = json.loads(ruta.read_text(encoding="utf-8"))
    contenido["elements"] = contenido["elements"][:2]
    ruta.write_text(json.dumps(contenido), encoding="utf-8")  # el manifiesto sigue diciendo 4 elementos y «completo»
    with pytest.raises(ValueError, match="2022-01-01_0.json: el sha256 del archivo"):
        dh.exigir_datos_verificados(tmp_path)


def test_exigir_datos_verificados_lista_todos_los_problemas_y_sin_manifiesto_falla(tmp_path):
    """Sin descargar nada: error claro. Con varios problemas: se listan todos, no solo el primero."""
    with pytest.raises(ValueError, match="primero hay que descargar"):
        dh.exigir_datos_verificados(tmp_path)
    _descargado_y_verificado(tmp_path)
    (tmp_path / "hoy_0.json").unlink()
    manifiesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifiesto["archivos"]["2022-01-01_1.json"]["verificacion"]["estado"] = "INCOMPLETO"
    (tmp_path / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    with pytest.raises(ValueError) as e:
        dh.exigir_datos_verificados(tmp_path)
    assert "hoy_0.json: no está descargado" in str(e.value) and "2022-01-01_1.json: no está verificado" in str(e.value)


def test_exigir_datos_verificados_detecta_una_alteracion_conjunta_si_se_da_la_huella(tmp_path):
    """Archivo y manifiesto alterados a juego: con la huella del repo, el análisis se niega."""
    _descargado_y_verificado(tmp_path)
    huella = dh.escribir_huella(tmp_path, tmp_path / "H.json")
    _alterar_archivo_y_manifiesto_a_juego(tmp_path)
    # Un manifiesto actualizado solo en `sha256` deja `sha256_verificado` atrás: ya eso se detecta, incluso sin huella.
    with pytest.raises(ValueError, match="se verificó otro archivo distinto"):
        dh.exigir_datos_verificados(tmp_path)
    # Un atacante COHERENTE actualiza también `sha256_verificado`: entonces solo la huella versionada lo delata.
    manifiesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    entrada = manifiesto["archivos"]["2022-01-01_0.json"]
    entrada["verificacion"]["sha256_verificado"] = entrada["sha256"]
    (tmp_path / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    dh.exigir_datos_verificados(tmp_path)  # sin ancla externa pasa (límite declarado)
    with pytest.raises(ValueError, match="huella versionada"):
        dh.exigir_datos_verificados(tmp_path, huella)


def test_escribir_huella_se_niega_a_anclar_un_archivo_distinto_del_verificado(tmp_path):
    """Si en disco hay otro archivo (descarga interrumpida) con el manifiesto antiguo «completo», no se ancla su hash viejo."""
    _descargado_y_verificado(tmp_path)
    (tmp_path / "hoy_0.json").write_text(json.dumps({"instante": "hoy", "elements": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="hoy_0.json: el archivo en disco no es el que se verificó"):
        dh.escribir_huella(tmp_path, tmp_path / "H.json")


# ---- main: errores coherentes y protección de la huella real -----------------------------------------------------------
def test_main_con_una_huella_rota_sale_con_error_claro_no_con_un_traceback(tmp_path, huella_en_tmp, capsys):
    """Una huella ilegible no se ignora en silencio, pero tampoco revienta: mensaje y código 1 (en cualquier modo)."""
    huella_en_tmp.parent.mkdir(parents=True)
    huella_en_tmp.write_text("{ rota", encoding="utf-8")
    assert dh.main(["--verificar", "--out", str(tmp_path)]) == 1
    salida = capsys.readouterr().out  # una sola lectura: capsys vacía el búfer al leerlo
    assert "ERROR" in salida and "no se ignora en silencio" in salida
    assert dh.main(["--out", str(tmp_path)]) == 1  # también al descargar
    assert "no se ignora en silencio" in capsys.readouterr().out


def test_main_verificar_sin_manifiesto_sale_con_error_claro(tmp_path, monkeypatch, capsys):
    """Sin descargar nada o con un manifiesto ilegible: mensaje y código 1, no un traceback."""
    monkeypatch.setattr(dh, "OverpassClient", lambda **kw: ClienteFalso({"https://x": servidor_con_recuento(n=4)}))
    assert dh.main(["--verificar", "--out", str(tmp_path)]) == 1
    salida = capsys.readouterr().out
    assert "no se pudo verificar" in salida and "primero hay que descargar" in salida
    (tmp_path / "manifest.json").write_text("{ no es json", encoding="utf-8")
    assert dh.main(["--verificar", "--out", str(tmp_path)]) == 1


@pytest.mark.parametrize("contenido", [{"archivos": {"a": 1}}, {"archivos": {"a": [1]}}, {"archivos": {"a": "x"}}])
def test_cargar_huella_rechaza_entradas_que_no_son_objetos(tmp_path, contenido):
    """Una entrada que no sea un objeto reventaría más tarde con un AttributeError: se rechaza al cargar."""
    (tmp_path / "h.json").write_text(json.dumps(contenido), encoding="utf-8")
    with pytest.raises(ValueError, match="no se ignora en silencio"):
        dh.cargar_huella(tmp_path / "h.json")


def test_huella_con_otro_out_no_puede_sobrescribir_la_huella_real(tmp_path, huella_en_tmp, capsys):
    """`--huella --out <otra carpeta>` escribiría hashes de otros datos en docs/HUELLA_OSM_HISTORY.json: se niega y pide un
    destino explícito."""
    _descargado_y_verificado(tmp_path)
    assert dh.main(["--huella", "--out", str(tmp_path)]) == 1 and not huella_en_tmp.exists()
    assert "--huella-destino" in capsys.readouterr().out


@pytest.mark.parametrize("otro", [["--verificar"], ["--dry-run"], ["--sobrescribir"], ["--sin-huella"]])
def test_huella_no_se_combina_con_otros_modos(tmp_path, huella_en_tmp, capsys, otro):
    """Antes `--huella` ignoraba en silencio `--verificar` y `--dry-run`: ahora es un error explícito."""
    assert dh.main(["--huella", "--out", str(tmp_path), "--huella-destino", str(huella_en_tmp)] + otro) == 1
    assert "no se combina" in capsys.readouterr().out


def test_sin_huella_solo_vale_con_verificar(tmp_path, capsys):
    assert dh.main(["--sin-huella", "--out", str(tmp_path)]) == 1
    assert "solo tiene sentido con --verificar" in capsys.readouterr().out


# ---- --pausa también manda tras el canario -------------------------------------------------------------------------------
def test_la_pausa_que_indica_el_usuario_tambien_se_aplica_tras_el_canario(tmp_path, monkeypatch):
    """Con `pausa_s=7` la pausa tras cada canario nuevo es de 7 s, no la constante de 12 (antes `--pausa 0` seguía esperando)."""
    monkeypatch.setattr(dh, "PAUSA_S", 12)  # la constante por defecto es distinta de la que indica el usuario
    pausas = []
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=4)})
    dh.pedir(cliente, "q", FECHA, espera_s=0, dormir=pausas.append, pausa_canario_s=7)
    assert pausas == [7]
    pausas.clear()
    dh.pedir(
        ClienteFalso({"https://x": servidor_con_recuento(n=4)}),
        "q",
        FECHA,
        espera_s=0,
        dormir=pausas.append,
        pausa_canario_s=0,
    )
    assert pausas == []  # `--pausa 0`: ninguna espera tras el canario


def test_descargar_aplica_su_pausa_tras_el_canario_y_entre_trozos(tmp_path, monkeypatch):
    """Con `pausa_s=7` (lo que sería `--pausa 7`): 7 s tras el canario de 2022 y 7 s entre los dos trozos."""
    esperas = []
    monkeypatch.setattr(dh.time, "sleep", esperas.append)
    cliente = ClienteFalso({"https://x": servidor_con_recuento(n=4)})
    dh.descargar(cliente, tmp_path, ["2022-01-01"], pausa_s=7, log=lambda *_: None)
    assert esperas == [7, 7]  # canario + entre el trozo 0 y el 1 (ninguna tras el último)


def test_escribir_atomico_deja_intacto_el_archivo_si_falla_el_reemplazo(tmp_path, monkeypatch):
    """La escritura es de verdad atómica: se escribe a un temporal y se reemplaza. Si el reemplazo falla (disco, permisos,
    interrupción), el archivo definitivo conserva su contenido anterior ENTERO (no se queda a medias)."""
    ruta = tmp_path / "datos.json"
    ruta.write_text("ANTERIOR COMPLETO", encoding="utf-8")

    def falla(origen, destino):
        raise OSError("disco lleno")

    monkeypatch.setattr(dh.os, "replace", falla)
    with pytest.raises(OSError, match="disco lleno"):
        dh._escribir_atomico(ruta, "NUEVO CONTENIDO LARGO")
    assert ruta.read_text(encoding="utf-8") == "ANTERIOR COMPLETO"


def test_escribir_atomico_sin_fallo_deja_el_contenido_nuevo_y_ningun_temporal(tmp_path):
    ruta = tmp_path / "datos.json"
    dh._escribir_atomico(ruta, "uno")
    dh._escribir_atomico(ruta, "dos")
    assert ruta.read_text(encoding="utf-8") == "dos" and [p.name for p in tmp_path.iterdir()] == ["datos.json"]


def test_escribir_huella_se_niega_si_se_verifico_otro_archivo_distinto_del_que_hay_en_disco(tmp_path):
    """Aunque el manifiesto y el disco coincidan, si `sha256_verificado` es de OTRO archivo (verificado antes de que
    cambiara), «completo» no corresponde a lo que hay: no se ancla."""
    _descargado_y_verificado(tmp_path)
    manifiesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifiesto["archivos"]["hoy_0.json"]["verificacion"]["sha256_verificado"] = "0" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    with pytest.raises(ValueError, match="hoy_0.json: el archivo en disco no es el que se verificó"):
        dh.escribir_huella(tmp_path, tmp_path / "H.json")


def test_main_al_descargar_respeta_lo_anclado_y_con_sobrescribir_lo_vuelve_a_bajar(
    tmp_path, huella_en_tmp, monkeypatch, capsys
):
    """De extremo a extremo por la línea de comandos: con la huella versionada, `main` no pisa lo anclado (lo dice y sale con
    0); con `--sobrescribir` sí lo descarga."""
    _descargado_y_verificado(tmp_path, n=4)
    dh.escribir_huella(tmp_path, huella_en_tmp)
    antes = dh.sha256_de(tmp_path / "hoy_0.json")
    monkeypatch.setattr(dh, "OverpassClient", lambda **kw: ClienteFalso({"https://x": servidor_con_recuento(n=9)}))
    base = ["--out", str(tmp_path), "--instantes", "hoy", "--pausa", "0", "--rondas", "1", "--espera", "0"]
    assert dh.main(base) == 0
    salida = capsys.readouterr().out
    assert "OMITIDO hoy_0.json" in salida and dh.sha256_de(tmp_path / "hoy_0.json") == antes
    assert dh.main(base + ["--sobrescribir"]) == 0
    assert dh.sha256_de(tmp_path / "hoy_0.json") != antes and "OMITIDO" not in capsys.readouterr().out


def test_escribir_huella_se_niega_si_el_sha256_del_manifiesto_no_es_el_del_disco(tmp_path):
    """Aunque `sha256_verificado` coincida con el disco, un `sha256` del manifiesto que no sea el del archivo actual indica un
    manifiesto desfasado: no se ancla."""
    _descargado_y_verificado(tmp_path)
    manifiesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifiesto["archivos"]["hoy_1.json"]["sha256"] = "f" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    with pytest.raises(ValueError, match="hoy_1.json: el archivo en disco no es el que se verificó"):
        dh.escribir_huella(tmp_path, tmp_path / "H.json")


# ---- `sha256_verificado` es obligatorio: sin él no consta qué archivo se verificó -----------------------------------------
def _sin_sha256_verificado(tmp_path, archivo="hoy_0.json"):
    """Quita el campo (como en un manifiesto de una versión anterior de la herramienta, o editado)."""
    manifiesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    del manifiesto["archivos"][archivo]["verificacion"]["sha256_verificado"]
    (tmp_path / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")


def test_sin_sha256_verificado_el_analisis_no_acepta_el_archivo(tmp_path):
    """Una entrada «completo» sin constancia de qué archivo se verificó NO es utilizable: antes el campo ausente se sustituía
    por el hash del manifiesto y pasaba."""
    _descargado_y_verificado(tmp_path)
    _sin_sha256_verificado(tmp_path)
    with pytest.raises(ValueError, match="hoy_0.json: el manifiesto no registra qué archivo se verificó"):
        dh.exigir_datos_verificados(tmp_path)


def test_sin_sha256_verificado_tampoco_se_ancla(tmp_path):
    """`escribir_huella` repetía el mismo fallback: ahora exige el campo y que coincida con el disco y el manifiesto."""
    _descargado_y_verificado(tmp_path)
    _sin_sha256_verificado(tmp_path)
    with pytest.raises(ValueError, match="hoy_0.json: el archivo en disco no es el que se verificó"):
        dh.escribir_huella(tmp_path, tmp_path / "H.json")
    assert not (tmp_path / "H.json").exists()


def test_el_procedimiento_para_recuperar_un_manifiesto_sin_sha256_verificado_es_verificar_de_nuevo(tmp_path):
    """El mensaje manda ejecutar `--verificar` de nuevo, y eso funciona: vuelve a registrar el campo y entonces sí se puede
    usar y anclar."""
    _descargado_y_verificado(tmp_path)
    _sin_sha256_verificado(tmp_path)
    with pytest.raises(ValueError):
        dh.exigir_datos_verificados(tmp_path)
    assert _verificar(tmp_path, n=4, instantes=("2022-01-01", "2024-01-01", "hoy"))["ok"]
    assert len(dh.exigir_datos_verificados(tmp_path)) == 7
    assert len(dh.escribir_huella(tmp_path, tmp_path / "H.json")["archivos"]) == 7
