"""Pruebas del sistema híbrido de interpretación del texto (src/ml/text_hibrido.py) y de la carga verificada del modelo
adoptado en la fase 3: palabras clave primero y, solo si se abstienen, el clasificador entrenado."""

import json
import logging
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import text_hibrido as th  # noqa: E402
from src.ml import text_training as tt  # noqa: E402
from tools import evaluate_text_classifier as etc  # noqa: E402

DIRECTORIO = ROOT / "data" / "ml"


class ModeloFalso:
    """Un modelo que responde lo que se le diga, para probar la lógica del híbrido sin depender del modelo real."""

    def __init__(self, categoria, probabilidad=0.9):
        self.categoria, self.probabilidad, self.consultas = categoria, probabilidad, []

    def clasificar(self, texto):
        self.consultas.append(texto)
        return self.categoria, self.probabilidad


@pytest.fixture
def modelo_real():
    m = th.cargar_modelo_adoptado(DIRECTORIO)
    assert m is not None
    return m


@pytest.fixture
def copia(tmp_path):
    """Copia del modelo y su manifiesto, para romperlos sin tocar los versionados."""
    for nombre in (th.ARCHIVO_MODELO, th.ARCHIVO_MANIFIESTO):
        shutil.copy(DIRECTORIO / nombre, tmp_path / nombre)
    return tmp_path


# ---- interpretar: la lógica del híbrido --------------------------------------------------------------------------
def test_las_palabras_clave_mandan_aunque_el_modelo_diga_otra_cosa():
    """Si las palabras clave reconocen el negocio, esa es la respuesta y ni siquiera se consulta al modelo."""
    modelo = ModeloFalso("school")
    r = th.interpretar("una farmacia", modelo)
    assert (r.categoria, r.fuente, r.confianza) == ("hospital", th.FUENTE_PALABRAS, None)
    assert modelo.consultas == []


def test_el_modelo_solo_entra_cuando_las_palabras_clave_se_abstienen():
    """Con un texto que las palabras clave no reconocen, responde el modelo y se indica su confianza."""
    modelo = ModeloFalso("sport", 0.62)
    r = th.interpretar("zzz qqq", modelo)
    assert (r.categoria, r.fuente, r.confianza) == ("sport", th.FUENTE_MODELO, 0.62)
    assert modelo.consultas == ["zzz qqq"]


def test_si_el_modelo_tambien_se_abstiene_no_se_adivina():
    """Sin respuesta de ninguno de los dos, no hay categoría (nunca se elige una al azar)."""
    assert th.interpretar("zzz qqq", ModeloFalso(None, 0.2)) == th.Interpretacion(None)


def test_sin_modelo_el_comportamiento_es_el_de_las_palabras_clave_solas():
    """Sin modelo (no hay artefacto o no se verificó) se vuelve al comportamiento anterior."""
    assert th.interpretar("una farmacia").fuente == th.FUENTE_PALABRAS
    assert th.interpretar("zzz qqq") == th.Interpretacion(None)


def test_un_texto_vacio_o_nulo_no_falla(modelo_real):
    """Vacío, solo espacios o None no rompen la pantalla ni el modelo: no hay categoría."""
    for texto in ("", "   ", None):
        assert th.interpretar(texto, modelo_real) == th.Interpretacion(None)


def test_con_el_modelo_real_una_errata_se_entiende_y_sin_el_no(modelo_real):
    """Caso de extremo a extremo con el artefacto versionado: «una pizeria» no es una palabra clave, pero el modelo la
    entiende como restauración; sin modelo no se entendía."""
    assert th.interpretar("una pizeria").categoria is None
    r = th.interpretar("una pizeria", modelo_real)
    assert r.categoria == "food_drink" and r.fuente == th.FUENTE_MODELO and 0.5 <= r.confianza <= 1.0


