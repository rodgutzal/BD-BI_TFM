"""Pruebas del sistema híbrido de interpretación del texto (src/ml/text_hibrido.py) y de la carga verificada del modelo:
palabras clave primero y, solo si se abstienen, el clasificador entrenado.

Desde la fase 4 el segundo paso NO se ejecuta: el reentrenamiento a once clases no pasó la regla preregistrada (§3.L3
del diseño) y el manifiesto dice `adoptado: false`, así que la aplicación responde solo con palabras clave. Por eso
estos tests cubren tres cosas a la vez: que la lógica del híbrido sigue siendo correcta (con dobles), que el artefacto
versionado sigue siendo un modelo válido aunque no se use, y que la aplicación da exactamente lo que se midió."""

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
from src.ml.text_classifier import ModeloTexto  # noqa: E402
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


def test_un_texto_vacio_o_nulo_no_falla():
    """Vacío, solo espacios o None no rompen la pantalla ni el modelo: no hay categoría. El modelo simulado se abstiene
    ante un texto sin contenido, como hace el real; lo que se prueba es que el híbrido no falla con None."""
    for texto in ("", "   ", None):
        assert th.interpretar(texto) == th.Interpretacion(None)
        assert th.interpretar(texto, ModeloFalso(None, 0.0)) == th.Interpretacion(None)


def test_sin_modelo_adoptado_una_errata_no_se_entiende_y_con_un_modelo_si():
    """El coste medido de no adoptar el modelo de once clases: con el artefacto versionado (que la regla preregistrada
    no adoptó) «una pizeria» no es una palabra clave y nadie la entiende. La lógica del híbrido sí funcionaría si
    hubiera modelo: con un `ModeloFalso` que la lee como restauración, la respuesta sería del modelo. Esto último no
    depende del artefacto, solo documenta lo que se renuncia a ganar."""
    assert th.cargar_modelo_adoptado(DIRECTORIO) is None
    assert th.interpretar("una pizeria", th.cargar_modelo_adoptado(DIRECTORIO)) == th.Interpretacion(None)
    r = th.interpretar("una pizeria", ModeloFalso("food_drink", 0.8))
    assert r.categoria == "food_drink" and r.fuente == th.FUENTE_MODELO


# ---- cargar_modelo_adoptado: solo se usa si está verificado -----------------------------------------------------
def test_el_modelo_versionado_es_evidencia_de_lo_medido_pero_no_esta_adoptado():
    """El modelo de once clases está en el repositorio como evidencia de lo que se midió, pero la regla preregistrada
    (docs/DISENO_ML_RECOMENDACION.md §L3) no lo adoptó: mejoraba la exactitud y subía las respuestas equivocadas por
    encima de la tolerancia. Se fija que el manifiesto existe, que su hash cuadra con el archivo (no es un artefacto
    cualquiera), que declara las once clases y que `adoptado` es false, de modo que la carga devuelve None y la
    aplicación usa solo palabras clave. Si alguien lo adoptara a mano sin pasar la regla, este test lo delata."""
    m = json.loads((DIRECTORIO / th.ARCHIVO_MANIFIESTO).read_text(encoding="utf-8"))
    assert m["modelo"]["sha256"] == etc.file_hash(DIRECTORIO / th.ARCHIVO_MODELO)
    assert len(m["modelo"]["clases"]) == 11 and "ninguna" in m["modelo"]["clases"]
    assert m["adoptado"] is False
    assert th.cargar_modelo_adoptado(DIRECTORIO) is None


def test_el_artefacto_versionado_carga_directamente_y_es_un_modelo_usable():
    """El artefacto de once clases NO está adoptado (el manifiesto dice `adoptado: false`, así que
    `cargar_modelo_adoptado` devuelve None a propósito), pero se conserva como evidencia de lo medido. Como ningún
    otro test lo carga ya, un archivo con el hash correcto pero internamente inválido pasaría la suite; por eso se
    carga aquí SIN pasar por la carga verificada y se comprueba que sigue siendo un modelo válido: las clases son las
    que declara el manifiesto y clasificar devuelve una de ellas con una probabilidad entre 0 y 1."""
    m = json.loads((DIRECTORIO / th.ARCHIVO_MANIFIESTO).read_text(encoding="utf-8"))
    modelo = ModeloTexto.load(DIRECTORIO / th.ARCHIVO_MODELO)
    assert modelo.clases == m["modelo"]["clases"] and len(modelo.clases) == 11
    # umbral 0: se quiere ver la clase ganadora, no que el umbral de abstención la tape
    categoria, probabilidad = modelo.clasificar("un hospital con urgencias", umbral=0.0)
    assert categoria in modelo.clases and 0.0 < probabilidad <= 1.0
    assert sum(modelo.probabilidades("un hospital con urgencias").values()) == pytest.approx(1.0)


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
    # El manifiesto real dice adoptado=false y la carga cortaría ahí, antes de mirar el hash: se fuerza adoptado=true
    # en la copia para que el test siga probando lo que dice (que un hash que no cuadra impide la carga).
    ruta_manifiesto = copia / th.ARCHIVO_MANIFIESTO
    m = json.loads(ruta_manifiesto.read_text(encoding="utf-8"))
    m["adoptado"] = True
    ruta_manifiesto.write_text(json.dumps(m), encoding="utf-8")
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
def test_la_aplicacion_da_la_misma_respuesta_que_la_evaluacion_para_cada_frase():
    """La aplicación (sin modelo adoptado: solo palabras clave) y el sistema `palabras` de la evaluación de la fase 4
    coinciden frase a frase sobre las 260 del tercer conjunto congelado (`frases_evaluacion_v3.psv`, con
    `--solo-coincidentes`). Así las cifras medidas son las de lo que ve el usuario: 163 aciertos de 260 (62,7 %) y 28
    respuestas equivocadas (10,8 %).

    No se usan las cifras del híbrido (71,2 % de exactitud): el híbrido no se adoptó porque sus equivocadas (13,1 %)
    superaron en más de los 2 puntos de tolerancia a las de las palabras clave (docs/DISENO_ML_RECOMENDACION.md §L3).
    Fijar aquí lo contrario haría que el test describiera un sistema que la aplicación no ejecuta."""
    assert th.cargar_modelo_adoptado(DIRECTORIO) is None
    tr, ev = etc.cargar(evaluacion=etc.DATA / "frases_evaluacion_v3.psv")
    ev = etc.solo_coincidentes(ev)
    evaluado = etc.evaluar(tr, ev, n_boot=50, con_mlp=False)["sistemas"]["palabras"]
    de_la_app = [th.interpretar(f).categoria for f in ev["frase"]]
    assert de_la_app == evaluado
    reales = list(ev["categoria"])
    assert len(reales) == 260
    assert int(tt.aciertos(de_la_app, reales).sum()) == 163 and int(tt.equivocadas(de_la_app, reales).sum()) == 28
