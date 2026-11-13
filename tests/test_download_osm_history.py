"""Pruebas de la descarga del estado histórico de OpenStreetMap (tools/download_osm_history.py, fase 4 §3.M).

Sin red: se usa un cliente falso. Lo más importante que comprueban: que un espejo de Overpass que IGNORA la fecha pedida
(y devuelve el mapa actual) se rechaza, porque si no, el «estado de 2022» sería en realidad el de hoy y no habría cierres.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.poi_client import CATEGORY_TAGS, OverpassClient  # noqa: E402
from tools import download_osm_history as dh  # noqa: E402


class Respuesta:
    def __init__(self, datos, error=None):
        self.datos, self.error = datos, error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.datos


class SesionFalsa:
    """Responde a cada espejo con lo que se le configure: {endpoint: JSON o excepción, o una LISTA de ellos que se va
    consumiendo en cada llamada (la última se repite)}."""

    def __init__(self, respuestas):
        self.respuestas, self.llamadas, self.timeouts = respuestas, [], []

    def post(self, endpoint, data=None, timeout=None):
        self.llamadas.append((endpoint, data["data"]))
        self.timeouts.append(timeout)
        r = self.respuestas[endpoint]
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        return Respuesta(None, r) if isinstance(r, Exception) else Respuesta(r)


class ClienteFalso:
    def __init__(self, respuestas):
        self.endpoints = list(respuestas)
        self.session = SesionFalsa(respuestas)


def respuesta(base, n=2):
    return {"osm3s": {"timestamp_osm_base": base}, "elements": [{"type": "node", "id": i} for i in range(n)]}


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


# ---- la fecha de Overpass: lo importante --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "base, pedida, esperado",
    [
        ("2022-01-01T00:00:00Z", "2022-01-01T00:00:00Z", True),  # la usó tal cual
        ("2021-12-31T23:59:59Z", "2022-01-01T00:00:00Z", True),  # un poco antes: aceptable
        ("2026-11-12T20:00:00Z", "2022-01-01T00:00:00Z", False),  # ignoró la fecha: devolvió el presente
        (None, "2022-01-01T00:00:00Z", False),  # no dice qué fecha usó
        ("2026-11-12T20:00:00Z", None, True),  # «hoy»: no hay nada que comprobar
    ],
)
def test_la_fecha_base_debe_no_ser_posterior_a_la_pedida(base, pedida, esperado):
    """Un espejo que devuelve el mapa actual para un instante pasado se detecta por su fecha base."""
    r = {"osm3s": {"timestamp_osm_base": base}} if base else {}
    assert dh.fecha_aceptada(r, pedida) is esperado


def test_un_espejo_que_ignora_la_fecha_se_rechaza_y_se_prueba_el_siguiente():
    """El primer espejo devuelve el presente para una consulta de 2022: se descarta y se usa el segundo."""
    cliente = ClienteFalso(
        {
            "https://malo": respuesta("2026-11-12T20:00:00Z"),
            "https://bueno": respuesta("2022-01-01T00:00:00Z", n=3),
        }
    )
    datos, espejo = dh.pedir(cliente, "consulta", "2022-01-01T00:00:00Z", espera_s=0)
    assert espejo == "https://bueno" and len(datos["elements"]) == 3
    assert [e for e, _ in cliente.session.llamadas] == ["https://malo", "https://bueno"]


def test_si_todos_los_espejos_ignoran_la_fecha_falla_en_vez_de_devolver_el_presente():
    """Nunca se devuelve en silencio el mapa actual como si fuera el de 2022."""
    cliente = ClienteFalso(
        {"https://a": respuesta("2026-11-12T20:00:00Z"), "https://b": respuesta("2026-11-12T20:00:00Z")}
    )
    with pytest.raises(RuntimeError, match="ignoró la fecha"):
        dh.pedir(cliente, "consulta", "2022-01-01T00:00:00Z", espera_s=0)


def test_un_error_de_red_en_un_espejo_pasa_al_siguiente():
    """Un fallo HTTP no detiene la descarga mientras otro espejo responda."""
    cliente = ClienteFalso({"https://a": OSError("sin red"), "https://b": respuesta("2022-01-01T00:00:00Z")})
    assert dh.pedir(cliente, "q", "2022-01-01T00:00:00Z")[1] == "https://b"


# ---- la descarga y su manifiesto ---------------------------------------------------------------------------------
def test_descargar_escribe_los_json_y_un_manifiesto_con_fecha_base_y_hash(tmp_path):
    """Cada trozo queda en su archivo con la fecha base que dijo Overpass y el manifiesto guarda recuento y sha256."""
    cliente = ClienteFalso({"https://x": respuesta("2022-01-01T00:00:00Z", n=4)})
    m = dh.descargar(cliente, tmp_path, ["2022-01-01"], pausa_s=0, log=lambda *_: None)
    assert m["fallidos"] == [] and sorted(m["archivos"]) == ["2022-01-01_0.json", "2022-01-01_1.json"]
    a = m["archivos"]["2022-01-01_0.json"]
    contenido = json.loads((tmp_path / "2022-01-01_0.json").read_text(encoding="utf-8"))
    assert (
        a["elementos"] == 4
        and a["osm_base"] == "2022-01-01T00:00:00Z"
        and a["sha256"] == dh.sha256_de(tmp_path / "2022-01-01_0.json")
    )
    assert contenido["instante"] == "2022-01-01" and contenido["osm_base"] == "2022-01-01T00:00:00Z"
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["descargado_utc"].endswith("Z")


def test_un_trozo_que_falla_se_anota_y_los_demas_siguen(tmp_path):
    """Si ningún espejo da la fecha pedida, ese trozo queda en `fallidos` y no se escribe su archivo."""
    cliente = ClienteFalso({"https://x": respuesta("2026-11-12T20:00:00Z")})
    m = dh.descargar(cliente, tmp_path, ["2022-01-01"], pausa_s=0, log=lambda *_: None, espera_s=0)
    assert len(m["fallidos"]) == 2 and m["archivos"] == {}
    assert not (tmp_path / "2022-01-01_0.json").exists()


def test_descargar_solo_escribe_dentro_del_directorio_de_salida(tmp_path):
    """No toca nada fuera de `out_dir` (ni la base de datos)."""
    salida = tmp_path / "out"
    dh.descargar(
        ClienteFalso({"https://x": respuesta("2022-01-01T00:00:00Z")}),
        salida,
        ["2022-01-01"],
        pausa_s=0,
        log=lambda *_: None,
    )
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
    cliente = ClienteFalso(
        {"https://a": [OSError("502 al límite de capacidad"), respuesta("2022-01-01T00:00:00Z", n=5)]}
    )
    esperas = []
    datos, espejo = dh.pedir(cliente, "q", "2022-01-01T00:00:00Z", rondas=3, espera_s=90, dormir=esperas.append)
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


def test_el_timeout_de_conexion_es_corto_y_el_de_lectura_largo():
    """Un espejo que no conecta se salta en segundos; solo la lectura (la consulta pesada) puede tardar."""
    cliente = ClienteFalso({"https://a": respuesta("2022-01-01T00:00:00Z")})
    dh.pedir(cliente, "q", "2022-01-01T00:00:00Z")
    conexion, lectura = cliente.session.timeouts[0]
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
ERROR_DE_TIEMPO = {
    "osm3s": {"timestamp_osm_base": "2022-01-01T00:00:00Z"},
    "elements": [],
    "remark": 'runtime error: Query timed out in "query" at line 3 after 151 seconds.',
}


def test_una_respuesta_http_200_con_remark_de_error_no_se_da_por_buena():
    """Si Overpass se queda sin tiempo o memoria responde 200 con `remark`, la fecha base ya escrita y `elements` vacío o
    parcial. Guardarlo como éxito daría un 2022 vacío, que parecería una ola de cierres: se descarta y se prueba otro espejo.
    """
    cliente = ClienteFalso({"https://a": ERROR_DE_TIEMPO, "https://b": respuesta("2022-01-01T00:00:00Z", n=3)})
    datos, espejo = dh.pedir(cliente, "q", "2022-01-01T00:00:00Z", rondas=1, espera_s=0)
    assert espejo == "https://b" and len(datos["elements"]) == 3


def test_si_todos_los_espejos_devuelven_un_error_de_overpass_no_se_escribe_nada(tmp_path):
    """El trozo queda en `fallidos` con el motivo y no se crea su archivo (ni un JSON vacío que parezca bueno)."""
    cliente = ClienteFalso({"https://a": ERROR_DE_TIEMPO})
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
    cliente = cliente or ClienteFalso({"https://x": respuesta("2022-01-01T00:00:00Z")})
    return dh.descargar(cliente, tmp_path, instantes, pausa_s=0, log=lambda *_: None, espera_s=0, **kw)


def test_relanzar_un_subconjunto_no_borra_lo_ya_descargado_del_manifiesto(tmp_path):
    """Tras bajar 2022 y luego solo 2024, el manifiesto trae los cuatro archivos con su hash y su fecha base."""
    _descargar(tmp_path, ["2022-01-01"])
    m = _descargar(tmp_path, ["2024-01-01"])
    assert sorted(m["archivos"]) == ["2022-01-01_0.json", "2022-01-01_1.json", "2024-01-01_0.json", "2024-01-01_1.json"]
    escrito = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert sorted(escrito["archivos"]) == sorted(m["archivos"])
    assert all(d["sha256"] and d["osm_base"] and d["descargado_utc"] for d in escrito["archivos"].values())


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
