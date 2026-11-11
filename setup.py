#!/usr/bin/env python
"""Setup script for Urban Mobility Analytics.

El proyecto está pensado para ejecutarse DESDE EL CLON del repositorio (o con
Docker): `src/` calcula sus rutas de datos (`data/`, `logs/`) respecto a la
raíz del repo. Por eso, para usar los comandos de consola de abajo, instala en
modo editable:

    pip install -e .

Con una instalación normal (no editable) esas rutas apuntarían a site-packages.
"""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="urban-mobility-analytics",
    version="1.0.0",
    author="Equipo BD-BI TFM (MBDIB)",
    description="Real-time traffic and weather monitoring dashboard for Malta routes",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rodgutzal/BD-BI_TFM",
    # `tests` no debe instalarse como paquete de nivel superior en site-packages.
    packages=find_packages(exclude=["tests", "tests.*"]),
    # train_models.py vive en la raíz (no dentro de un paquete): sin esto el
    # comando `urban-mobility-train` apuntaba a un módulo que no se instalaba.
    py_modules=["train_models"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        # Sin clasificador de licencia a propósito: el repo no tiene archivo LICENSE.
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering :: GIS",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.11",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "urban-mobility-collect=src.route_extraction:main",
            "urban-mobility-migrate=src.migration:main",
            "urban-mobility-analyze=src.analytics:main",
            "urban-mobility-train=train_models:main",
        ],
    },
    include_package_data=True,
    package_data={
        "src": ["models/trained/*.pkl"],
    },
)
