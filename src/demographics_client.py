"""Cliente de Google Data Commons para datos demográficos (población) por
zona — fuente COMPLEMENTARIA, diseñada para transicionar a otras ciudades
SIN cambiar código: en vez de depender de conocer de antemano el DCID
(Data Commons ID) de cada lugar, resuelve por NOMBRE vía la API la primera
vez que ve una zona nueva, y ese DCID se cachea en `zone_demographics.dcid`
(ver database.py) para no volver a resolverlo en corridas siguientes.

Por qué Google Data Commons: agrega datos oficiales (censos nacionales,
Banco Mundial, ONU, etc.) bajo un esquema único. Confirmado con búsquedas
específicas que tiene páginas propias para localidades de Malta
(Birkirkara, Sliema) — no solo a nivel país.

Por qué el paquete oficial `datacommons-client` y no `requests` directo
(a diferencia de los demás clientes de este proyecto): la respuesta REST
V2 de Data Commons tiene una estructura anidada compleja
(byVariable -> byEntity -> orderedFacets -> observations) que el cliente
oficial ya parsea de forma confiable — reimplementar ese parseo a mano
tendría más riesgo de error que beneficio.

Variable estadística usada: Count_Person (población total) — la misma que
usa la documentación oficial en sus ejemplos.

Requiere una API key GRATUITA Y PROPIA (autoservicio):
https://apikeys.datacommons.org — pedirla para el dominio
api.datacommons.org. NO usar la "trial key" que aparece pública en la
documentación: está compartida entre todo el que lea esos mismos docs y
tiene cuota muy limitada, no pensada para un recolector programado.

ESTADO DE VALIDACIÓN: probado contra la API real (datacommons-client 2.1.6):
las 7 zonas de Malta se resuelven por nombre y su población está cargada en
`zone_demographics` / `zone_population_history`. Lo aprendido en esas
pruebas, y que el código ya contempla (detalle en el README, sección
"Troubleshooting"):
  - la key hay que pasarla de forma EXPLÍCITA al constructor; dejarla solo en
    la variable de entorno DC_API_KEY da 401 "unregistered callers" en las
    consultas de observación;
  - `date="latest"` puede devolver un dato menos reciente que otro de la misma
    serie (Valletta: 2014 frente a 2021), de ahí fetch_population_history() y
    el reconciliado a un año común de demographics_extraction.py;
  - resolve_dcid() toma el primer candidato que devuelve la API: al agregar
    una ciudad o zona nueva, revisar a ojo el nombre que Data Commons le
    asocia (`dc_name`, que se registra en el log) por si hay una homónima.
"""

import inspect
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

POPULATION_VARIABLE_DCID = "Count_Person"


def _clean(value) -> str:
    """Texto limpio de una celda de DataFrame (None/NaN -> cadena vacía)."""
    if value is None or value != value:
        return ""
    return str(value).strip()


