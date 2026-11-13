# Datos y licencias

El **código** de este repositorio es MIT (ver [`LICENSE`](../LICENSE)). Los **datos** que incluye no son del autor y tienen sus propias condiciones, que este documento resume. No es asesoría legal: son lecturas de los textos oficiales de cada proveedor, hechas en noviembre de 2026; si publicas o reutilizas los datos, comprueba la versión vigente.

## Qué datos hay en el repositorio y bajo qué condiciones

| Archivo | Origen | Condición |
|---|---|---|
| `notebooks/mobility_data_sample_ors_openweather.csv` | Mediciones de rutas de OpenRouteService (HeiGIT) con clima de OpenWeather, sin la geometría de la ruta | Resultados de ORS: **CC BY-SA 4.0**. Datos de OpenWeather guardados y publicados: **ODbL** (base de datos adaptada, con *share-alike*). Ambas exigen atribución |
| `data/raw/legacy_ors_traffic_weather_data.csv`, `data/raw/traffic_weather_data.csv` | Histórico heredado de ORS y OpenWeather (mayo de 2026) | Igual que la fila anterior |
| `data/ml/cell_counts.csv` | Conteos de POIs de OpenStreetMap por celda | **ODbL** (OpenStreetMap), con atribución y *share-alike* |
| `data/ml/panorama.csv` | Conteos de OpenStreetMap más salidas del modelo exploratorio (brecha de oferta). **Ver «Punto abierto»** | ODbL para la parte de OpenStreetMap; el resto, sin resolver |
| `data/text/frases_entrenamiento.psv`, `frases_evaluacion.psv` | Frases de entrenamiento y de la primera evaluación del clasificador, escritas por el autor | MIT |
| `data/text/frases_evaluacion_v2.psv`, `data/text/evaluacion_v2/` | 200 frases de evaluación y los prompts usados, generados por Codex (un modelo de OpenAI) y etiquetados a ciegas por otra sesión | Salida de un modelo de lenguaje a partir de definiciones propias, sin datos de terceros; se publican bajo MIT con el aviso de su origen |
| `data/ml/text_classifier.json`, `text_classifier_manifest.json` | Clasificador de texto (regresión logística sobre n-gramas de caracteres) entrenado solo con las frases del autor | MIT |

**Atribución requerida:**

- © colaboradores de OpenStreetMap, datos bajo la [ODbL](https://opendatacommons.org/licenses/odbl/) (<https://www.openstreetmap.org/copyright>).
- © openrouteservice by HeiGIT | Data from OpenStreetMap (<https://account.heigit.org/info/tos>).
- Datos meteorológicos: OpenWeather (<https://openweathermap.org/guide>).

Al ser datos con *share-alike*, quien redistribuya una versión adaptada de ellos debe hacerlo bajo la misma licencia. La licencia MIT del código **no** los relicencia.

## Qué NO está en el repositorio: datos de TomTom

Los términos del portal de TomTom prohíben almacenar y redistribuir los resultados de su API: la cláusula 11.4 prohíbe cachear o almacenar resultados salvo en cachés de cliente de corta vida, la 11.6.1 prohíbe crear bases de datos derivadas con su contenido, y la 20.2.3 prohíbe combinarlo con datos que lo sometan a una licencia *copyleft* (como las ODbL y CC BY-SA de arriba). Por eso **no se publican** ni el histórico heredado (`legacy_tomtom_route_weather_data.csv`) ni las filas TomTom de la muestra de los *notebooks*, ni la salida HTML del `.Rmd` (sus tablas incluían filas de TomTom), y `.gitignore` impide volver a añadirlos por accidente.

**Estado de la historia de git:** el 12-13 de noviembre de 2026 se reescribió la historia de las 24 ramas (`git filter-repo`) para eliminar estos archivos y dos volcados PostgreSQL con datos de TomTom (`backup.sql` y `backup_.sql`, que ya no estaban en la rama principal pero seguían en commits antiguos). Los SHA de los commits cambiaron. **Límite:** GitHub conserva las referencias `refs/pull/*` de los PR antiguos, que siguen apuntando a commits previos a la reescritura, así que esos datos pueden seguir descargables por SHA hasta que GitHub Support los purgue. No hay copias conocidas en forks (0 forks) pero no se puede descartar que alguien clonara el repositorio antes.

Consecuencias que conviene conocer:

- **Los `notebooks` trabajan solo con la muestra de ORS + OpenWeather.** ORS no reporta tráfico en tiempo real, así que sus tiempos de viaje no tienen la componente de tráfico y **las cifras no coinciden con las de la versión anterior** (que mezclaba ORS y TomTom). El `.ipynb` se entrega **sin salidas** (las que traía eran de la ejecución con los datos de TomTom) y hay que ejecutarlo para verlas. El `.Rmd` **no se ha ejecutado con la muestra** (no hay R en el equipo): como `data_source` queda con un único nivel, se añadió una guarda para que `dummyVars` no falle, sin probarla.
- **`tools/merge_legacy_data.py`** (fusión de un solo uso, ya ejecutada) se detiene con un mensaje si no encuentra el CSV de TomTom, sin tocar ninguna base.
- **Tu copia local sigue funcionando.** `data/mobility.db` y `data/raw/route_weather_data.csv` no se versionan. Si el colector guarda resultados de TomTom en tu base local, eso queda bajo tus propias condiciones de uso con TomTom; conviene confirmarlas.

## Otros proveedores

Foursquare y Google Data Commons se usan para contraste y como variables del modelo, y sus datos no se versionan (la población de Data Commons sí influye en `panorama.csv`: ver el punto abierto de abajo). Antes de publicar cualquier dato obtenido de ellos, revisa sus condiciones de almacenamiento y redistribución.

## Punto abierto: `data/ml/panorama.csv`

Sus columnas de brecha (`esperado`, `brecha_relativa`, `brecha_p10`, `brecha_p90`) son predicciones de un modelo que, además de los conteos de OpenStreetMap, usa como variables la **población por zona** (Google Data Commons) y el **tiempo de viaje medio** de las rutas de cada zona, calculado sobre todas las mediciones de la base local, **incluidas las de TomTom**. No se publica ninguna fila de TomTom ni de Data Commons, pero el resultado depende de ellas, y la cláusula 11.6.1 de TomTom habla de «bases de datos derivadas». Hay tres salidas posibles, a decidir por el autor: (a) tratarlo como resultado de un modelo y no como copia de contenido, y dejarlo así, asumiendo el riesgo; (b) regenerar el panorama sin la variable de tiempo de viaje (requiere volver a entrenar); (c) retirar `panorama.csv` del repositorio y conservar solo `cell_counts.csv`.
