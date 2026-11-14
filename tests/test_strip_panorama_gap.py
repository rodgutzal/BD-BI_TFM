"""Tests de `tools/strip_panorama_gap.py`: quitar la brecha de oferta de un panorama publicado sin tocar las lentes ni los
conteos (docs/DATOS_Y_LICENCIAS.md)."""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import business_profiles as bp  # noqa: E402
from src.ml import panorama  # noqa: E402
from src.ml.cell_counts import CellCounts  # noqa: E402

_s = importlib.util.spec_from_file_location("strip_panorama_gap", ROOT / "tools" / "strip_panorama_gap.py")
herramienta = importlib.util.module_from_spec(_s)
_s.loader.exec_module(herramienta)

_t = importlib.util.spec_from_file_location("test_ml_panorama_helpers", ROOT / "tests" / "test_ml_panorama.py")
ayudas = importlib.util.module_from_spec(_t)
_t.loader.exec_module(ayudas)

BRECHA = list(panorama.COLUMNAS_BRECHA)


@pytest.fixture
def con_brecha(tmp_path):
    """Un directorio de panorama como el publicado hasta ahora: brecha en food_drink y business."""
    counts = CellCounts.from_pois(ayudas.pois_sinteticos())
    partes = []
    for clave, perfil in bp.DEFAULT_PROFILES.items():
        base = panorama.build_panorama(counts, perfil)
        if clave in ("food_drink", "business"):
            rng = np.random.default_rng(1)
            tabla = pd.DataFrame({c: rng.random(len(base)) for c in BRECHA}, index=base.index)
            base = panorama.build_panorama(counts, perfil, tabla, "boosting", brecha_validada=False)
        partes.append(base)
    manifiesto = {
        "procedencia": {"commit": "abc1234", "entrada_sha256": "e" * 64},
        "parametros": {"repeats": 10, "con_brecha": True, "con_contexto": True},
        "perfiles": list(bp.DEFAULT_PROFILES),
        "brecha": {"food_drink": {"ganador": None, "modelo_brecha": "boosting"}, "business": {"ganador": None}},
        "advertencia": "La brecha de oferta es EXPLORATORIA",
    }
    panorama.write_outputs(tmp_path, pd.concat(partes), counts, manifiesto)
    return tmp_path


def crudo(ruta):
    return pd.read_csv(ruta / "panorama.csv", dtype=str, keep_default_na=False)


def test_el_punto_de_partida_tiene_brecha(con_brecha):
    assert herramienta.tiene_brecha(panorama.read_panorama(con_brecha))
    assert set(crudo(con_brecha).loc[lambda t: t["esperado"] != "", "perfil"]) == {"food_drink", "business"}


def test_quitar_la_brecha_vacia_solo_las_columnas_de_brecha(con_brecha):
    antes = crudo(con_brecha)
    r = herramienta.quitar_brecha(con_brecha)
    despues = crudo(con_brecha)
    assert r["cambiado"] and r["filas"] == len(antes)
    assert (despues[BRECHA + ["modelo_brecha"]] == "").all().all() and (despues["brecha_validada"] == "False").all()
    resto = [c for c in antes.columns if c not in BRECHA + ["modelo_brecha", "brecha_validada"]]
    pd.testing.assert_frame_equal(antes[resto], despues[resto])  # texto idéntico: lentes, orden y filas
    assert list(antes.columns) == list(despues.columns)


def test_cell_counts_no_se_toca_ni_un_byte(con_brecha):
    antes = (con_brecha / "cell_counts.csv").read_bytes()
    herramienta.quitar_brecha(con_brecha)
    assert (con_brecha / "cell_counts.csv").read_bytes() == antes


def test_el_resultado_verifica_y_se_lee_sin_brecha(con_brecha):
    herramienta.quitar_brecha(con_brecha)
    assert panorama.verify_outputs(con_brecha) == []
    p = panorama.read_panorama(con_brecha)
    assert not herramienta.tiene_brecha(p) and p["brecha_validada"].dtype == bool and not p["brecha_validada"].any()
    assert b"\r\n" not in (con_brecha / "panorama.csv").read_bytes()


def test_el_manifiesto_se_actualiza_y_conserva_la_procedencia(con_brecha):
    anterior = json.loads((con_brecha / "panorama_manifest.json").read_text(encoding="utf-8"))
    r = herramienta.quitar_brecha(con_brecha)
    m = json.loads((con_brecha / "panorama_manifest.json").read_text(encoding="utf-8"))
    assert m["parametros"]["con_brecha"] is False and m["parametros"]["repeats"] == 10 and m["brecha"] == {}
    assert m["advertencia"] == "Sin brecha: solo lentes explícitas." and "EXPLORATORIA" not in json.dumps(m)
    assert m["procedencia"] == anterior["procedencia"] and m["perfiles"] == anterior["perfiles"]
    assert m["archivos"]["cell_counts.csv"] == anterior["archivos"]["cell_counts.csv"]
    assert (
        m["archivos"]["panorama.csv"]["sha256"]
        == r["sha256"]
        != r["sha256_anterior"]
        == anterior["archivos"]["panorama.csv"]["sha256"]
    )
    assert m["derivado"]["panorama_sha256_anterior"] == r["sha256_anterior"] and "TomTom" in m["derivado"]["motivo"]