class DemographicsClient:
    """Cliente para resolver lugares por nombre y consultar su población
    más reciente en Data Commons."""

    def __init__(self, api_key: str):
        # Limpia espacios/comillas que a veces se cuelan al pegar la key en .env.
        api_key = (api_key or "").strip().strip('"').strip("'")
        if not api_key:
            raise ValueError("DATACOMMONS_API_KEY vacía o no configurada")

        # Respaldo: algunas versiones de la librería leen la key de DC_API_KEY.
        os.environ["DC_API_KEY"] = api_key

        try:
            from datacommons_client import DataCommonsClient
        except ImportError as e:
            raise ImportError(
                "Falta el paquete datacommons-client. Instalar con: "
                "pip install 'datacommons-client[Pandas]'"
            ) from e

        # La key se pasa de forma EXPLÍCITA al constructor. La primera versión
        # de este cliente solo la dejaba en DC_API_KEY y asumía que la librería
        # la leería; en la práctica (datacommons-client 2.1.6) las llamadas de
        # observación llegaron sin identidad (401 "unregistered callers"). Se
        # inspecciona la firma en vez de asumir el nombre del parámetro, para
        # no romper si otra versión lo llama distinto.
        params = [p for p in inspect.signature(DataCommonsClient.__init__).parameters if p != "self"]
        logger.info(
            f"Data Commons: key configurada ({len(api_key)} caracteres); "
            f"parámetros del cliente instalado: {params}"
        )
        if "api_key" in params:
            self._client = DataCommonsClient(api_key=api_key)
        else:
            logger.warning(
                "El DataCommonsClient instalado no acepta `api_key`; se usa solo "
                "DC_API_KEY del entorno (puede fallar con 401)."
            )
            self._client = DataCommonsClient()

    def resolve_dcid(self, place_name: str) -> Optional[str]:
        """Resuelve un nombre de lugar a su DCID. Devuelve None si no hay
        ningún candidato — no lanza excepción, para que una zona nueva sin
        match todavía no tumbe el resto del refresco de las demás zonas."""
        try:
            response = self._client.resolve.fetch_dcids_by_name(names=place_name)
        except Exception as e:
            logger.warning(f"Data Commons resolve falló para '{place_name}': {e}")
            return None

        for entity in getattr(response, "entities", []):
            candidates = getattr(entity, "candidates", [])
            if candidates:
                # Se toma el primer candidato (orden de relevancia que
                # devuelve la propia API) — para las 7 zonas de Malta esto
                # se revisa una vez a mano la primera corrida (ver NOTA
                # arriba); si el match resulta incorrecto para un lugar
                # nuevo, se puede sobreescribir el dcid a mano en la tabla.
                return candidates[0].dcid
        return None

    def fetch_population_history(self, dcids: Dict[str, str]) -> Dict[str, List[dict]]:
        """Serie COMPLETA de población (todas las fechas y todas las fuentes)
        de cada lugar, en vez de solo la observación más reciente.

        Por qué: `date="latest"` devuelve, para cada zona, lo más nuevo que
        exista — y no coincide entre zonas (en Malta: 2014 para la mayoría,
        2019 y 2021 para otras). Para comparar zonas hace falta saber qué
        años existen de verdad y elegir uno común.

        Devuelve {nombre: [{"date", "year", "population", "source"}, ...]}
        ordenado por fecha. Una misma fecha puede venir de varias fuentes
        (`importName` o `facetId`); se conservan todas, deduplicadas.
        """
        if not dcids:
            return {}

        try:
            df = self._client.observations_dataframe(
                variable_dcids=POPULATION_VARIABLE_DCID,
                date="all",
                entity_dcids=list(dcids.values()),
            )
        except Exception as e:
            logger.error(f"Data Commons: falló la consulta de serie completa: {e}")
            return {}

        if df is None or df.empty:
            return {}

        dcid_to_name = {v: k for k, v in dcids.items()}
        history: Dict[str, List[dict]] = {}
        seen = set()
        for _, row in df.iterrows():
            name = dcid_to_name.get(row.get("entity"))
            date = _clean(row.get("date"))
            value = row.get("value")
            if name is None or not date or value is None or value != value:
                continue
            source = _clean(row.get("importName")) or _clean(row.get("facetId"))
            key = (name, date, source)
            if key in seen:
                continue
            seen.add(key)
            year = int(date[:4]) if date[:4].isdigit() else None
            history.setdefault(name, []).append(
                {"date": date, "year": year, "population": int(value), "source": source}
            )

        for rows in history.values():
            rows.sort(key=lambda r: r["date"])
        return history

    def fetch_population(self, dcids: Dict[str, str]) -> Dict[str, dict]:
        """`dcids`: {nombre_de_zona: dcid ya resuelto}. Devuelve
        {nombre_de_zona: {"population": int, "date": str, "dc_name": str}} solo para las
        zonas que tengan una observación disponible."""
        if not dcids:
            return {}

        try:
            df = self._client.observations_dataframe(
                variable_dcids=POPULATION_VARIABLE_DCID,
                date="latest",
                entity_dcids=list(dcids.values()),
            )
        except Exception as e:
            logger.error(f"Data Commons observation fetch falló: {e}")
            return {}

        if df is None or df.empty:
            return {}

        dcid_to_name = {v: k for k, v in dcids.items()}
        result: Dict[str, dict] = {}
        for _, row in df.iterrows():
            name = dcid_to_name.get(row.get("entity"))
            if name is None or row.get("value") is None:
                continue
            result[name] = {
                "population": int(row["value"]),
                "date": str(row.get("date", "")),
                # Nombre que Data Commons asocia a ese DCID: sirve para detectar
                # un match equivocado de la resolución por nombre (ej. una
                # homónima en otro país) revisando el log a ojo.
                "dc_name": str(row.get("entity_name", "") or ""),
            }
        return result