# ---- cargar_modelo_adoptado: solo se usa si está verificado -----------------------------------------------------
def test_el_modelo_versionado_se_carga_y_su_hash_coincide_con_el_manifiesto():
    """El artefacto de data/ml/ está adoptado, completo y es el que describe su manifiesto."""
    m = json.loads((DIRECTORIO / th.ARCHIVO_MANIFIESTO).read_text(encoding="utf-8"))
    assert m["adoptado"] is True and m["modelo"]["sha256"] == etc.file_hash(DIRECTORIO / th.ARCHIVO_MODELO)
    modelo = th.cargar_modelo_adoptado(DIRECTORIO)
    assert modelo is not None and modelo.umbral == m["umbral"] and "ninguna" in modelo.clases


def test_sin_archivos_no_hay_modelo_y_se_avisa(tmp_path, caplog):
    """Sin modelo en la carpeta devuelve None y deja un aviso, en vez de fallar."""
    with caplog.at_level(logging.WARNING):
        assert th.cargar_modelo_adoptado(tmp_path) is None
    assert "palabras clave" in caplog.text


def test_un_modelo_que_el_manifiesto_no_da_por_adoptado_no_se_usa(copia, caplog):
    """Aunque el archivo exista y su hash cuadre, si el manifiesto dice adoptado=false no se usa."""
    ruta = copia / th.ARCHIVO_MANIFIESTO
    m = json.loads(ruta.read_text(encoding="utf-8"))
    m["adoptado"] = False
    ruta.write_text(json.dumps(m), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert th.cargar_modelo_adoptado(copia) is None
    assert "adopta" in caplog.text


def test_un_modelo_alterado_no_se_usa(copia, caplog):
    """Si el archivo del modelo cambia (hash distinto al del manifiesto), no se carga."""
    ruta = copia / th.ARCHIVO_MODELO
    ruta.write_bytes(ruta.read_bytes() + b" ")
    with caplog.at_level(logging.WARNING):
        assert th.cargar_modelo_adoptado(copia) is None
    assert "hash" in caplog.text


def test_un_manifiesto_roto_o_incompleto_no_rompe_la_carga(copia):
    """JSON inválido o sin el hash del modelo: se vuelve a las palabras clave en vez de lanzar una excepción."""
    ruta = copia / th.ARCHIVO_MANIFIESTO
    ruta.write_text("{ no es json", encoding="utf-8")
    assert th.cargar_modelo_adoptado(copia) is None
    ruta.write_text(json.dumps({"adoptado": True}), encoding="utf-8")  # sin modelo.sha256
    assert th.cargar_modelo_adoptado(copia) is None
    # JSON válido pero de otra forma: tampoco tumba la pantalla (TypeError / AttributeError)
    ruta.write_text(json.dumps({"adoptado": True, "modelo": None}), encoding="utf-8")
    assert th.cargar_modelo_adoptado(copia) is None
    ruta.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert th.cargar_modelo_adoptado(copia) is None


# ---- el sistema de la aplicación ES el que se evaluó -------------------------------------------------------------
def test_la_aplicacion_da_la_misma_respuesta_que_la_evaluacion_para_cada_frase(modelo_real):
    """El híbrido de la aplicación y el de la evaluación de la fase 3 coinciden frase a frase sobre las 192 del conjunto
    principal (mismo modelo, mismo umbral, mismas palabras clave). Así las cifras de docs/DISENO_ML_RECOMENDACION.md §3.L2
    (76,0 % de exactitud, 6,2 % de respuestas equivocadas) son las de lo que ve el usuario."""
    tr, ev = etc.cargar(evaluacion=etc.DATA / "frases_evaluacion_v2.psv")
    ev = etc.solo_coincidentes(ev)
    evaluado = etc.evaluar(tr, ev, n_boot=50, con_mlp=False)["sistemas"]["hibrido"]
    de_la_app = [th.interpretar(f, modelo_real).categoria for f in ev["frase"]]
    assert de_la_app == evaluado
    reales = list(ev["categoria"])
    assert int(tt.aciertos(de_la_app, reales).sum()) == 146 and int(tt.equivocadas(de_la_app, reales).sum()) == 12
