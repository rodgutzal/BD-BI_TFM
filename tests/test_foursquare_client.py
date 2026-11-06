"""Pruebas de la categorización y de los puntos de búsqueda de Foursquare.

No hacen llamadas de red: solo ejercitan la lógica pura del cliente.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.foursquare_client import FoursquareClient, build_search_points
from src.locations import LOCATIONS, ROUTES


def _cat(nombre):
    return FoursquareClient._categorize([{"name": nombre}])


@pytest.mark.parametrize(
    "nombre, esperado",
    [
        ("Pizzeria", "restaurant"),
        ("Coffee Shop", "restaurant"),  # "shop" no debe mandarlo a retail
        ("Dessert Shop", "restaurant"),
        ("Bar", "restaurant"),
        ("Hair Salon", "services"),
        ("Bank", "services"),
        ("Hospital", "health"),
        ("Pharmacy", "health"),
        ("Elementary School", "school"),
        ("Department Store", "mall"),  # debe llegar a mall antes que al "store" genérico
        ("Shopping Mall", "mall"),
        ("Food and Beverage Retail", "retail"),  # es una tienda, no un restaurante
        ("Health Food Store", "retail"),
        ("Supermarket", "retail"),
        ("Gym", "entertainment"),
        ("Church", "other"),
        ("Public Park", "other"),
    ],
)
def test_categoriza_nombres_reales_de_foursquare(nombre, esperado):
    assert _cat(nombre) == esperado


def test_barbershop_no_se_confunde_con_bar():
    """Regresión: "bar" dentro de "Barbershop" no puede mandarlo a restaurant
    (se usa \\b, no un simple `in`).

    Limitación conocida: "Barbershop" (una sola palabra) tampoco matchea la
    palabra clave "barber" de `services` y cae en "other"; "Barber Shop" sí
    llega a `services`. Aquí solo se garantiza lo documentado: nunca restaurant.
    """
    assert _cat("Barbershop") != "restaurant"
    assert _cat("Barber Shop") == "services"


def test_nunca_descarta_un_poi_sin_categoria():
    assert FoursquareClient._categorize([]) == "other"
    assert FoursquareClient._categorize(None) == "other"
    assert _cat("Algo Totalmente Desconocido") == "other"


# ---------------------------------------------------------------------------
# build_search_points
# ---------------------------------------------------------------------------

def test_sin_rutas_solo_devuelve_las_zonas():
    puntos = build_search_points(LOCATIONS)
    assert set(puntos) == set(LOCATIONS)


def test_con_las_rutas_actuales_son_27_llamadas():
    """El README documenta 7 zonas + 20 puntos intermedios = 27 llamadas por
    refresco (~117/mes con refresco semanal, 23% del límite gratis)."""
    puntos = build_search_points(LOCATIONS, ROUTES)
    assert len(puntos) == 27
    assert len(puntos) - len(LOCATIONS) == 20


def test_no_duplica_corredores_en_sentido_inverso():
    """Valletta->Birkirkara y Birkirkara->Valletta son el mismo tramo físico."""
    un_sentido = build_search_points(LOCATIONS, [("Valletta", "Birkirkara")])
    ambos = build_search_points(LOCATIONS, [("Valletta", "Birkirkara"), ("Birkirkara", "Valletta")])
    assert len(ambos) == len(un_sentido)


def test_puntos_intermedios_quedan_entre_origen_y_destino():
    puntos = build_search_points(LOCATIONS, [("Msida", "Marsaskala")])
    intermedios = [p for nombre, p in puntos.items() if "km" in nombre]
    assert intermedios, "Msida-Marsaskala (~9.5 km) debe generar puntos intermedios"

    o, d = LOCATIONS["Msida"], LOCATIONS["Marsaskala"]
    for p in intermedios:
        assert min(o.latitude, d.latitude) <= p.latitude <= max(o.latitude, d.latitude)
        assert min(o.longitude, d.longitude) <= p.longitude <= max(o.longitude, d.longitude)


def test_ignora_rutas_con_zonas_desconocidas():
    puntos = build_search_points(LOCATIONS, [("Msida", "Narnia")])
    assert set(puntos) == set(LOCATIONS)


# ---------------------------------------------------------------------------
# _parse_results
# ---------------------------------------------------------------------------

@pytest.fixture
def cliente():
    return FoursquareClient(api_key="clave-falsa")


def test_acepta_la_forma_nueva_de_la_respuesta(cliente):
    pois = cliente._parse_results([{
        "fsq_place_id": "abc", "name": "La Pizzeria", "latitude": 35.9, "longitude": 14.5,
        "categories": [{"name": "Pizzeria"}],
    }])
    assert pois == [{
        "fsq_place_id": "abc", "category": "restaurant", "subcategory": "Pizzeria",
        "name": "La Pizzeria", "latitude": 35.9, "longitude": 14.5,
    }]


def test_acepta_la_forma_antigua_con_geocodes(cliente):
    pois = cliente._parse_results([{
        "fsq_id": "xyz", "name": "Farmacia", "categories": [{"name": "Pharmacy"}],
        "geocodes": {"main": {"latitude": 35.8, "longitude": 14.4}},
    }])
    assert len(pois) == 1
    assert pois[0]["fsq_place_id"] == "xyz"
    assert (pois[0]["latitude"], pois[0]["longitude"]) == (35.8, 14.4)
    assert pois[0]["category"] == "health"


def test_descarta_lugares_sin_id_o_sin_coordenadas(cliente):
    pois = cliente._parse_results([
        {"name": "Sin id", "latitude": 35.9, "longitude": 14.5, "categories": []},
        {"fsq_place_id": "sin-coords", "name": "Sin coords", "categories": []},
    ])
    assert pois == []


def test_cliente_exige_api_key():
    with pytest.raises(ValueError):
        FoursquareClient(api_key="")
