"""Tests de la licencia del repositorio: el archivo LICENSE, su declaración en setup.py y su mención en el README."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _leer(nombre):
    return (ROOT / nombre).read_text(encoding="utf-8")


def test_el_archivo_license_es_el_texto_estandar_de_mit_con_el_titular():
    """LICENSE existe, es MIT y lleva el año y el titular elegidos (rodgutzal)."""
    texto = _leer("LICENSE")
    assert texto.startswith("MIT License")
    assert "Copyright (c) 2026 rodgutzal" in texto
    # las tres partes que hacen que sea MIT: la concesión, la condición de conservar el aviso y la exención de garantías
    assert "Permission is hereby granted, free of charge" in texto
    assert "The above copyright notice and this permission notice shall be included" in texto
    assert 'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND' in texto


def test_setup_declara_la_licencia_mit_y_no_un_clasificador_obsoleto():
    """setup.py declara license="MIT" (expresión SPDX). No usa el clasificador "License :: ...", obsoleto en
    setuptools moderno, ni conserva el comentario que decía que el repo no tenía licencia."""
    setup = _leer("setup.py")
    assert re.search(r'license\s*=\s*"MIT"', setup)
    assert not re.search(r'^\s*"License :: OSI', setup, flags=re.MULTILINE)  # un clasificador real, no el comentario
    assert "no tiene archivo LICENSE" not in setup


def test_el_readme_enlaza_la_licencia_y_avisa_de_que_no_cubre_los_datos_de_terceros():
    """El README dice que el código es MIT, enlaza LICENSE y advierte de que la licencia no cubre datos de terceros."""
    readme = _leer("README.md")
    seccion = readme.split("## Licencia", 1)[1].split("\n## ", 1)[0]
    assert "MIT" in seccion and "(LICENSE)" in seccion
    assert "no relicencia" in seccion and "ODbL" in seccion
    for proveedor in ("TomTom", "OpenRouteService", "OpenWeather", "Foursquare"):
        assert proveedor in seccion


def test_los_datos_de_terceros_que_el_readme_dice_que_estan_en_el_repositorio_existen():
    """El README enumera datos de terceros versionados; si se retiran del repositorio, el aviso debe actualizarse."""
    readme = _leer("README.md")
    seccion = readme.split("## Licencia", 1)[1].split("\n## ", 1)[0]
    for ruta in re.findall(r"`(data/[\w/.\-]+\.csv)`", seccion):
        assert (ROOT / ruta).exists(), f"El README menciona {ruta}, que ya no existe: actualiza la sección Licencia"