def test_es_idempotente(con_brecha):
    herramienta.quitar_brecha(con_brecha)
    bytes_p = (con_brecha / "panorama.csv").read_bytes()
    bytes_m = (con_brecha / "panorama_manifest.json").read_bytes()
    r = herramienta.quitar_brecha(con_brecha)
    assert r["cambiado"] is False and r["sha256"] == r["sha256_anterior"]
    assert (con_brecha / "panorama.csv").read_bytes() == bytes_p and (
        con_brecha / "panorama_manifest.json"
    ).read_bytes() == bytes_m


def test_se_niega_si_el_panorama_no_coincide_con_su_manifiesto_y_no_toca_nada(con_brecha):
    (con_brecha / "panorama.csv").write_text("alterado\n", encoding="utf-8")
    antes = {p.name: p.read_bytes() for p in con_brecha.iterdir()}
    with pytest.raises(ValueError, match="no coincide con su manifiesto"):
        herramienta.quitar_brecha(con_brecha)
    assert {p.name: p.read_bytes() for p in con_brecha.iterdir()} == antes


def test_un_directorio_sin_panorama_es_un_error(tmp_path):
    with pytest.raises(ValueError):
        herramienta.quitar_brecha(tmp_path)


def test_el_resultado_es_lo_que_daria_el_panorama_sin_brecha_de_la_herramienta_de_construccion(con_brecha):
    """Misma representación de las columnas de brecha que `build_panorama(...)` sin tabla de brecha."""
    herramienta.quitar_brecha(con_brecha)
    p = panorama.read_panorama(con_brecha)
    base = panorama.build_panorama(panorama.read_counts(con_brecha), bp.get_default_profile("food_drink"))
    fila = p[p["perfil"] == "food_drink"].iloc[0]
    esperada = base.reset_index().iloc[0]
    for c in BRECHA:
        assert pd.isna(fila[c]) and pd.isna(esperada[c])
    assert (
        fila["modelo_brecha"] == esperada["modelo_brecha"] == ""
        and fila["brecha_validada"] == esperada["brecha_validada"] == False
    )  # noqa: E712


def test_main_imprime_y_devuelve_codigos(con_brecha, capsys, tmp_path):
    assert herramienta.main(["--dir", str(con_brecha)]) == 0
    assert "Brecha retirada" in capsys.readouterr().out
    assert herramienta.main(["--dir", str(con_brecha)]) == 0
    assert "ya no tiene brecha" in capsys.readouterr().out
    assert herramienta.main(["--dir", str(tmp_path / "no_existe")]) == 1
    assert "ERROR" in capsys.readouterr().out


def test_tiene_brecha_detecta_cualquiera_de_sus_columnas():
    base = pd.DataFrame({c: [np.nan, np.nan] for c in BRECHA})
    base["modelo_brecha"] = ["", ""]
    assert herramienta.tiene_brecha(base) is False
    for c in BRECHA:
        otra = base.copy()
        otra.loc[0, c] = 0.5
        assert herramienta.tiene_brecha(otra) is True, c
    solo_modelo = base.copy()
    solo_modelo.loc[1, "modelo_brecha"] = "boosting"
    assert herramienta.tiene_brecha(solo_modelo) is True


def test_si_la_tabla_ya_no_tiene_brecha_pero_el_manifiesto_la_declara_se_corrige_el_manifiesto(con_brecha):
    """Estado a medias (p. ej. una ejecución interrumpida): no se da por hecho solo porque la tabla esté vacía."""
    herramienta.quitar_brecha(con_brecha)
    ruta = con_brecha / "panorama_manifest.json"
    m = json.loads(ruta.read_text(encoding="utf-8"))
    m["brecha"] = {"food_drink": {"ganador": None}}
    ruta.write_text(json.dumps(m), encoding="utf-8")
    assert herramienta.quitar_brecha(con_brecha)["cambiado"] is True
    assert json.loads(ruta.read_text(encoding="utf-8"))["brecha"] == {}


def test_si_el_manifiesto_dice_con_brecha_true_se_corrige_aunque_la_tabla_este_vacia(con_brecha):
    herramienta.quitar_brecha(con_brecha)
    ruta = con_brecha / "panorama_manifest.json"
    m = json.loads(ruta.read_text(encoding="utf-8"))
    m["parametros"]["con_brecha"] = True
    ruta.write_text(json.dumps(m), encoding="utf-8")
    assert herramienta.quitar_brecha(con_brecha)["cambiado"] is True
    assert json.loads(ruta.read_text(encoding="utf-8"))["parametros"]["con_brecha"] is False
