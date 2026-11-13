"""Tests de la fase 3: clasificador de texto del tipo de negocio (src/ml/text_classifier.py, src/ml/text_training.py y
tools/evaluate_text_classifier.py) — inferencia con solo numpy que reproduce a scikit-learn, abstención, regla de
decisión y que los datos de evaluación no se usan para entrenar ni para elegir el umbral."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import text_classifier as tc  # noqa: E402
from src.ml import text_training as tt  # noqa: E402

_s = importlib.util.spec_from_file_location("evaluate_text_classifier", ROOT / "tools" / "evaluate_text_classifier.py")
etc = importlib.util.module_from_spec(_s)
_s.loader.exec_module(etc)


@pytest.fixture(scope="module")
def datos():
    return etc.cargar()


@pytest.fixture(scope="module")
def modelo(datos):
    tr, _ = datos
    return tt.entrenar_logistica(list(tr["frase"]), list(tr["categoria"]))


# ---- n-gramas y normalización ------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "texto",
    [
        "pizzería",
        "niño",
        "  espacios   de más  ",
        "a",
        "ab",
        "abc",
        "tienda de ropa",
        "ÁÉÍÓÚ Ñandú",
        "",
        "   ",
        "centro-comercial",
        "123 abc",
        "café,té;mate",
        "una frase bastante más larga que las demás del conjunto",
    ],
)
def test_los_ngramas_coinciden_con_los_de_scikit_learn(texto):
    """Los n-gramas de caracteres son exactamente los del analizador `char_wb` de scikit-learn (incluidas las palabras
    más cortas que n, los espacios repetidos y la ñ)."""
    esperado = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(2, 5), lowercase=True, strip_accents="unicode"
    ).build_analyzer()(texto)
    assert tc.char_wb_ngrams(texto, 2, 5) == esperado


def test_normalizar_quita_tildes_y_enie_y_pasa_a_minusculas():
    """Sin tildes ni mayúsculas; la ñ pasa a n."""
    assert tc.normalizar("PIZZERÍA Ñandú") == "pizzeria nandu"


# ---- el modelo de numpy reproduce a scikit-learn -----------------------------------------------------------------
def test_las_probabilidades_coinciden_con_scikit_learn_en_todas_las_frases(datos, modelo):
    """Para todas las frases del proyecto, las probabilidades de la inferencia de solo numpy difieren de las de
    scikit-learn en menos de 1e-9."""
    tr, ev = datos
    frases = list(ev["frase"]) + list(tr["frase"]) + ["", "xyz", "pizeria"]
    clases, esperado = tt.probabilidades_sklearn(list(tr["frase"]), list(tr["categoria"]), frases)
    assert clases == modelo.clases
    obtenido = np.array([[modelo.probabilidades(f)[c] for c in clases] for f in frases])
    assert np.abs(obtenido - esperado).max() < 1e-9


def test_las_probabilidades_suman_uno_y_un_texto_desconocido_no_falla(modelo):
    """Un texto sin ningún n-grama conocido da una distribución válida (solo el intercepto)."""
    for texto in ("pizzería", "zzzzqqqq", "日本語"):
        p = modelo.probabilidades(texto)
        assert sum(p.values()) == pytest.approx(1.0) and all(v >= 0 for v in p.values())


def test_una_frase_clara_se_clasifica_y_devuelve_su_confianza(modelo):
    """«una farmacia» se clasifica como hospital con confianza alta."""
    categoria, confianza = modelo.clasificar("una farmacia")
    assert categoria == "hospital" and 0.5 < confianza <= 1.0


def test_texto_vacio_o_en_blanco_no_responde(modelo):
    """Sin texto no hay respuesta ni confianza."""
    assert (
        modelo.clasificar("") == (None, 0.0)
        and modelo.clasificar("   ") == (None, 0.0)
        and modelo.clasificar(None) == (None, 0.0)
    )


def test_gana_ninguna_y_no_responde(modelo):
    """Una frase que no describe un negocio no recibe categoría."""
    categoria, _ = modelo.clasificar("hola buenos días")
    assert categoria is None


def test_por_debajo_del_umbral_no_responde_y_el_umbral_se_puede_cambiar(modelo):
    """Con un umbral imposible no se responde; con uno nulo responde si la clase ganadora no es «ninguna»."""
    assert modelo.clasificar("una farmacia", umbral=1.01)[0] is None
    assert modelo.clasificar("una farmacia", umbral=0.0)[0] == "hospital"
    por_defecto = modelo.umbral
    try:
        modelo.umbral = 1.01
        assert modelo.clasificar("una farmacia")[0] is None
    finally:
        modelo.umbral = por_defecto


# ---- (de)serialización -------------------------------------------------------------------------------------------
def test_guardar_y_cargar_da_el_mismo_modelo(modelo, tmp_path):
    """El JSON conserva todo: las probabilidades son idénticas y el archivo usa LF."""
    ruta = tmp_path / "m.json"
    modelo.save(ruta)
    cargado = tc.ModeloTexto.load(ruta)
    for f in ("una farmacia", "pizeria", "hola"):
        assert cargado.probabilidades(f) == modelo.probabilidades(f)
    assert cargado.umbral == modelo.umbral and cargado.clases == modelo.clases and b"\r" not in ruta.read_bytes()


def test_un_formato_o_unas_dimensiones_incoherentes_se_rechazan(modelo):
    """Un modelo de otro formato o con coeficientes que no cuadran con el vocabulario no se carga."""
    d = modelo.to_dict()
    with pytest.raises(ValueError):
        tc.ModeloTexto.from_dict({**d, "formato": 99})
    with pytest.raises(ValueError):
        tc.ModeloTexto.from_dict({**d, "idf": d["idf"][:-1]})


def test_el_modulo_de_inferencia_no_importa_scikit_learn():
    """El dashboard debe poder cargar el modelo sin scikit-learn."""
    codigo = (
        "import sys; sys.path.insert(0, sys.argv[1]); import src.ml.text_classifier; "
        "sys.exit(1 if any(m.split('.')[0] == 'sklearn' for m in sys.modules) else 0)"
    )
    assert subprocess.run([sys.executable, "-c", codigo, str(ROOT)]).returncode == 0


# ---- métricas y regla de decisión --------------------------------------------------------------------------------
REALES = ["hospital", "school", "ninguna", "ninguna", "sport"]


def test_aciertos_equivocadas_y_perdidas_tienen_el_significado_documentado():
    """Una frase fuera de alcance se acierta no respondiendo; responderle es una respuesta equivocada; no responder a un
    negocio es una pérdida, no un error."""
    resp = ["hospital", None, None, "school", "school"]
    assert tt.aciertos(resp, REALES).tolist() == [1, 0, 1, 0, 0]
    assert tt.equivocadas(resp, REALES).tolist() == [0, 0, 0, 1, 1]
    assert tt.perdidas(resp, REALES).tolist() == [0, 1, 0, 0, 0]
    assert tt.resumen(resp, REALES) == {"exactitud": 0.4, "equivocadas": 0.4, "sin_respuesta": 0.2}


def test_el_hibrido_prefiere_las_palabras_clave_y_usa_el_modelo_solo_si_se_abstienen():
    """Donde las palabras clave responden, manda su respuesta aunque el modelo diga otra cosa."""
    assert tt.hibrido(["a", None, None, "b"], ["x", "y", None, None]) == ["a", "y", None, "b"]


def test_respuesta_aplica_la_abstencion():
    """Gana «ninguna» o no llega al umbral: None."""
    clases = ["hospital", "ninguna", "school"]
    p = np.array([[0.7, 0.2, 0.1], [0.2, 0.7, 0.1], [0.4, 0.3, 0.3]])
    assert tt.respuesta(clases, p, 0.5) == ["hospital", None, None]
    assert tt.respuesta(clases, p, 0.3) == ["hospital", None, "hospital"]
    assert tt.respuesta(clases, np.array([[0.5, 0.3, 0.2]]), 0.5) == ["hospital"]  # justo en el umbral: responde


def test_elegir_umbral_toma_el_mas_bajo_que_no_pasa_de_las_equivocadas_de_las_palabras_mas_la_tolerancia():
    """El umbral es el más bajo cuyo híbrido no comete más respuestas equivocadas que las palabras clave (+2 puntos).
    Aquí las palabras no responden nunca (0 equivocadas): a 0,6 o menos el clasificador contesta «hospital» a dos
    frases fuera de alcance (2 de 3 equivocadas); a 0,65 se abstiene y deja de equivocarse."""
    clases = ["hospital", "ninguna"]
    p = np.array([[0.6, 0.4], [0.6, 0.4], [0.9, 0.1]])
    assert tt.elegir_umbral(clases, p, ["ninguna", "ninguna", "hospital"], [None, None, None]) == 0.65


def test_elegir_umbral_la_tolerancia_incluye_el_borde_y_se_pasa_a_la_siguiente_rejilla():
    """Con 98 frases de hospital bien respondidas y 2 fuera de alcance respondidas mal (2 %), el borde de la tolerancia
    (palabras 0 % + 2 puntos) se cumple y sale el umbral más bajo; con 3 mal (3 %) ya no y hay que subirlo."""
    clases = ["hospital", "ninguna"]
    p = np.array([[0.9, 0.1]] * 98 + [[0.5, 0.5]] * 2)
    sin_palabras = [None] * 100
    assert tt.elegir_umbral(clases, p, ["hospital"] * 98 + ["ninguna"] * 2, sin_palabras) == tt.UMBRALES[0]
    p3 = np.array([[0.9, 0.1]] * 97 + [[0.5, 0.5]] * 3)
    assert tt.elegir_umbral(clases, p3, ["hospital"] * 97 + ["ninguna"] * 3, sin_palabras) == 0.55


def test_elegir_umbral_si_ninguno_cumple_toma_el_mas_alto():
    """Una frase fuera de alcance a la que el clasificador responde con 0,99 se contesta mal con cualquier umbral: sin
    umbral válido se elige el más alto (el más prudente), no el más bajo."""
    clases = ["hospital", "ninguna"]
    p = np.array([[0.99, 0.01], [0.99, 0.01]])
    assert tt.elegir_umbral(clases, p, ["ninguna", "hospital"], [None, None]) == tt.UMBRALES[-1]


def test_elegir_umbral_mide_el_hibrido_no_el_clasificador_solo():
    """Si las palabras clave ya responden bien una frase, lo que el clasificador diría de ella no cuenta: el híbrido solo
    lo consulta cuando las palabras se abstienen. Aquí el clasificador solo se equivocaría siempre, el híbrido nunca."""
    clases = ["hospital", "school"]
    p = np.array([[0.1, 0.9], [0.1, 0.9]])
    assert tt.elegir_umbral(clases, p, ["hospital", "hospital"], ["hospital", "hospital"]) == tt.UMBRALES[0]

def test_bootstrap_pareado_con_diferencia_constante_y_con_diferencia_nula():
    """Si a acierta siempre y b nunca, el IC es [1, 1]; si son iguales, la diferencia es 0."""
    a, b = np.ones(30), np.zeros(30)
    r = tt.bootstrap_pareado(a, b, 500)
    assert r["diferencia"] == 1.0 and r["ic_inf"] == r["ic_sup"] == 1.0
    assert tt.bootstrap_pareado(a, a, 500) == {"diferencia": 0.0, "ic_inf": 0.0, "ic_sup": 0.0}


def test_la_regla_adopta_solo_si_mejora_y_no_sube_los_errores():
    """Las tres salidas posibles de la regla fijada: adoptar, fallar por exactitud y fallar por errores."""
    reales = ["hospital"] * 40
    palabras = [None] * 40  # no responde nunca
    bueno = ["hospital"] * 40  # acierta siempre
    assert tt.decidir(palabras, bueno, reales, 300)["adoptar"] is True
    igual = tt.decidir(palabras, palabras, reales, 300)
    assert igual["adoptar"] is False and igual["cumple_exactitud"] is False
    malo = ["school"] * 20 + ["hospital"] * 20  # mejora la exactitud pero 50 % de errores
    d = tt.decidir(palabras, malo, reales, 300)
    assert d["cumple_exactitud"] is True and d["cumple_errores"] is False and d["adoptar"] is False


def test_la_tolerancia_de_errores_es_de_dos_puntos():
    """Justo en la tolerancia (+2 puntos) todavía cumple; por encima, no."""
    reales = ["hospital"] * 100
    palabras = ["hospital"] * 90 + [None] * 10
    dentro = ["hospital"] * 90 + ["school"] * 2 + ["hospital"] * 8
    fuera = ["hospital"] * 90 + ["school"] * 3 + ["hospital"] * 7
    assert tt.decidir(palabras, dentro, reales, 200)["cumple_errores"] is True
    assert tt.decidir(palabras, fuera, reales, 200)["cumple_errores"] is False


def test_por_tipo_agrupa_las_metricas():
    """Una fila por tipo con su número de frases y sus tasas."""
    t = tt.por_tipo(["hospital", None, "school"], ["hospital", "school", "school"], ["directa", "directa", "errata"])
    assert (
        t.loc["directa", "n"] == 2 and t.loc["directa", "exactitud"] == 0.5 and t.loc["directa", "sin_respuesta"] == 0.5
    )
    assert t.loc["errata", "exactitud"] == 1.0


# ---- los datos ---------------------------------------------------------------------------------------------------
def test_los_datos_versionados_son_validos_y_el_conjunto_de_evaluacion_es_el_prometido(datos):
    """Sin categorías raras, sin repetidas, sin frases en ambos conjuntos; ≥200 frases de evaluación con los cinco tipos
    del diseño y las siete categorías más las fuera de alcance."""
    tr, ev = datos
    assert etc.validar_datos(tr, ev) == []
    assert len(ev) >= 200 and set(ev["tipo"]) == {"directa", "sinonimo", "errata", "larga", "fuera"}
    assert set(ev["categoria"]) == set(etc.CATEGORIAS) | {"ninguna"} and set(tr["categoria"]) == set(ev["categoria"])
    assert (ev.loc[ev["tipo"] == "fuera", "categoria"] == "ninguna").all()
    assert not (ev.loc[ev["tipo"] != "fuera", "categoria"] == "ninguna").any()


def test_validar_datos_detecta_cada_problema():
    """Categoría desconocida, frases repetidas o vacías, y fuga de evaluación a entrenamiento."""
    tr = pd.DataFrame({"categoria": ["hospital", "school"], "frase": ["una farmacia", "un colegio"]})
    ev = pd.DataFrame(
        {"tipo": ["directa", "directa"], "categoria": ["hospital", "sport"], "frase": ["Una Farmacia ", "un gimnasio"]}
    )
    assert any("están a la vez" in p for p in etc.validar_datos(tr, ev))
    assert any(
        "desconocidas" in p for p in etc.validar_datos(tr, ev.assign(categoria=["hospital", "xx"], frase=["a", "b"]))
    )
    assert any("vacías o repetidas" in p for p in etc.validar_datos(tr, ev.assign(frase=["a", "a"])))
    assert any("vacías o repetidas" in p for p in etc.validar_datos(tr, ev.assign(frase=["a", " "])))


# ---- la evaluación de punta a punta ------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def resultado(datos):
    """Una evaluación completa (con la red). Para que la suite no tarde, la red usa una sola semilla aquí."""
    tr, ev = datos
    semillas = tt.MLP_SEMILLAS
    tt.MLP_SEMILLAS = 1
    try:
        return etc.evaluar(tr, ev, n_boot=300)
    finally:
        tt.MLP_SEMILLAS = semillas


def test_la_decision_es_la_regla_aplicada_a_las_cifras(resultado):
    """`adoptar` es la conjunción de las dos condiciones y las cifras del resumen son las de los sistemas."""
    d = resultado["decision"]
    assert d["adoptar"] == (d["cumple_exactitud"] and d["cumple_errores"])
    assert d["cumple_exactitud"] == (d["exactitud"]["ic_inf"] > 0)
    assert d["cumple_errores"] == (
        d["equivocadas_candidato"] <= d["equivocadas_palabras"] + tt.TOLERANCIA_ERRORES + 1e-12
    )
    assert resultado["resumen"]["palabras"]["equivocadas"] == pytest.approx(d["equivocadas_palabras"])
    assert resultado["resumen"]["hibrido"]["equivocadas"] == pytest.approx(d["equivocadas_candidato"])


def test_el_hibrido_nunca_cambia_una_respuesta_de_las_palabras_clave(resultado):
    """Donde las palabras clave responden, el híbrido da lo mismo."""
    for p, h in zip(resultado["sistemas"]["palabras"], resultado["sistemas"]["hibrido"]):
        if p is not None:
            assert h == p


def test_el_umbral_no_depende_de_la_evaluacion(datos, resultado):
    """El umbral sale solo del entrenamiento: si se barajan las etiquetas de la evaluación no cambia."""
    tr, ev = datos
    barajada = ev.assign(categoria=list(ev["categoria"].sample(frac=1, random_state=1)))
    otro = etc.evaluar(tr, barajada, n_boot=50, con_mlp=False)
    assert otro["umbral"]["logistica"] == resultado["umbral"]["logistica"]


def test_ninguna_frase_de_evaluacion_entra_en_el_entrenamiento(datos, resultado):
    """El vocabulario del modelo sale solo del entrenamiento: añadir una frase con n-gramas inéditos a la evaluación no lo cambia."""
    tr, ev = datos
    extra = pd.concat(
        [ev, pd.DataFrame({"tipo": ["directa"], "categoria": ["business"], "frase": ["xqzvwkj"]})], ignore_index=True
    )
    assert etc.evaluar(tr, extra, n_boot=50, con_mlp=False)["modelo"].vocabulario == resultado["modelo"].vocabulario


def test_la_evaluacion_es_determinista(datos, resultado):
    """Mismos datos y semilla, mismas cifras."""
    tr, ev = datos
    otra = etc.evaluar(tr, ev, n_boot=300, con_mlp=False)
    for sistema in ("palabras", "logistica", "hibrido"):
        assert otra["resumen"][sistema] == resultado["resumen"][sistema]


def test_la_sensibilidad_recorre_los_umbrales_y_a_mayor_umbral_menos_respuestas(resultado):
    """A mayor umbral el híbrido responde menos (más «sin respuesta»); la tabla es descriptiva."""
    s = resultado["sensibilidad"]
    assert [x["umbral"] for x in s] == list(tt.UMBRALES)
    assert s[-1]["sin_respuesta"] >= s[0]["sin_respuesta"]


def test_main_imprime_la_decision_y_exporta_modelo_y_manifiesto(tmp_path, capsys):
    """La herramienta termina bien, imprime la decisión, y con --exportar escribe un modelo cuyo hash está en el manifiesto
    y que se carga y clasifica."""
    assert etc.main(["--boot", "200", "--sin-mlp", "--exportar", str(tmp_path)]) == 0
    salida = capsys.readouterr().out
    assert "DECISIÓN:" in salida and "Sensibilidad al umbral" in salida
    m = json.loads((tmp_path / "text_classifier_manifest.json").read_text(encoding="utf-8"))
    assert m["modelo"]["sha256"] == etc.file_hash(tmp_path / "text_classifier.json")
    assert m["datos"]["entrenamiento"]["sha256"] == etc.file_hash(etc.ENTRENAMIENTO) and "optimista" in m["advertencia"]
    assert m["adoptado"] == ("NO se adopta" not in salida)  # el manifiesto dice lo mismo que la decisión impresa
    assert m["umbral"] in tt.UMBRALES
    assert tc.ModeloTexto.load(tmp_path / "text_classifier.json").clasificar("una farmacia")[0] == "hospital"


def test_main_se_niega_a_evaluar_con_datos_invalidos(tmp_path, capsys):
    """Si una frase de evaluación está también en el entrenamiento, no se evalúa."""
    tr, ev = etc.cargar()
    ev.loc[0, "frase"] = tr.loc[0, "frase"]
    ruta = tmp_path / "ev.psv"
    ev.to_csv(ruta, sep="|", index=False)
    assert etc.main(["--evaluacion", str(ruta)]) == 1
    assert "no son válidos" in capsys.readouterr().out


def test_sin_mlp_se_omiten_la_red_y_su_comparacion(datos):
    """Con con_mlp=False no hay sistema MLP, ni su umbral, ni la comparación logística-MLP; el resto se calcula igual."""
    tr, ev = datos
    r = etc.evaluar(tr, ev, n_boot=50, con_mlp=False)
    assert (
        set(r["sistemas"]) == {"palabras", "logistica", "hibrido"}
        and r["umbral"]["mlp"] is None
        and r["logistica_vs_mlp"] is None
    )


def test_con_mlp_se_comparan_la_red_y_la_logistica(resultado):
    """Con la red incluida hay umbral propio, sistema híbrido con la red y la comparación pareada."""
    assert {"mlp", "hibrido_mlp"} <= set(resultado["sistemas"]) and resultado["umbral"]["mlp"] in tt.UMBRALES
    assert set(resultado["logistica_vs_mlp"]) == {"diferencia", "ic_inf", "ic_sup"}


def test_la_regla_exige_que_el_intervalo_quede_por_encima_de_cero_no_solo_la_media():
    """Una mejora pequeña (2 aciertos más de 40) tiene media positiva pero un IC que llega a 0: no cumple la exactitud."""
    reales = ["hospital"] * 40
    palabras = ["hospital"] * 38 + [None] * 2
    candidato = ["hospital"] * 40
    d = tt.decidir(palabras, candidato, reales, 2000)
    assert d["exactitud"]["diferencia"] > 0 and d["exactitud"]["ic_inf"] <= 0 and d["cumple_exactitud"] is False


def test_el_bootstrap_da_un_intervalo_con_anchura_que_contiene_la_media():
    """Con diferencias variables el IC tiene anchura positiva y rodea a la media."""
    d = np.array([1.0] * 12 + [0.0] * 20 + [-1.0] * 8)
    r = tt.bootstrap_pareado(d, np.zeros(40), 2000)
    assert r["ic_inf"] < r["diferencia"] < r["ic_sup"] and r["ic_sup"] - r["ic_inf"] > 0.1


def test_el_softmax_es_estable_con_logits_enormes():
    """Con coeficientes gigantes no hay desbordamiento: las probabilidades siguen siendo válidas."""
    m = tc.ModeloTexto(["a", "b"], {" x ": 0}, np.array([1.0]), np.array([[1000.0], [-1000.0]]), np.zeros(2), (3, 3))
    p = m.probabilidades("x")
    assert p["a"] == pytest.approx(1.0) and p["b"] == pytest.approx(0.0) and np.isfinite(list(p.values())).all()
