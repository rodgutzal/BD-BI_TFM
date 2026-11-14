# Catálogo de tests

> **Archivo generado automáticamente. No editar a mano.** Se deriva del código de `tests/` con
> `python tools/generate_tests_doc.py`; el CI (`tests/test_tests_documentation.py`) falla si
> está desactualizado. Para añadir un test: escríbelo con un nombre y un docstring descriptivos,
> añade su archivo a la tabla de la sección *Tests* del README (si es un archivo nuevo) y
> regenera este catálogo.

**54 archivos · 1034 funciones de test · 1234 casos** (un caso es una ejecución: un test parametrizado genera varios).

| Archivo | Funciones | Casos |
|---|---:|---:|
| [`tests/test_analyst_quality.py`](#teststest_analyst_qualitypy) | 6 | 6 |
| [`tests/test_analyst_tabs.py`](#teststest_analyst_tabspy) | 22 | 30+ |
| [`tests/test_analytics.py`](#teststest_analyticspy) | 3 | 3 |
| [`tests/test_analyze_weather_effect.py`](#teststest_analyze_weather_effectpy) | 4 | 4 |
| [`tests/test_api.py`](#teststest_apipy) | 14 | 20 |
| [`tests/test_api_clients.py`](#teststest_api_clientspy) | 22 | 22+ |
| [`tests/test_business_type_classifier.py`](#teststest_business_type_classifierpy) | 7 | 20 |
| [`tests/test_causal_analysis.py`](#teststest_causal_analysispy) | 49 | 59 |
| [`tests/test_check_collection_gaps.py`](#teststest_check_collection_gapspy) | 10 | 10 |
| [`tests/test_closure_labels.py`](#teststest_closure_labelspy) | 64 | 132+ |
| [`tests/test_collector.py`](#teststest_collectorpy) | 38 | 38+ |
| [`tests/test_config.py`](#teststest_configpy) | 4 | 4 |
| [`tests/test_dashboards_executive_maps.py`](#teststest_dashboards_executive_mapspy) | 38 | 49+ |
| [`tests/test_data_profile.py`](#teststest_data_profilepy) | 15 | 15 |
| [`tests/test_database.py`](#teststest_databasepy) | 4 | 4 |
| [`tests/test_database_windows.py`](#teststest_database_windowspy) | 12 | 12 |
| [`tests/test_demographics.py`](#teststest_demographicspy) | 15 | 15 |
| [`tests/test_download_osm_history.py`](#teststest_download_osm_historypy) | 128 | 170+ |
| [`tests/test_ensemble_predictor.py`](#teststest_ensemble_predictorpy) | 17 | 17 |
| [`tests/test_forecasting.py`](#teststest_forecastingpy) | 9 | 9 |
| [`tests/test_formatter_pins.py`](#teststest_formatter_pinspy) | 4 | 4 |
| [`tests/test_foursquare_client.py`](#teststest_foursquare_clientpy) | 12 | 28 |
| [`tests/test_hybrid_scheduler.py`](#teststest_hybrid_schedulerpy) | 3 | 3 |
| [`tests/test_license.py`](#teststest_licensepy) | 4 | 4 |
| [`tests/test_location_scoring.py`](#teststest_location_scoringpy) | 25 | 25 |
| [`tests/test_locations.py`](#teststest_locationspy) | 5 | 5 |
| [`tests/test_medallion.py`](#teststest_medallionpy) | 20 | 20 |
| [`tests/test_merge_legacy_data.py`](#teststest_merge_legacy_datapy) | 1 | 1 |
| [`tests/test_migrations.py`](#teststest_migrationspy) | 18 | 18 |
| [`tests/test_ml_context.py`](#teststest_ml_contextpy) | 33 | 33+ |
| [`tests/test_ml_grid.py`](#teststest_ml_gridpy) | 19 | 22 |
| [`tests/test_ml_inputs_bundle.py`](#teststest_ml_inputs_bundlepy) | 36 | 36 |
| [`tests/test_ml_lenses.py`](#teststest_ml_lensespy) | 38 | 38+ |
| [`tests/test_ml_panorama.py`](#teststest_ml_panoramapy) | 36 | 36 |
| [`tests/test_ml_panorama_view.py`](#teststest_ml_panorama_viewpy) | 23 | 23 |
| [`tests/test_ml_text_classifier.py`](#teststest_ml_text_classifierpy) | 43 | 56 |
| [`tests/test_ml_validation.py`](#teststest_ml_validationpy) | 31 | 33+ |
| [`tests/test_normalize_bronze_timestamps.py`](#teststest_normalize_bronze_timestampspy) | 15 | 15 |
| [`tests/test_operations_dashboard.py`](#teststest_operations_dashboardpy) | 7 | 7+ |
| [`tests/test_operations_status.py`](#teststest_operations_statuspy) | 11 | 16 |
| [`tests/test_ors_null_fields.py`](#teststest_ors_null_fieldspy) | 2 | 2 |
| [`tests/test_poi_extraction.py`](#teststest_poi_extractionpy) | 23 | 23 |
| [`tests/test_predictive_modeling_dashboard.py`](#teststest_predictive_modeling_dashboardpy) | 13 | 13 |
| [`tests/test_predictive_modeling_ondemand.py`](#teststest_predictive_modeling_ondemandpy) | 6 | 6 |
| [`tests/test_query_measurements_polyline.py`](#teststest_query_measurements_polylinepy) | 8 | 8 |
| [`tests/test_recommendation_dashboard.py`](#teststest_recommendation_dashboardpy) | 6 | 6 |
| [`tests/test_recommendation_interpretacion_ui.py`](#teststest_recommendation_interpretacion_uipy) | 7 | 7 |
| [`tests/test_recommendation_panorama_ui.py`](#teststest_recommendation_panorama_uipy) | 25 | 25+ |
| [`tests/test_tests_documentation.py`](#teststest_tests_documentationpy) | 9 | 9 |
| [`tests/test_text_hibrido.py`](#teststest_text_hibridopy) | 12 | 12 |
| [`tests/test_time_series.py`](#teststest_time_seriespy) | 10 | 10 |
| [`tests/test_travel_time_predictor.py`](#teststest_travel_time_predictorpy) | 28 | 31 |
| [`tests/test_validate_ensemble_model.py`](#teststest_validate_ensemble_modelpy) | 9 | 9 |
| [`tests/test_validate_travel_time_model.py`](#teststest_validate_travel_time_modelpy) | 11 | 11 |

`+` = hay un `parametrize` con valores no literales; esos tests se cuentan como 1 caso.

## `tests/test_analyst_quality.py`

> Pruebas de Analyst: abrir la pantalla usa UN perfil de la base y no las consultas caras de antes.
>
> Regresión (medido en el bind mount de Windows de Docker, donde cada recorrido de la tabla cuesta ~8 s):
>   - `get_available_routes()` (un SELECT DISTINCT que recorre toda la tabla) se llamaba 4 veces;
>   - la completitud por ruta hacía 12 consultas (33 s);
>   - "Missing Values" cargaba 100 mil filas en un DataFrame (15 s);
>   - `get_all_routes_statistics()` recorría la tabla otra vez solo para contar filas por ruta.
> Todo eso sale ahora de `get_data_profile()`, una sola pasada.

- `test_abrir_analyst_no_usa_las_consultas_caras` — Abrir el Analyst no lanza `get_available_routes` ni `get_all_routes_statistics`; hace un único `get_data_profile` compartido por todas las pestañas.
- `test_ninguna_consulta_carga_la_base_entera` — 'Missing Values' ya no carga 100 mil filas: toda lectura de filas es de UNA ruta.
- `test_las_metricas_de_calidad_son_las_del_perfil` — Total de registros, valores faltantes, duplicados y rango de fechas de la pestaña de calidad coinciden con los del perfil de datos.
- `test_la_completitud_por_ruta_sale_del_perfil_y_cubre_todas_las_rutas` — La tabla de completitud sale del perfil, trae todas las rutas y la ruta con `traffic_delay_min` vacío es menos completa que la que lo trae.
- `test_las_muestras_por_ruta_de_model_performance_son_las_filas_reales` — La tabla de muestras por ruta de Model Performance cuenta las filas reales de cada ruta.
- `test_el_panel_lateral_usa_el_ultimo_timestamp_y_no_el_resumen_completo` — app.py pedía get_database_summary() (con el DISTINCT de rutas) solo para la hora del último dato.

## `tests/test_analyst_tabs.py`

> Tests de las pestañas de Analyst que no cubría test_analyst_quality.py: editor SQL (solo lectura de verdad),
> exportación completa, explorador de datos, pruebas estadísticas, correlaciones y base vacía.
>
> (test_analyst_quality.py ya prueba que Analyst abre con UN perfil de la base; test_predictive_modeling_*.py,
> el modelado. Aquí el modelado se sustituye por un no-op.)

- `test_el_editor_sql_ejecuta_selects_y_ofrece_la_descarga` — El editor SQL ejecuta un SELECT, muestra el número de filas y la tabla con el resultado correcto.
- `test_el_editor_sql_acepta_with_recursivo_y_funciones` — El editor SQL de solo lectura acepta consultas con `WITH RECURSIVE` y funciones de SQLite.
- `test_el_editor_sql_rechaza_escrituras_y_pragmas_sin_tocar_los_datos` ×7 — Cada consulta que escribe o usa PRAGMA (parametrizado) se rechaza con «Error en la consulta» y el archivo de la base queda byte a byte igual.
- `test_el_editor_sql_no_crea_archivos_en_disco` ×2 — Regresión: con solo `mode=ro`, ATTACH y VACUUM INTO se ejecutaban y creaban archivos nuevos (VACUUM INTO vuelca una copia completa de la base a cualquier ruta escribible). El authorizer de SQLite los deniega.
- `test_el_editor_sql_cierra_la_conexion_aunque_la_consulta_falle` — Si no se cerrara, en Windows el archivo quedaría bloqueado (no se podría borrar/mover).
- `test_el_editor_sql_con_consulta_vacia_avisa` — Una consulta vacía o de solo espacios muestra el aviso «Escribe una consulta».
- `test_un_ejemplo_del_editor_rellena_la_consulta` — Elegir un ejemplo en el selector del editor rellena el cuadro de texto con su consulta.
- `test_todos_los_ejemplos_del_editor_se_pueden_ejecutar` — Cada consulta de ejemplo debe ser válida y pasar el authorizer (incluida sqlite_master).
- `test_la_exportacion_incluye_todas_las_rutas_y_la_polyline_por_defecto` — La exportación por defecto incluye las filas de todas las rutas e informa de cuántas son.
- `test_la_exportacion_ligera_omite_la_polyline` ×2 — La casilla de la polyline debe respetarse tanto en la exportación total como en la limitada por fechas.
- `test_la_exportacion_con_rango_de_fechas_filtra` — Con el rango de fechas activado y un día de historial, la exportación trae menos filas que sin filtro.
- `test_la_exportacion_sin_datos_avisa` — Si la tabla está vacía, la exportación avisa «No hay datos disponibles» en vez de fallar.
- `test_el_explorador_muestra_los_datos_de_la_ruta_elegida` — El Data Explorer muestra una tabla con las 60 filas de la ruta elegida.
- `test_las_pruebas_estadisticas_corren_con_datos_suficientes` — Con datos suficientes, la pestaña de pruebas estadísticas muestra las pruebas de estacionariedad y sus resultados.
- `test_las_correlaciones_se_dibujan_con_las_columnas_por_defecto` — La pestaña de correlaciones preselecciona las columnas por defecto (tiempo de viaje, velocidad y temperatura).
- `test_analyst_con_la_base_vacia_no_lanza_excepciones` — El Analyst se abre sin excepciones con una base vacía.
- `test_la_pestana_de_modelos_marca_las_rutas_con_modelo_entrenado` — La pestaña de modelos marca como entrenadas las rutas que tienen su archivo de modelo y como no entrenadas las demás.
- `test_un_error_en_una_pestana_se_muestra_en_ella_y_no_tumba_la_pagina` — Antes una excepción en cualquier pestaña (se ejecutan las siete en cada rerun) dejaba la página entera con el traceback. Ahora cada una se aísla: se dice cuál falló y por qué.
- `test_las_demas_pestanas_siguen_mostrandose_cuando_una_falla` — Con el explorador roto, la pestaña del editor SQL (que viene después) sigue dibujando su editor.
- `test_sin_fallos_no_aparece_ningun_aviso_de_pestana` — Si ninguna pestaña falla, no aparece ningún aviso «No se pudo mostrar».
- `test_el_fallo_de_una_pestana_queda_en_el_registro` — El mensaje en pantalla es corto; el traceback completo va al registro de la aplicación.
- `test_st_stop_dentro_de_una_pestana_no_se_trata_como_un_error` — Solo se captura Exception: st.stop() usa una excepción de control (BaseException) y debe seguir deteniendo el script. Si se capturara, se registraría como un fallo de la pestaña que no lo es (en pantalla no se notaría: el propio st.error volvería a disparar la parada), así que se comprueba el registro.

## `tests/test_analytics.py`

> Pruebas para el módulo de análisis.

- `test_analytics_initialization` — Verifica que el analizador se inicializa correctamente.
- `test_consistency_score` — Verifica el cálculo de consistency score.
- `test_database_summary` — Verifica que se puede obtener un resumen de la BD.

## `tests/test_analyze_weather_effect.py`

> Tests de tools/analyze_weather_effect.py: análisis del efecto asociado al tiempo sobre los datos de la base.

- `test_la_herramienta_lee_en_solo_lectura_y_solo_las_columnas_necesarias`
- `test_ignora_las_filas_sin_temperatura_o_sin_tiempo_de_viaje`
- `test_el_informe_muestra_la_confusion_por_la_ruta_y_el_aviso_del_psm`
- `test_con_muy_pocas_mediciones_devuelve_error`

## `tests/test_api.py`

> Pruebas de la API REST (src/api.py).
>
> Regresión: cada endpoint envolvía todo en `except Exception -> HTTPException(400)`,
> y ese `except` capturaba también el `HTTPException(404)` que el propio endpoint
> lanzaba: una ruta sin datos respondía 400 con detail="404: No data available"
> en vez de un 404 real.
>
> `src.api` construye la base y GoldLayer AL IMPORTARSE (GoldLayer crea tablas), así
> que se importa aquí con MOBILITY_DB_PATH apuntando a un directorio temporal: ningún
> test toca data/mobility.db.

- `test_la_api_usa_la_base_indicada_por_variable_de_entorno` — La API usa la base de datos que indica la variable de entorno.
- `test_ruta_sin_datos_responde_404_y_no_400` ×5 — Una ruta sin datos responde 404 (en cada URL parametrizada) y el `detail` no lleva el 404 anidado.
- `test_el_detail_del_404_es_el_mensaje_original` — El `detail` del 404 es el mensaje original de cada endpoint.
- `test_analisis_invalido_es_422` — Un tipo de análisis de serie temporal no válido responde 422.
- `test_parametros_fuera_de_rango_son_422` ×3 — Los parámetros fuera de rango (en cada URL parametrizada) responden 422.
- `test_health` — `/api/health` responde «healthy» con el número de rutas.
- `test_routes` — `/api/routes` lista el total y cada ruta con origen y destino.
- `test_rankings_con_gold_vacio_no_falla` — `/api/routes/rankings` responde 200 con listas vacías cuando la capa Gold no tiene datos.
- `test_statistics` — `/api/statistics` devuelve la ruta y las estadísticas con el recuento de mediciones.
- `test_anomalies` — `/api/anomalies` responde 200 con la ruta y la lista de anomalías.
- `test_json_safe_sustituye_nan_e_infinito_por_none` — JSON no admite NaN/inf: se convierten en None, también dentro de dicts y listas anidados. Los escalares de numpy (np.bool_, np.float64) pasan a tipos nativos de Python.
- `test_time_series_patrones_con_un_dia_de_una_sola_muestra` — Regresión: un día con 1 muestra tiene desviación típica NaN y el endpoint devolvía 500 (dependía de la hora a la que se ejecutaba: justo tras la medianoche UTC).
- `test_time_series_patrones` — `/api/time-series` con `analysis=patterns` responde 200 con ese tipo de análisis.
- `test_predict_devuelve_json_serializable_y_modelos_entrenados` — De punta a punta: entrena el ensemble con los datos y responde. Cubre también que el resultado se serialice (antes `model_predictions` se apuntaba a sí mismo).

## `tests/test_api_clients.py`

> Tests de los clientes HTTP (TomTom, OpenRouteService, OpenWeather, Overpass).
>
> Sin red: se sustituye `client.session` por una sesión falsa que devuelve respuestas fijas o lanza
> excepciones de `requests`, y se comprueba la petición que se habría enviado y el parseo del resultado.

- `test_la_sesion_reintenta_solo_errores_transitorios` — Cada cliente monta reintentos sobre https: 4 intentos, solo para 429/5xx y solo para su método HTTP.
- `test_close_cierra_la_sesion` — `close()` cierra la sesión HTTP del cliente.
- `test_tomtom_parsea_la_ruta_y_envia_la_peticion_correcta` — TomTom interpreta la respuesta con todos sus campos y envía la URL, el timeout y los parámetros correctos.
- `test_tomtom_sin_campos_opcionales_deduce_el_tiempo_sin_trafico` — Sin trafico ni noTrafficTravelTime: retraso 0 y tiempo sin tráfico = tiempo de viaje; sin polyline.
- `test_tomtom_con_tiempo_cero_no_divide_por_cero` — Con un tiempo de viaje de 0, TomTom da velocidad media 0 y no divide entre cero.
- `test_tomtom_propaga_los_errores` — Los errores de red y de estado HTTP de TomTom (parametrizado) se propagan al llamador.
- `test_ors_parsea_la_ruta_con_las_mismas_claves_que_tomtom` — ORS devuelve las mismas claves que TomTom; los campos de tráfico que no informa quedan en `None`, no en 0.
- `test_ors_envia_longitud_antes_que_latitud_y_la_clave_en_la_cabecera` — ORS recibe las coordenadas como [longitud, latitud] y la clave de API en la cabecera `Authorization`.
- `test_ors_propaga_los_errores` — Los errores de red y de estado HTTP de ORS (parametrizado) se propagan al llamador.
- `test_weather_parsea_y_pide_unidades_metricas` — El clima se interpreta correctamente y se pide en unidades métricas con la clave en los parámetros.
- `test_weather_respuesta_incompleta_da_none_y_unknown` — Una respuesta de clima incompleta da valores `None` y la descripción «Unknown».
- `test_weather_usa_la_cache_por_ubicacion_y_caduca` — El clima se cachea por ubicación y caduca pasado el tiempo de vida; `clear_cache` vacía la caché.
- `test_weather_un_error_no_se_guarda_en_cache` — Un error al pedir el clima no se guarda en la caché: la siguiente petición vuelve a intentarlo.
- `test_weather_propaga_los_errores` — Los errores de red y de estado HTTP del clima (parametrizado) se propagan al llamador.
- `test_overpass_clasifica_por_prioridad_y_toma_el_valor_como_subcategoria` — Overpass clasifica cada elemento por prioridad entre categorías y toma el valor de la etiqueta como subcategoría; lo que no encaja da `None`.
- `test_overpass_la_query_cubre_todas_las_categorias` — La consulta de Overpass cubre todas las categorías: cabecera con el timeout, regex para varios valores y una cláusula de nodo y otra de vía por etiqueta.
- `test_overpass_parsea_nodos_y_ways_y_descarta_lo_inutil` — Se interpretan nodos y vías y se descartan los elementos sin categoría o sin coordenadas; el que no tiene nombre recibe uno genérico.
- `test_overpass_fetch_calcula_el_bbox_con_margen_y_el_timeout_del_servidor` — `fetch_pois` calcula el rectángulo de búsqueda con el margen y envía el timeout del servidor y el del cliente.
- `test_overpass_prueba_el_siguiente_espejo_si_uno_falla` — Si un servidor espejo de Overpass falla (error de red o 504), se prueba el siguiente.
- `test_overpass_json_invalido_cuenta_como_fallo_del_espejo` — Un JSON inválido cuenta como fallo del espejo y se pasa al siguiente.
- `test_overpass_si_todos_los_espejos_fallan_lanza_runtimeerror` — Si todos los espejos fallan, `fetch_pois` lanza `RuntimeError` tras probarlos todos.
- `test_overpass_envia_un_user_agent_descriptivo` — El cliente de Overpass envía su `User-Agent` descriptivo.

## `tests/test_business_type_classifier.py`

> Pruebas del clasificador de texto libre -> categoría de Overpass.

- `test_clasifica_negocios_comunes` ×10 — Cada texto de negocio común (parametrizado) se clasifica en la categoría esperada.
- `test_barberia_no_se_confunde_con_bar` — Regresión: la palabra clave "bar" (comida y bebida) no debe matchear dentro de "barbería". Es el bug que ya ocurrió una vez con datos reales de Foursquare, y el clasificador usa límites de palabra (\b) para evitarlo.
- `test_ignora_mayusculas_tildes_y_espacios_de_mas` — El clasificador no distingue mayúsculas, tildes ni espacios repetidos o sobrantes.
- `test_sin_coincidencia_devuelve_none_y_nunca_adivina` ×5 — Un texto sin ninguna palabra clave devuelve `None`; nunca elige una categoría al azar.
- `test_todas_las_categorias_existen_en_overpass` — El clasificador solo puede devolver categorías que realmente guarda la tabla `pois` (CATEGORY_TAGS de poi_client.py).
- `test_ninguna_palabra_clave_choca_con_otra_categoria` — Una misma palabra no puede aparecer en dos categorías (el orden de las reglas decidiría en silencio), y ninguna palabra de una categoría puede estar contenida como palabra completa dentro de una frase de otra.
- `test_cantidad_de_palabras_clave_documentada` — El README dice 140 palabras clave (únicas).

## `tests/test_causal_analysis.py`

> Tests de src/analytics/causal_analysis.py con datos sintéticos de efecto conocido.
>
> Ojo con lo que NO prueban: el módulo estima asociaciones en datos observacionales (no experimentales); estos
> tests comprueban que los cálculos recuperan un efecto conocido y que los casos límite se manejan, no que el
> resultado sea causal.

- `test_el_constructor_ordena_por_tiempo_parsea_utc_y_no_modifica_el_original` — El constructor ordena por tiempo, interpreta los timestamps en UTC y no modifica el DataFrame original.
- `test_recupera_un_efecto_positivo_conocido` — Sobre datos con un efecto positivo conocido de la temperatura, el análisis lo recupera: correlación alta, diferencia entre grupos significativa y conclusión de evidencia muy fuerte.
- `test_sin_efecto_no_sale_significativo` — Sin efecto real, ni la correlación ni el análisis estratificado salen significativos y la conclusión es de evidencia débil.
- `test_un_efecto_negativo_lleva_signo_negativo` — Un efecto negativo da coeficiente de correlación y tamaño del efecto con signo negativo.
- `test_sin_marca_de_tiempo_ni_covariables_no_hay_ajuste` — Sin timestamp, ruta ni covariables no hay con qué ajustar: ni propensity score ni estratificación (`None`), pero el análisis sin ajustar sí. Antes bastaba con que faltaran `hour`/`day_of_week`/`average_speed_kmh`.
- `test_con_marca_de_tiempo_se_ajusta_aunque_no_existan_las_columnas_hour_y_day_of_week` — Regresión: el 'PSM' solo corría si existían las columnas hour/day_of_week/average_speed_kmh, que en los datos reales casi nunca existen. Ahora hora, día y semana se derivan del timestamp.
- `test_usa_otra_columna_de_clima_si_se_pide` — Se puede analizar otra columna de clima distinta de la temperatura, por ejemplo la humedad.
- `test_ignora_las_filas_con_nulos_y_exige_30_filas` — Las filas con nulos se descartan del tamaño de muestra y con menos de 30 filas útiles devuelve «Insufficient data».
- `test_columnas_ausentes_devuelven_error` — Si falta una columna necesaria o se pide una que no existe, devuelve un error «Missing columns».
- `test_la_simulacion_recupera_el_coeficiente_y_escenarios_coherentes` — La simulación recupera el coeficiente de temperatura y sus escenarios (de -5 a +5 °C) son coherentes: el cambio es proporcional, nulo en +0 y creciente.
- `test_la_simulacion_valida_los_datos` — La simulación devuelve error si falta la columna de temperatura o si hay pocos datos.
- `test_mide_una_mejora_antes_despues` — Mide una intervención que mejora el tiempo de viaje: efecto negativo, significativo, grande y con los tamaños de muestra de antes y después.
- `test_una_degradacion_se_marca_como_tal` — Una intervención que empeora el tiempo de viaje se marca como degradación con efecto positivo.
- `test_sin_cambio_no_es_significativo_y_el_efecto_es_despreciable` — Sin cambio entre antes y después, el resultado no es significativo y el efecto es despreciable o pequeño.
- `test_intervencion_valida_columna_y_tamano_de_los_periodos` — La evaluación de una intervención devuelve error si falta `travel_time_min` o si el periodo tiene muy pocos datos.
- `test_serie_constante_no_divide_por_cero` — Con una serie constante, la d de Cohen es 0 y no se divide entre cero.
- `test_detecta_la_hora_como_confusor_cuando_afecta_a_temperatura_y_trafico` — La hora del día se detecta como confusor de severidad alta cuando influye a la vez en la temperatura y en el tráfico.
- `test_la_hora_no_es_confusor_si_solo_afecta_a_una_de_las_dos_variables` — Un confusor debe afectar al tratamiento Y al resultado: con solo uno de los dos no se marca.
- `test_detecta_el_dia_de_la_semana_si_el_trafico_varia_mas_de_un_20_por_ciento` — El día de la semana se detecta como confusor si el tráfico varía más de un 20 % entre días.
- `test_sin_confusores_la_lista_esta_vacia_y_hay_recomendaciones` — Sin confusores la lista queda vacía, pero se devuelven consejos y recomendación de método; con datos insuficientes también queda vacía.
- `test_interpretacion_del_p_valor` ×4 — El texto de interpretación del efecto cambia según el p-valor (parametrizado) y siempre incluye el efecto con su signo.
- `test_interpretacion_de_cohen` ×7 — La etiqueta de magnitud de la d de Cohen (parametrizado) corresponde a cada valor de d.
- `test_la_estratificacion_recupera_un_efecto_conocido` — Con efecto 0,5 min/°C de anomalía, la diferencia entre 'más calor de lo habitual' y 'menos' es ~0,5 × 3,4 °C (esperado ~1,7; medido 1,59): se recupera y el intervalo excluye el 0.
- `test_la_estratificacion_sin_efecto_no_inventa_uno_aunque_la_hora_confunda` — El calor y el tráfico dependen de la hora; sin efecto verdadero, el estimador ajustado da ~0.
- `test_la_ruta_confunde_y_la_estratificacion_la_neutraliza` — La ruta A es más cálida y 4 min más rápida, pero el calor NO tiene efecto: sin ajustar sale -4,4 min; con la ruta en los estratos, ~0; sin la ruta en los estratos, el sesgo vuelve (es lo que pasaba con los datos reales).
- `test_estratificacion_descarta_las_tratadas_sin_controles_en_su_estrato_y_lo_cuenta`
- `test_estratificacion_sin_soporte_comun_da_error` — Si cada estrato tiene solo tratadas o solo controles (aquí, una columna que separa los dos grupos), no hay comparación posible.
- `test_las_columnas_de_estrato_desconocidas_dan_error_en_vez_de_romper`
- `test_errores_de_los_estimadores_ajustados` ×2
- `test_la_estratificacion_sin_columnas_de_estrato_avisa`
- `test_el_psm_es_un_emparejamiento_real_y_no_la_diferencia_de_medias` — Regresión: antes se calculaban los propensity scores y no se usaban; el 'PSM' era la diferencia de medias entre tratadas y controles. Con la ruta confundiendo (-4,4 sin ajustar), el emparejamiento exacto por ruta la reduce mucho.
- `test_el_psm_avisa_cuando_su_equilibrio_es_pobre_y_no_se_fia_de_si_mismo` — Con un propensity score casi constante el emparejamiento es casi aleatorio y puede no equilibrar (King y Nielsen, 2019). El diagnóstico lo detecta y el texto lo advierte en vez de presentar el número como bueno.
- `test_con_la_mediana_global_el_tratamiento_queda_determinado_por_la_hora_y_el_equilibrio_falla` — 'Por encima de la mediana global' es casi 'es de día': sin solapamiento, el PSM no equilibra (SMD ~1).
- `test_el_psm_informa_del_equilibrio_antes_y_despues_y_de_las_peores_covariables`
- `test_el_psm_no_ajusta_por_consecuencias_del_trafico` — La velocidad media es CONSECUENCIA del tiempo de viaje: ajustar por ella sesga. Por defecto no entra.
- `test_el_psm_es_determinista_con_la_misma_semilla_y_el_intervalo_contiene_el_efecto`
- `test_el_intervalo_por_dias_es_mas_ancho_que_uno_que_trata_cada_medicion_como_independiente` — Las mediciones de un mismo día comparten el mismo golpe: remuestrear días completos da un intervalo más honesto.
- `test_smd_de_dos_grupos_iguales_desplazados_y_con_pesos`
- `test_la_matriz_de_ajuste_deriva_hora_dia_semana_ruta_y_fuente`
- `test_una_covariable_numerica_con_pocos_valores_es_categorica_y_con_muchos_se_estandariza`
- `test_sin_nada_con_que_ajustar_la_matriz_es_none`
- `test_ningun_texto_presenta_una_asociacion_como_causa` — Los datos son observacionales: las salidas hablan de asociación y avisan de que no es prueba de causalidad.
- `test_weather_impact_causal_incluye_los_dos_estimadores_ajustados`
- `test_el_psm_ajusta_un_confusor_continuo_cuando_hay_solapamiento` — Donde el propensity score SÍ varía, el emparejamiento hace su trabajo: la diferencia sin ajustar (+3) se reduce a ~0 y el equilibrio pasa de SMD 2,3 a ~0,05.
- `test_el_psm_con_confusor_continuo_recupera_un_efecto_positivo`
- `test_el_caliper_descarta_las_tratadas_sin_pareja_cercana_y_sin_el_el_sesgo_reaparece` — Sin caliper se empareja a todas, también a las que no tienen un control parecido, y el estimador se sesga.
- `test_el_equilibrio_pondera_cada_control_por_las_veces_que_se_usa` — Emparejamiento con reemplazo: un control usado dos veces pesa el doble. Tratadas x=1,1,1; controles x=1 (usado 2 veces) y x=100 (1 vez): la media ponderada es 34, no 50,5.
- `test_una_covariable_constante_no_cuenta_como_ajuste` — Una variable sin variación se descarta de la matriz: no puede ajustar nada.
- `test_el_vecino_mas_cercano_se_elige_entre_los_dos_lados` — Controles separados (0, 1, 5, 10): cada tratada se empareja con el más próximo, venga de la izquierda o de la derecha, y los extremos se quedan con el control del borde.

## `tests/test_check_collection_gaps.py`

> Pruebas de tools/check_collection_gaps.py (detección de huecos de recolección).

- `test_find_gaps_detecta_solo_pausas_mayores_al_umbral` — `find_gaps` detecta solo las pausas mayores que el umbral: ciclos cada 15 minutos y 5 horas de silencio dan un único hueco.
- `test_find_gaps_sin_huecos` — Sin pausas mayores que el umbral, `find_gaps` devuelve una tabla vacía.
- `test_find_gaps_ignora_duplicados_y_orden` — Las filas de un mismo ciclo comparten instante y el orden de entrada no importa para detectar huecos.
- `test_find_gaps_con_menos_de_dos_instantes` — Con menos de dos instantes distintos no puede haber huecos.
- `test_fmt_h` — `fmt_h` da horas para una duración corta (3 h se muestra «3.0 h») y días para una larga (72 h se muestra «3.0 días»).
- `test_load_cycle_times_filtra_por_fecha_y_descarta_timestamps_invalidos` — `load_cycle_times` descarta lo anterior a la fecha de inicio y los timestamps que no son fechas.
- `test_load_cycle_times_es_de_solo_lectura` — `load_cycle_times` no modifica la base de datos.
- `test_report_avisa_si_ahora_mismo_no_llega_trafico` — El informe avisa «AHORA MISMO» si el último dato es antiguo y devuelve su edad.
- `test_report_mide_el_tiempo_total_sin_datos` — El informe cuenta los huecos y suma el tiempo total sin datos, sin avisar de sequía actual si los datos son recientes.
- `test_report_sin_datos` — Sin datos, el informe devuelve cero huecos y escribe «Sin datos».

## `tests/test_closure_labels.py`

> Tests de las etiquetas de cierre y la puerta de tamaño muestral (fase 4, protocolo 3.M de docs/DISENO_ML_RECOMENDACION.md).
>
> Datos sintéticos: cada test fija UNA regla del protocolo. Ningún test lee los datos reales de `data/osm_history/`.

- `test_normalizar_nombre` ×7
- `test_un_nombre_vacio_o_que_no_es_texto_normaliza_a_vacio` ×7
- `test_dos_nombres_son_el_mismo_solo_si_son_iguales_tras_normalizar_sin_coincidencia_aproximada`
- `test_categoria_usa_la_clasificacion_del_recolector` ×12
- `test_local_vacio` ×9
- `test_toda_combinacion_prefijo_clave_es_una_marca_de_ciclo_de_vida` ×25
- `test_lo_que_no_es_prefijo_y_clave_de_categoria_no_es_una_marca` ×6
- `test_las_marcas_de_ciclo_de_vida_son_las_que_descarga_la_herramienta` — Si la descarga cambiase de claves o prefijos, las etiquetas dejarían de ver marcas: un test lo ata.
- `test_el_punto_es_el_nodo_o_el_centro_del_way`
- `test_un_elemento_sin_coordenadas_validas_no_tiene_punto`
- `test_un_nodo_y_un_way_con_el_mismo_numero_son_elementos_distintos`
- `test_la_distancia_al_borde_se_mide_contra_los_cuatro_lados` ×4
- `test_fuera_de_la_rejilla_la_distancia_es_negativa`
- `test_la_poblacion_son_los_locales_de_las_siete_categorias_con_nombre_lejos_del_borde_y_abiertos`
- `test_el_margen_del_borde_es_estricto_a_500_m`
- `test_los_elementos_repetidos_entre_franjas_cuentan_una_vez_y_nodo_y_way_con_el_mismo_id_son_dos`
- `test_una_poblacion_vacia_da_una_tabla_vacia_con_columnas`
- `test_fuerte_marca_de_ciclo_sin_categoria_activa`
- `test_fuerte_tambien_con_la_marca_dentro_de_los_archivos_de_hoy_y_otro_prefijo`
- `test_fuerte_un_local_vacio_hoy_es_cierre_explicito_aunque_haya_cambiado_de_nombre_o_categoria` ×5 — Por eso «fuerte» prevalece sobre «dudoso».
- `test_vacio_y_marca_de_ciclo_a_la_vez_es_fuerte`
- `test_la_marca_de_ciclo_con_categoria_activa_y_sin_vacio_es_dudosa_no_fuerte`
- `test_los_tags_de_hoy_son_la_union_de_los_dos_archivos` — Con la categoría activa en «hoy» y la marca en el archivo de ciclo de vida, el elemento es activo+marca (dudoso), no fuerte.
- `test_superviviente_misma_categoria_mismo_nombre_normalizado_y_sin_marca`
- `test_el_superviviente_no_depende_de_otras_etiquetas_ni_del_valor_concreto_de_la_clave`
- `test_dudoso_sigue_pero_cambio_de_nombre`
- `test_dudoso_sigue_pero_perdio_el_nombre`
- `test_dudoso_sigue_pero_cambio_de_categoria`
- `test_dudoso_ausente_pero_hay_un_elemento_con_el_mismo_nombre_a_menos_de_60_m_nodo_que_pasa_a_way`
- `test_la_distancia_de_60_m_es_inclusiva_y_mas_alla_es_probable`
- `test_el_emparejamiento_por_nombre_vale_para_cualquiera_de_las_siete_categorias`
- `test_otro_nombre_a_menos_de_60_m_no_basta`
- `test_el_nombre_de_un_elemento_sin_categoria_activa_no_cuenta_como_remapeo`
- `test_un_local_vacio_con_el_mismo_nombre_no_es_un_remapeo` ×2 — Interpretación declarada: un negocio re-mapeado tiene que estar abierto, igual que en la población de estudio.
- `test_el_remapeo_no_se_aplica_al_que_sigue_con_su_propio_id` — Un local que sigue con su (tipo, id) y mismo nombre no necesita emparejamiento: es superviviente aunque haya otro igual cerca.
- `test_el_mismo_numero_pero_otro_tipo_no_es_el_mismo_local` — El nodo 1 de 2022 y un way 1 de hoy: son distintos. El nodo no figura hoy; el way, a 0 m con el mismo nombre → dudoso.
- `test_probable_no_figura_hoy_ni_hay_nada_con_su_nombre_cerca`
- `test_el_mismo_nombre_lejos_no_evita_el_probable`
- `test_no_se_usa_foursquare_ni_ninguna_fuente_externa` — `etiquetar` solo recibe elementos de OSM: no hay parámetro para otra fuente (el protocolo la deja fuera de la principal).
- `test_cierre_principal_y_sensibilidad_a`
- `test_el_orden_de_las_reglas_decide_la_primera_que_se_cumple_sin_solapes` — Cada local tiene exactamente un nivel, y la tabla recorre los cuatro.
- `test_hay_bloques_de_sobra_en_la_rejilla_para_estos_tests`
- `test_la_puerta_se_cumple_con_60_cierres_en_30_bloques_exactos`
- `test_con_59_cierres_no_pasa_aunque_haya_bloques_de_sobra`
- `test_con_29_bloques_no_pasa_aunque_haya_cierres_de_sobra`
- `test_los_bloques_se_cuentan_por_bloque_de_1_km_no_por_celda` — 64 cierres en las 16 celdas de un mismo bloque de 1 km (filas y columnas 0-3): un único bloque.
- `test_celdas_vecinas_de_bloques_distintos_son_bloques_distintos` — Las filas 3 y 4 están en bloques de 1 km diferentes (la cuadrícula de bloques no está desplazada).
- `test_solo_cuentan_los_cierres_principales_no_los_superviviente_ni_dudosos`
- `test_sin_cierres_no_pasa_y_no_falla`
- `test_los_minimos_de_la_puerta_son_los_del_protocolo`
- `test_la_herramienta_verifica_antes_de_leer_e_imprime_la_puerta`
- `test_la_herramienta_se_niega_si_los_datos_no_estan_verificados_y_no_lee_nada`
- `test_la_herramienta_se_niega_sin_huella_versionada`
- `test_la_herramienta_con_una_huella_rota_sale_con_error_claro`
- `test_guardar_escribe_solo_agregados_y_nunca_etiquetas_por_local`
- `test_sin_guardar_no_se_escribe_ningun_archivo_ni_en_el_destino_por_defecto`
- `test_guardar_sin_destino_escribe_en_el_destino_por_defecto`
- `test_la_herramienta_agrupa_los_trozos_por_instante_y_no_usa_2024`
- `test_un_elements_que_no_es_lista_se_rechaza`
- `test_justo_a_500_m_del_borde_se_excluye_la_poblacion_es_a_MAS_de_500`
- `test_justo_a_60_m_es_el_mismo_sitio_el_umbral_es_inclusivo`
- `test_si_un_elemento_viene_repetido_con_datos_distintos_gana_el_primero` — Determinista: las franjas solapadas traen copias iguales, pero si no lo fueran no depende del azar.
- `test_si_hoy_y_ciclo_de_vida_discrepan_en_un_tag_manda_hoy` — Hoy dice «Café Luna»; el archivo de ciclo de vida (otra consulta, otro instante) dice «Otro»: manda hoy, así que es superviviente.
- `test_un_way_de_2022_se_empareja_con_el_way_de_hoy_y_no_con_un_nodo_del_mismo_numero`

## `tests/test_collector.py`

> Tests del orquestador de recolección (src/collector.py): DataCollector de punta a punta y el bucle real de
> HybridScheduler.
>
> Sin red ni esperas: los clientes TomTom/ORS/OpenWeather se sustituyen por falsos, `time.sleep` por un contador y
> `signal.signal` por un registro (para no tocar el manejador de Ctrl+C de pytest). La base es temporal y el
> heartbeat se redirige (el real vive en logs/heartbeat y lo lee el HEALTHCHECK de Docker).

- `test_rechaza_una_fuente_desconocida` — Una fuente de tráfico que no sea «ors» o «tomtom» lanza `ValueError`.
- `test_la_fuente_elige_el_cliente` — La fuente elegida («tomtom» u «ors») decide qué cliente de tráfico se crea.
- `test_timescale_solo_se_activa_con_configuracion` — Timescale solo se activa si hay configuración y no se pide desactivarlo expresamente.
- `test_el_manejador_de_parada_solo_se_registra_si_se_pide` — Se escuchan Ctrl+C y SIGTERM (la de `docker stop`); antes solo SIGINT y Docker acababa matando con SIGKILL.
- `test_una_senal_de_parada_baja_la_bandera_sin_salir_ni_cerrar_los_clientes` — Antes el manejador hacía sys.exit(0) y cerraba los clientes en cualquier punto del ciclo: se perdía el ciclo (si estaba pidiendo datos) o se guardaba a medias (CSV sí, SQLite no). Ahora solo pide parar.
- `test_una_segunda_senal_sale_sin_esperar` — La primera señal de parada solo pide parar; la segunda sale de inmediato con código 1.
- `test_la_senal_durante_un_ciclo_deja_que_termine_y_lo_guarda` — Si llega la señal a mitad de un ciclo, el ciclo se completa y se guarda; después el bucle sale y cierra los clientes.
- `test_close_no_falla_si_un_cliente_ya_estaba_cerrado_o_falla` — `close()` no propaga el error si un cliente falla al cerrarse y cierra igualmente el resto.
- `test_run_continuous_cierra_los_clientes_aunque_el_ciclo_lance_una_excepcion` — `run_continuous` cierra los clientes aunque un ciclo lance una excepción.
- `test_un_ciclo_guarda_todas_las_rutas_en_csv_y_sqlite` — Un ciclo guarda una fila por ruta en el CSV y en SQLite, con un único instante y la fuente correcta, y escribe el heartbeat.
- `test_cada_ruta_lleva_el_clima_de_su_origen_y_destino_y_se_pide_una_vez_por_lugar` — Cada ruta lleva el clima de su origen y destino, y el clima se pide una vez por lugar, no una vez por ruta.
- `test_el_nivel_de_movilidad_cambia_justo_por_encima_de_20_minutos` — > 20 min es 'Alta demora'; 20 exactos todavía es normal (umbral estricto).
- `test_si_falla_el_clima_de_un_lugar_la_ruta_se_guarda_sin_clima` — Si falla el clima de un lugar, las rutas de ese origen se guardan sin clima y las demás conservan el suyo.
- `test_si_falla_una_ruta_se_siguen_guardando_las_demas` — Si falla una ruta, las demás se siguen guardando y el ciclo cuenta solo las que se guardaron.
- `test_si_fallan_todas_las_rutas_no_se_guarda_nada_ni_hay_latido` — Si fallan todas las rutas no se guarda nada y no se escribe el heartbeat.
- `test_si_falla_el_guardado_devuelve_cero_y_no_hay_latido` — Si falla el guardado en SQLite, el ciclo devuelve 0 y no escribe el heartbeat.
- `test_con_timescale_activo_se_guarda_tambien_alli_con_su_configuracion` — Con Timescale activo, el ciclo guarda también allí todos los registros con su configuración.
- `test_sin_timescale_no_se_intenta_guardar_alli` — Sin Timescale, el ciclo no intenta guardar allí.
- `test_el_heartbeat_se_escribe_en_logs_del_proyecto_con_la_hora_del_ciclo` — El heartbeat se escribe en `logs/` del proyecto con la hora actual.
- `test_un_heartbeat_que_no_se_puede_escribir_no_rompe_el_ciclo` — Un heartbeat que no se puede escribir no rompe el ciclo.
- `test_el_ciclo_alimenta_bronze_silver_y_gold_solo_con_sus_registros` — Con el medallón activo, el ciclo alimenta Bronze, Silver y Gold con los registros del ciclo.
- `test_cada_ciclo_procesa_solo_sus_propios_registros_en_silver` — El medallón es incremental: el 2º ciclo transforma únicamente las filas de Bronze de ese ciclo, no todo el histórico (sería lento y reprocesaría datos ya vistos).
- `test_sin_medallon_no_se_crean_las_capas` — Con el medallón desactivado no se crean las tablas de las capas.
- `test_un_fallo_del_medallon_no_impide_guardar_ni_cambia_el_resultado` — Executive es una vista adicional: si Bronze revienta, CSV/SQLite ya están guardados y el ciclo cuenta.
- `test_si_bronze_no_responde_success_se_omite_silver_y_gold` — Si Bronze no responde «success», se omiten Silver y Gold pero el ciclo sigue contando sus registros.
- `test_run_once_hace_un_solo_ciclo` — `run_once` hace un único ciclo.
- `test_run_continuous_espera_el_intervalo_segundo_a_segundo_y_se_detiene` — `run_continuous` espera el intervalo de segundo en segundo, para al bajar la bandera y no hace más ciclos.
- `test_run_continuous_termina_si_se_detiene_durante_el_ciclo` — Si se pide parar durante un ciclo, `run_continuous` termina sin esperar el intervalo.
- `test_el_hibrido_registra_un_unico_manejador_y_guarda_los_intervalos` — El planificador híbrido registra SIGINT y SIGTERM con un único manejador y guarda los intervalos de ORS y TomTom.
- `test_en_el_primer_tick_corren_las_dos_fuentes_y_despues_ninguna_hasta_su_intervalo` — En el primer tick corren las dos fuentes y después ninguna hasta que vence su intervalo.
- `test_una_fuente_vencida_corre_y_la_otra_no` — Solo corre la fuente cuyo intervalo ya venció; su reloj se reinicia y el de la otra no cambia.
- `test_si_se_detiene_durante_un_ciclo_no_dispara_la_otra_fuente` — Si se pide parar durante el ciclo de una fuente, no se dispara la otra.
- `test_el_hibrido_ante_una_senal_baja_la_bandera_sin_salir` — Ante una señal de parada (parametrizada), el híbrido baja la bandera sin salir ni cerrar todavía.
- `test_el_hibrido_con_una_segunda_senal_sale_sin_esperar` — En el híbrido, la segunda señal sale de inmediato con código 1.
- `test_el_hibrido_termina_el_ciclo_en_curso_y_cierra_los_dos_collectors` — La señal llega durante el ciclo de ORS: ese ciclo termina, no se dispara el de TomTom y se cierran ambos.
- `test_el_hibrido_cierra_los_collectors_aunque_el_ciclo_lance_una_excepcion` — El híbrido cierra los dos colectores aunque un ciclo lance una excepción.
- `test_el_compose_da_tiempo_al_colector_para_terminar_su_ciclo` — `docker compose stop` manda SIGTERM y espera stop_grace_period antes del SIGKILL: el colector necesita más que los 10 s por defecto para terminar un ciclo largo (p95 ~15 s).
- `test_un_error_en_un_ciclo_se_propaga_porque_collect_cycle_ya_captura_los_suyos` — Documenta el contrato: el hibrido NO captura excepciones de collect_cycle (DataCollector ya las maneja por dentro); si una se escapara, el bucle terminaría.

## `tests/test_config.py`

> Pruebas para el módulo de configuración (BD_BI_TFM: selección de fuente de datos).

- `test_get_data_source_default` — Sin DATA_SOURCE definido, debe usar 'ors' por defecto.
- `test_get_data_source_tomtom` — Con DATA_SOURCE=tomtom en el entorno, debe respetarlo.
- `test_get_data_source_invalid` — Un valor inválido debe lanzar RuntimeError.
- `test_get_timescale_config_defaults` — Sin variables PG* definidas, deben usarse los valores de docker-compose.yml.

## `tests/test_dashboards_executive_maps.py`

> Tests de las pantallas Executive y Maps (Streamlit AppTest) con una base temporal.
>
> Se comprueba que abren sin excepciones con datos y con la base vacía, y que lo que muestran sale de los datos
> (tarjetas, deltas, alertas, colores y estados de las rutas, capas de POIs). No se prueba el aspecto visual.

- `test_executive_abre_con_datos_y_muestra_las_tarjetas` — Executive se abre con datos y muestra las cuatro tarjetas de resumen con los valores correctos.
- `test_executive_tablas_de_mejores_y_peores_rutas` — Executive muestra las tablas de mejores y peores rutas con las columnas esperadas y cada ruta en la tabla que le toca.
- `test_executive_sin_periodo_anterior_no_inventa_deltas` — Sin periodo anterior, Executive no muestra variación en las tarjetas.
- `test_executive_con_periodo_anterior_calcula_el_delta_con_los_datos` — Con periodo anterior, Executive calcula la variación con los datos reales y pinta de rojo un aumento del tiempo de viaje.
- `test_delta` ×5 — `_delta` da el texto de variación esperado para cada par de valores y formato (parametrizado).
- `test_executive_alertas_segun_los_umbrales` ×6 — Executive muestra las alertas que corresponden a los umbrales de cada resumen (parametrizado) y no las demás.
- `test_executive_si_el_resumen_falla_muestra_el_error_y_no_sigue` — Si el resumen falla, Executive muestra el error y no dibuja tarjetas.
- `test_executive_con_la_base_vacia_no_lanza_excepciones` — Executive se abre sin excepciones con una base vacía.
- `test_executive_con_la_base_vacia_no_muestra_un_0_por_ciento_ni_una_alerta_falsa` — Sin mediciones la fiabilidad no es 0 %: es desconocida. Antes salía «0.0%» y la alerta «Low system reliability».
- `test_executive_con_datos_sigue_mostrando_las_cifras_y_las_alertas` — El aviso de «sin mediciones» no aparece cuando sí las hay.
- `test_hay_datos_solo_si_el_resumen_tiene_mediciones` ×3 — `_hay_datos` es verdadero solo si el resumen tiene mediciones (parametrizado).
- `test_color_segun_el_retraso` — El color de la ruta en el mapa depende del retraso (parametrizado).
- `test_el_mapa_dibuja_una_traza_por_ruta_mas_las_ubicaciones_y_colorea_por_retraso` — El mapa dibuja una línea por ruta más la capa de ubicaciones, y colorea cada ruta según su retraso (gris si no tiene dato).
- `test_el_mapa_ignora_rutas_con_ubicaciones_desconocidas` — El mapa ignora las rutas con ubicaciones que no existen.
- `test_maps_abre_con_datos_y_la_tabla_de_estado_cubre_todas_las_rutas` — Maps se abre con datos y su tabla de estado cubre todas las rutas con el estado correcto: flujo libre, moderado o denso.
- `test_los_limites_de_los_estados_de_la_tabla_son_1_y_4_minutos_de_retraso` — <=1 libre, <=4 moderado, >4 denso (los mismos umbrales que el color del mapa).
- `test_maps_con_la_base_vacia_marca_todas_las_rutas_sin_dato` — Con una base vacía, Maps marca todas las rutas como «Sin dato».
- `test_maps_sin_rutas_seleccionadas_avisa` — Si no se selecciona ninguna ruta, Maps avisa de que hay que elegir al menos una.
- `test_maps_sin_pois_explica_como_cargarlos` — Sin POIs cargados, Maps explica cómo cargar los de Overpass y los de Foursquare.
- `test_maps_con_pois_de_overpass_dibuja_la_capa_y_cuenta_los_elementos` — Con POIs de Overpass, Maps dibuja la capa e indica cuántos elementos muestra.
- `test_las_categorias_de_overpass_por_defecto_excluyen_las_masivas` — Las categorías de Overpass seleccionadas por defecto excluyen las más numerosas.
- `test_la_capa_de_pois_usa_la_fuente_indicada_y_no_mezcla_las_dos` — school/mall existen en los dos catálogos: elegir una fuente no debe dibujar los de la otra.
- `test_la_capa_de_pois_no_hace_nada_sin_categorias_o_con_fuente_invalida` — La capa de POIs no dibuja nada si no hay categorías o si la fuente no es válida.
- `test_executive_un_error_en_una_seccion_se_muestra_en_ella_y_no_tumba_la_pagina` — Cada sección (parametrizado) se aísla: se dice cuál falló y por qué, y la página sigue hasta la última sección.
- `test_executive_las_demas_secciones_siguen_mostrandose_cuando_una_falla` — Con el gráfico de tendencia roto, las tarjetas y las alertas (que vienen antes y después) se siguen viendo.
- `test_executive_una_seccion_que_falla_a_mitad_no_deja_lo_que_ya_habia_dibujado` — Si las tarjetas dibujan una métrica y luego fallan, esa métrica a medias se retira: solo queda el aviso.
- `test_executive_sin_fallos_no_aparece_ningun_aviso_de_seccion` — Si ninguna sección falla, no aparece ningún aviso «No se pudo mostrar».
- `test_executive_el_fallo_de_una_seccion_queda_en_el_registro` — El mensaje en pantalla es corto; el traceback completo va al registro de la aplicación.
- `test_executive_st_stop_dentro_de_una_seccion_no_se_trata_como_un_error` — Solo se captura Exception: `st.stop()` usa una excepción de control y debe seguir deteniendo el script. Si se capturara, se registraría como un fallo de la sección que no lo es, así que se comprueba el registro.
- `test_maps_un_error_en_una_seccion_se_muestra_en_ella_y_no_tumba_la_pagina` — Cada sección (parametrizado) se aísla: se dice cuál falló y por qué, y la página sigue hasta la última sección.
- `test_maps_las_demas_secciones_siguen_mostrandose_cuando_una_falla` — Con el mapa roto, los selectores y la tabla de estado (que viene después) se siguen viendo.
- `test_maps_una_seccion_que_falla_a_mitad_no_deja_lo_que_ya_habia_dibujado` — Si el mapa dibuja una nota y luego falla, esa nota a medias se retira: solo queda el aviso.
- `test_maps_si_falla_la_capa_de_infraestructura_el_mapa_de_rutas_se_dibuja_sin_ella` — La capa de POIs es opcional: si falla, el mapa de rutas y su leyenda se dibujan igualmente, con un aviso (no un error de sección), y el fallo queda en el registro.
- `test_maps_la_capa_de_infraestructura_que_funciona_llega_a_la_figura` — Cuando la capa de POIs funciona, sus marcadores van en la figura que se dibuja, junto a las rutas.
- `test_maps_una_capa_que_falla_a_mitad_no_deja_marcadores_sueltos_en_el_mapa` — Si la capa de POIs añade algo y luego falla, la figura que se dibuja no lleva esa capa a medias.
- `test_maps_sin_fallos_no_aparece_ningun_aviso_de_seccion` — Si ninguna sección falla, no aparece ningún aviso «No se pudo mostrar».
- `test_maps_el_fallo_de_una_seccion_queda_en_el_registro` — El mensaje en pantalla es corto; el traceback completo va al registro de la aplicación.
- `test_maps_st_stop_dentro_de_una_seccion_no_se_trata_como_un_error` — Solo se captura Exception: `st.stop()` usa una excepción de control y debe seguir deteniendo el script. Si se capturara, se registraría como un fallo de la sección que no lo es; y la parada se nota en que las secciones siguientes (el resumen y la tabla de estado) no se dibujan.

## `tests/test_data_profile.py`

> Pruebas del perfil de calidad de la base en UNA pasada (RouteDatabase.get_data_profile).
>
> Regresión: Analyst hacía más de diez consultas al abrirse (rutas únicas ×4, una consulta por ruta
> para la completitud, un resumen completo, 100 mil filas cargadas...). Cada recorrido de la tabla
> cuesta ~8 s en el bind mount de Windows de Docker (décimas de segundo en el host), así que sumaban
> ~87 s. Un único perfil agregado da todo eso en un recorrido.

- `test_totales_y_rutas` — El perfil da el total de filas, de rutas y de orígenes, y las filas de cada ruta.
- `test_fechas_primera_y_ultima` — El primer y el último timestamp del perfil son el mínimo y el máximo de las mediciones.
- `test_los_nulos_coinciden_con_un_calculo_independiente_en_pandas` — Los nulos por columna, por ruta y el porcentaje de faltantes coinciden con un cálculo independiente en pandas.
- `test_completitud_por_ruta` — La completitud por ruta está entre 0 y 100, y la ruta de ORS, con más columnas vacías, es menos completa que las de TomTom.
- `test_id_polyline_y_created_at_no_son_columnas_de_medicion` — `id`, `polyline` y `created_at` no cuentan como columnas de medición.
- `test_una_polilinea_nula_no_cuenta_como_dato_faltante` — Las filas históricas de TomTom no tienen polyline: eso no debe bajar la completitud.
- `test_base_vacia` — Con una base vacía el perfil devuelve ceros, fechas `None` y una tabla de rutas vacía pero con sus columnas.
- `test_cuenta_duplicados_de_ruta_instante_y_fuente` — La clave UNIQUE de la tabla real los impide; se prueba con una tabla SIN la restricción.
- `test_en_la_tabla_real_no_hay_duplicados` — El perfil no encuentra duplicados en la tabla de datos de prueba.
- `test_el_perfil_hace_una_sola_consulta_sobre_la_tabla` — El perfil recorre la tabla de mediciones con una sola consulta.
- `test_ultimo_timestamp` — `get_last_timestamp` devuelve el máximo de los timestamps.
- `test_ultimo_timestamp_de_base_vacia` — `get_last_timestamp` devuelve `None` con una base vacía.
- `test_resumen_sin_rutas_omite_solo_las_rutas_unicas` — `get_database_summary(include_routes=False)` omite solo las rutas únicas y el resto del resumen es igual.
- `test_el_resumen_por_defecto_sigue_igual` — Compatibilidad: quien lo llame sin argumentos sigue obteniendo unique_routes.
- `test_ultimo_timestamp_no_recorre_la_tabla` — MAX(timestamp) se resuelve con el índice: una sola consulta, sin DISTINCT.

## `tests/test_database.py`

> Pruebas para el módulo de base de datos.

- `test_database_init` — Verifica que la base de datos se inicializa correctamente.
- `test_save_records_to_csv` — Verifica que se guardan registros en CSV.
- `test_save_records_to_sqlite` — Verifica que se guardan registros en SQLite.
- `test_query_measurements` — Verifica que se pueden consultar mediciones.

## `tests/test_database_windows.py`

> Pruebas de las consultas de ventana completa de RouteDatabase.
>
> Regresión: los dashboards traían `query_measurements(limit=10000)` —las
> 10.000 filas MÁS RECIENTES— para gráficos de "30 días" y "7 días", así que
> con mucha recolección mostraban solo los últimos días sin avisar.

- `test_el_limit_antiguo_si_recortaba_la_ventana` — Documenta el bug: con limit=10000 solo se llega a ~25 de los 30 días.
- `test_promedio_diario_cubre_toda_la_ventana` — El promedio diario cubre toda la ventana, no pierde ninguna fila y sale ordenado por fecha.
- `test_promedio_diario_respeta_la_ventana` — Con una ventana de 3 días el promedio diario devuelve pocos días y menos filas que con la ventana completa.
- `test_promedio_diario_calcula_bien_el_promedio` — El promedio diario es la media de los tiempos de viaje del día.
- `test_promedio_diario_base_vacia` — Con una base vacía el promedio diario devuelve una tabla vacía.
- `test_promedio_por_ruta_y_hora` — El promedio por ruta y hora agrupa por origen, destino y hora, y cuenta las mediciones de cada grupo.
- `test_promedio_por_ruta_y_hora_no_pierde_filas_con_mucha_data` — El promedio por ruta y hora no pierde filas con mucho volumen y las horas están entre 0 y 23.
- `test_columnas_numericas_excluyen_el_id_y_el_texto` — Las columnas numéricas disponibles excluyen el `id` y las columnas de texto.
- `test_query_columns_trae_solo_lo_pedido_sin_limit` — `query_columns` devuelve solo las columnas pedidas y todas las filas de la ventana, sin límite.
- `test_query_columns_rechaza_columnas_que_no_existen` — `query_columns` lanza `ValueError` si una columna no existe.
- `test_query_columns_no_permite_inyeccion_sql` — `query_columns` rechaza un nombre de columna con inyección SQL y no toca la tabla.
- `test_query_columns_sin_columnas` — `query_columns` sin columnas devuelve una tabla vacía.

## `tests/test_demographics.py`

> Pruebas de la lógica pura de demografía (reconciliado a un año común).
>
> No usan la API de Data Commons ni requieren `datacommons-client`.

- `test_latest_observation_usa_el_anio_mas_alto_de_la_serie_completa` — Regresión: date='latest' de la API devolvió 2014 para Valletta cuando su propia serie ya tenía 2021.
- `test_latest_observation_ignora_zonas_sin_observaciones` — `latest_observation_per_zone` ignora las zonas sin observaciones.
- `test_latest_observation_prefiere_la_fecha_mas_reciente_en_el_mismo_anio` — Entre dos observaciones del mismo año, se queda con la de fecha más reciente.
- `test_summarize_history_encuentra_anios_comunes` — `summarize_history` encuentra los años en los que todas las zonas tienen dato.
- `test_summarize_history_sin_anio_comun_o_con_zona_sin_datos` — Sin año común, o con una zona sin observaciones, los años comunes quedan vacíos.
- `test_reconcile_proyecta_con_la_tasa_nacional` — Un dato antiguo se proyecta al año común con la tasa de crecimiento nacional y queda trazado cuál es el dato real y cuál la proyección.
- `test_reconcile_no_toca_un_dato_igual_o_mas_nuevo_que_el_objetivo` — Un dato del año objetivo o posterior se deja como observado, sin proyectar.
- `test_reconcile_respeta_un_anio_objetivo_explicito` — Si se indica un año objetivo, la proyección usa ese año.
- `test_reconcile_omite_zonas_sin_tasa_nacional_para_su_anio` — Una zona cuyo año no está en la serie nacional se omite en vez de inventar un dato.
- `test_reconcile_sin_serie_nacional` — Sin serie nacional no hay registros ni año objetivo.
- `test_reconcile_se_guarda_y_se_recupera_de_la_base` — Los datos reconciliados se guardan en la base y se recuperan con su método y año base.
- `test_guardar_solo_el_dcid_no_borra_la_poblacion_ya_guardada` — El upsert usa COALESCE: resolver un dcid no debe pisar datos existentes.
- `test_historial_de_poblacion_es_upsert` — El historial de población se guarda con upsert: repetir una observación la actualiza en vez de duplicarla.
- `test_clean_normaliza_nulos` — `_clean` convierte `None` y NaN en cadena vacía, recorta espacios y pasa números a texto.
- `test_el_cliente_exige_api_key` — El cliente de demografía lanza `ValueError` con una clave vacía o solo de comillas.

## `tests/test_download_osm_history.py`

> Pruebas de la descarga del estado histórico de OpenStreetMap (tools/download_osm_history.py, fase 4 §3.M).
>
> Sin red: se usa un cliente falso. Lo más importante que comprueban: que un espejo de Overpass que IGNORA la fecha pedida
> (y devuelve el mapa actual) se rechaza, porque si no, el «estado de 2022» sería en realidad el de hoy y no habría cierres.
>
> OJO con cómo se detecta: medido contra overpass-api.de, `osm3s.timestamp_osm_base` trae SIEMPRE la hora actual del servidor,
> también en una respuesta con datos de 2022. Por eso la fecha se comprueba con un canario (`out meta`: el `timestamp` de cada
> elemento) y NO con esa hora base; una prueba de regresión fija que una respuesta histórica con hora base actual se acepta.

- `test_el_plan_pide_tres_instantes_en_dos_franjas_y_el_ciclo_de_vida_solo_para_hoy` — 2022, 2024 y hoy, cada uno en 2 franjas (6 consultas), más una de ciclo de vida del estado actual: 7.
- `test_las_consultas_pasadas_llevan_la_fecha_y_las_actuales_no` — Solo 2022 y 2024 llevan `[date:...]`; «hoy» y el ciclo de vida piden el estado actual.
- `test_las_clausulas_de_categorias_son_las_mismas_que_las_del_cliente_de_overpass` — Si CATEGORY_TAGS o el cliente cambian, este archivo no se queda pidiendo otra cosa que el resto del proyecto.
- `test_las_siete_categorias_estan_en_la_consulta` — Cada etiqueta de cada categoría aparece en la consulta (nada se queda sin pedir).
- `test_las_clausulas_de_ciclo_de_vida_cubren_cinco_prefijos_por_cinco_claves` — `disused:`, `was:`, `abandoned:`, `demolished:` y `razed:` sobre amenity, shop, office, leisure y tourism.
- `test_las_franjas_cubren_toda_el_area_sin_huecos_ni_solapes` — Las franjas de latitud son contiguas y suman toda la rejilla.
- `test_la_consulta_del_canario_lleva_la_fecha_que_se_va_a_pedir_y_pide_meta` — El canario es una consulta pequeña en LA FECHA PEDIDA con `out center meta` (para ver el `timestamp` de cada elemento); hay uno por fecha, no uno fijo.
- `test_el_canario_acepta_un_espejo_que_respeta_la_fecha` — Todas las versiones son anteriores a la fecha y alguna es de los 2 años previos: es un estado de esa fecha.
- `test_el_canario_acepta_una_version_justo_en_la_fecha` — El límite superior es inclusivo: una versión con la fecha exacta no es posterior.
- `test_el_canario_rechaza_un_espejo_que_ignora_la_fecha` — Con el mapa actual hay versiones recientes: se rechaza y el motivo dice cuántas y la más reciente.
- `test_una_sola_version_posterior_basta_para_rechazar` — Aunque casi todo sea antiguo, una versión posterior a la fecha delata un mapa que no es de esa fecha.
- `test_el_canario_rechaza_un_espejo_con_una_copia_antigua_de_la_base` — COTA INFERIOR: un espejo atrasado (última versión de hace 5 años) pasaría la cota superior para una fecha reciente y serviría datos viejos como si fueran de 2024 u hoy. Se detecta porque no hay ninguna versión de los 2 años previos.
- `test_la_cota_inferior_del_canario_es_inclusiva_en_el_borde_de_la_ventana` — Una versión justo 730 días antes de la fecha cuenta como «reciente»; un segundo antes, no.
- `test_el_canario_exige_un_minimo_de_elementos_y_lo_trata_como_pasajero` — Una respuesta vacía o recortada no se da por buena (no hay nada que comprobar), pero NO es un motivo definitivo: lanza una excepción, que no se recuerda y se puede reintentar.
- `test_elementos_sin_timestamp_en_el_canario_son_un_problema_pasajero_no_definitivo` ×2 — Sin `timestamp` no se puede comprobar la fecha: no se acepta, pero tampoco se prueba que el espejo ignore la fecha (puede ser una respuesta defectuosa, no solo que no admita `meta`): lanza una excepción en vez de un motivo definitivo, tanto si faltan en todos los elementos como si falta solo en uno.
- `test_un_canario_sin_timestamp_no_descarta_el_espejo_y_la_ronda_siguiente_lo_recupera` — A nivel de `pedir`: un espejo que contesta una vez sin `timestamp` (respuesta defectuosa) y luego bien NO queda marcado de por vida; se reintenta en la ronda siguiente y se usa.
- `test_un_espejo_que_nunca_admite_meta_falla_a_la_vista_tras_agotar_las_rondas` — Un espejo que de verdad no admite `meta` nunca pasa el canario: no se le piden datos y el error final lo dice.
- `test_el_canario_con_remark_de_error_es_un_problema_pasajero` — Un error de Overpass con HTTP 200 (servidor saturado) no es un canario válido, pero tampoco prueba que el espejo ignore la fecha: lanza una excepción en vez de devolver un motivo definitivo.
- `test_la_hora_base_del_servidor_es_la_actual_y_aun_asi_una_respuesta_historica_valida_se_acepta` — REGRESIÓN del hallazgo real: overpass-api.de pone la hora ACTUAL en `osm3s.timestamp_osm_base` aunque los datos sean de 2022. La versión anterior de la herramienta comparaba esa hora con la fecha pedida y habría rechazado TODAS las respuestas históricas válidas.
- `test_un_espejo_que_ignora_la_fecha_se_rechaza_y_se_prueba_el_siguiente` — El primer espejo devuelve el mapa actual para una consulta de 2022: se descarta tras el canario y se usa el segundo. Al espejo malo no se le pide ningún dato real.
- `test_si_todos_los_espejos_ignoran_la_fecha_falla_en_vez_de_devolver_el_presente` — Nunca se devuelve en silencio el mapa actual como si fuera el de 2022.
- `test_el_canario_se_pide_una_sola_vez_por_espejo_y_se_recuerda` — Con el mismo diccionario de verificados, varias consultas al mismo espejo solo gastan un canario.
- `test_un_espejo_marcado_como_que_ignora_la_fecha_no_se_vuelve_a_consultar` — Tras fallar el canario por ignorar la fecha, el espejo queda descartado: no se repite el canario en cada consulta.
- `test_si_falla_la_red_en_el_canario_el_espejo_no_queda_marcado_y_se_puede_reintentar` — Un error de red durante el canario no es «ignora la fecha»: se reintenta en la ronda siguiente y entonces se acepta.
- `test_un_canario_pasajero_no_descarta_el_espejo_y_la_ronda_siguiente_lo_recupera` — El único espejo con historia está saturado justo en el canario (remark o respuesta recortada) y responde bien en la ronda 2: no se le debe marcar como «ignora la fecha» de por vida. Es el caso que las rondas existen para cubrir.
- `test_un_canario_pasajero_no_deja_marcado_el_espejo_mientras_dure_el_fallo` — Mientras el canario siga fallando de forma pasajera, `verificados` queda vacío (nada se recuerda).
- `test_tras_un_canario_nuevo_se_hace_una_pausa_y_con_el_espejo_ya_verificado_no` — El canario es una petición más: se espera `PAUSA_S` antes de la consulta pesada, una sola vez por espejo.
- `test_hay_un_canario_por_cada_fecha_que_se_pide_y_se_recuerda_por_separado` — Pedir 2022 y 2024 al mismo espejo gasta DOS canarios (uno por fecha), y cada uno se recuerda aparte; con la misma fecha varias veces solo se gasta uno.
- `test_un_espejo_atrasado_se_rechaza_para_2024_aunque_hubiera_pasado_el_canario_de_2022` — Un espejo con una copia vieja pasa el canario de 2022 pero no el de 2024: no se le piden los datos de 2024.
- `test_el_resumen_final_no_falla_con_un_manifiesto_de_la_version_anterior` — Un `manifest.json` heredado con la clave antigua `osm_base` (sin `osm_base_servidor`) no hace reventar el resumen.
- `test_una_consulta_actual_no_pide_canario` — Para «hoy» (sin fecha) no hay nada que comprobar: no se gasta una consulta de canario.
- `test_un_error_de_red_en_un_espejo_pasa_al_siguiente` — Un fallo HTTP no detiene la descarga mientras otro espejo responda.
- `test_descargar_escribe_los_json_y_un_manifiesto_con_hora_del_servidor_y_hash` — Cada trozo queda en su archivo; el manifiesto guarda recuento, sha256 y la hora del servidor solo como informativa.
- `test_descargar_pide_un_canario_por_espejo_y_por_fecha_en_toda_la_descarga` — Con 2022 y 2024 (4 consultas fechadas) hay 2 canarios (uno por fecha) y 4 consultas reales, no uno por consulta.
- `test_un_trozo_que_falla_se_anota_y_los_demas_siguen` — Si ningún espejo respeta la fecha, esos trozos quedan en `fallidos` y no se escribe su archivo.
- `test_descargar_solo_escribe_dentro_del_directorio_de_salida` — No toca nada fuera de `out_dir` (ni la base de datos).
- `test_el_dry_run_no_hace_ninguna_llamada_de_red` — `--dry-run` imprime las consultas y no crea ni usa el cliente de Overpass.
- `test_los_datos_descargados_estan_ignorados_por_git` — El estado histórico se regenera y no se versiona: `data/osm_history/` está en .gitignore.
- `test_si_todos_fallan_en_la_primera_ronda_se_espera_y_se_reintenta` — Los espejos públicos se saturan y se recuperan: tras una ronda en la que todos fallan se espera y se vuelve a empezar; aquí el primero está «al límite de capacidad» en la ronda 1 y responde en la 2.
- `test_se_rinde_tras_las_rondas_indicadas_y_solo_espera_entre_ellas` — Con 3 rondas fallidas hay 2 esperas (no una tras la última) y 3 intentos por espejo.
- `test_el_error_final_dice_por_que_fallo_cada_espejo` — Antes solo se veía el motivo del ÚLTIMO espejo y se ocultaba el de los demás.
- `test_el_timeout_de_conexion_es_corto_y_el_de_lectura_largo_tambien_en_el_canario` — Un espejo que no conecta se salta en segundos; solo la lectura (la consulta pesada) puede tardar. Vale para la consulta real y para el canario.
- `test_descargar_respeta_las_rondas_y_la_espera_que_se_le_indican` — `descargar` pasa `rondas` y `espera_s` a `pedir`: con 2 rondas y un espejo caído hay 2 intentos por trozo (4 en total para los 2 trozos de 2022) y una espera de 5 s por trozo, entre la ronda 1 y la 2.
- `test_una_respuesta_http_200_con_remark_de_error_no_se_da_por_buena` — Si Overpass se queda sin tiempo o memoria responde 200 con `remark` y `elements` vacío o parcial. Guardarlo como éxito daría un 2022 vacío, que parecería una ola de cierres: se descarta y se prueba otro espejo.
- `test_si_todos_los_espejos_devuelven_un_error_de_overpass_no_se_escribe_nada` — El trozo queda en `fallidos` con el motivo y no se crea su archivo (ni un JSON vacío que parezca bueno).
- `test_respuesta_valida_rechaza_lo_que_no_es_una_respuesta_completa` ×5 — Un `remark`, un `elements` ausente o que no es una lista, o un JSON que no es un objeto, son fallos visibles.
- `test_una_respuesta_correcta_sin_elementos_si_es_valida` — Una lista `elements` vacía sin `remark` es una respuesta legítima (un trozo sin locales), no un error.
- `test_relanzar_un_subconjunto_no_borra_lo_ya_descargado_del_manifiesto` — Tras bajar 2022 y luego solo 2024, el manifiesto trae los cuatro archivos con su hash y su fecha de descarga.
- `test_si_el_reintento_de_un_trozo_falla_se_conserva_el_archivo_anterior_y_se_avisa` — El JSON de la ejecución anterior sigue siendo válido: se mantiene en el manifiesto, y el fallo queda anotado con que se conserva el anterior (no queda un archivo en disco sin registrar).
- `test_el_manifiesto_se_ignora_si_el_anterior_esta_roto_o_apunta_a_archivos_borrados` — Un manifiesto ilegible no impide descargar, y no se heredan entradas de archivos que ya no existen.
- `test_un_cuerpo_json_cortado_a_la_mitad_es_un_fallo_y_se_prueba_otro_espejo` — Un corte de red deja el JSON a medias y `r.json()` falla: es un fallo del espejo, no una respuesta parcial que se guarde. (Es la forma realista de «respuesta truncada»; con un `remark` o sin `elements` ya se rechazaba.)
- `test_si_el_cuerpo_llega_cortado_en_todos_los_espejos_no_se_escribe_nada` — El trozo queda en `fallidos` con el motivo y no se crea su archivo (nunca un JSON a medias o vacío).
- `test_un_timestamp_malformado_en_el_canario_es_un_problema_pasajero` ×9 — Comparar como texto un valor que no es una fecha ISO válida daría un veredicto sin sentido (aceptar o rechazar un espejo por una cadena rara): se trata como respuesta defectuosa, pasajera, igual que la falta de `timestamp`.
- `test_un_timestamp_malformado_no_descarta_el_espejo_y_la_ronda_siguiente_lo_recupera` — A nivel de `pedir`: una respuesta defectuosa con un timestamp raro no deja marcado el espejo; la ronda siguiente (con el canario bien) lo acepta.
- `test_una_marca_valida_se_acepta_y_una_inventada_con_la_forma_correcta_no` — `_marca_valida` exige una fecha real, no solo el aspecto `AAAA-MM-DDThh:mm:ssZ`.
- `test_elements_con_algo_que_no_es_un_objeto_es_una_respuesta_invalida` — Si `elements` trae números o cadenas en vez de objetos no se puede guardar ni interpretar: fallo visible.
- `test_limpiar_elemento_conserva_solo_los_campos_de_la_lista_blanca` — Se quedan tipo, id, posición y etiquetas; se van versión, fecha, conjunto de cambios, uid y nombre de usuario.
- `test_los_datos_guardados_no_contienen_datos_de_colaboradores_aunque_el_espejo_los_envie` — Aunque un espejo devolviera `user`/`uid` en una respuesta normal, no llegan al JSON del disco, ni al manifiesto, ni a lo que se imprime. Es una garantía explícita, no un efecto de usar `out center tags`.
- `test_el_canario_no_guarda_nada_en_disco` — El canario (el único con `out meta`, con usuarios y uid) solo se comprueba en memoria: ningún archivo lo contiene.
- `test_la_consulta_de_recuento_es_la_misma_consulta_pidiendo_solo_cuantos` — Mismas cláusulas, misma zona y misma fecha; solo cambia la salida: `out count;` en vez de `out center tags;`.
- `test_la_consulta_de_recuento_se_niega_a_convertir_lo_que_no_es_una_consulta_de_datos` — Si la consulta no termina en `out center tags;` no se inventa un recuento.
- `test_total_del_servidor_rechaza_respuestas_que_no_son_un_recuento_valido` ×5 — Un recuento ausente, doble o no numérico no se interpreta: es un error (la verificación queda «sin verificar»).
- `test_total_del_servidor_lee_el_total_que_declara_overpass`
- `test_una_descarga_completa_se_verifica_y_queda_anotado_en_el_manifiesto` — Si el recuento del servidor coincide con lo guardado, el archivo es `completo` y el manifiesto lo registra con el criterio, las dos cifras y el espejo. Los archivos de datos no se tocan.
- `test_un_archivo_con_menos_elementos_que_el_servidor_es_incompleto_aunque_su_json_sea_valido` — El caso que no se podía detectar de otro modo: una respuesta parcial pero JSON válido y sin `remark`. El servidor dice 10 y el archivo tiene 4: INCOMPLETO, `ok` falso, y queda anotado.
- `test_para_un_instante_pasado_la_coincidencia_es_exacta_sin_tolerancia` — El pasado no cambia: una diferencia de UN solo elemento ya es un fallo (también por arriba).
- `test_para_el_estado_actual_se_admite_una_diferencia_del_uno_por_ciento` — «Hoy» cambia cada minuto: 1000 guardados frente a 1005 en el servidor (0,5 %) vale; 1030 (3 %) no.
- `test_un_recuento_ilegible_deja_el_archivo_sin_verificar_y_no_lo_da_por_bueno` — Si el servidor no contesta un recuento válido, el archivo queda `sin_verificar` (no `completo`) y `ok` es falso.
- `test_un_archivo_que_falta_se_informa_y_no_se_da_por_verificado` — Si algún trozo no está descargado, `ok` es falso aunque los demás estén completos.
- `test_sin_manifiesto_no_hay_nada_que_verificar` — Verificar una carpeta sin descargar da un error claro, no un informe vacío «correcto».
- `test_no_hay_verificacion_correcta_sin_ningun_archivo_verificado` — `ok` exige al menos un archivo completo: una verificación que no comprobó nada no puede dar luz verde.
- `test_el_canario_tambien_protege_la_verificacion_de_los_instantes_pasados` — Los recuentos fechados se piden con el mismo control de fecha: un espejo que ignora la fecha no puede 'verificar'.
- `test_main_con_verificar_no_descarga_y_su_codigo_de_salida_refleja_el_resultado` — `--verificar` solo verifica (no hace la descarga) y sale con 0 si todo está completo y con 1 si no.
- `test_un_solo_archivo_incompleto_basta_para_que_la_verificacion_no_sea_correcta` — Caso realista: uno completo y otro INCOMPLETO. `ok` debe ser falso aunque haya algún archivo correcto.
- `test_un_solo_archivo_sin_verificar_basta_para_que_la_verificacion_no_sea_correcta` — Uno completo y otro cuyo recuento no se pudo leer: `ok` es falso (lo no verificado no se da por bueno).
- `test_un_archivo_alterado_con_el_mismo_numero_de_elementos_no_sale_completo` — Si el JSON cambia después de descargarlo (mismo número de elementos, distinto contenido) el sha256 ya no coincide con el manifiesto: queda MODIFICADO, `ok` es falso y ni siquiera se gasta una consulta de recuento para ese archivo.
- `test_un_archivo_que_dice_ser_de_otro_instante_franja_o_fecha_queda_modificado` ×4 — Aunque el manifiesto lleve el sha256 del archivo cambiado, si DENTRO dice otro instante, otra franja u otra fecha pedida que la que le corresponde, no puede salir «completo» (p. ej. un trozo de 2024 copiado como si fuera de 2022).
- `test_un_archivo_con_distinto_numero_de_elementos_que_el_manifiesto_queda_modificado` — El manifiesto dice 4 elementos; si el archivo tiene otros, no es el descargado (aunque el sha256 se hubiera puesto a juego).
- `test_un_archivo_sin_sha256_en_el_manifiesto_no_se_puede_dar_por_completo` — Un manifiesto sin el hash del archivo no permite asegurar que sea el descargado: MODIFICADO, no «completo».
- `test_un_archivo_que_no_es_un_json_legible_queda_modificado` — Un archivo corrupto cuyo hash se pusiera a juego tampoco pasa: se comprueba que se pueda leer con `elements`.
- `test_un_archivo_intacto_deja_anotado_el_sha256_que_se_verifico` — «Completo» queda ligado al hash del archivo verificado (trazabilidad: qué archivo exacto se comprobó).
- `test_el_resumen_de_main_cuenta_los_archivos_modificados` — `--verificar` informa también de los MODIFICADOS y sale con 1.
- `test_el_total_del_servidor_debe_ser_una_cadena_de_digitos_ascii` ×13 — `int()` aceptaría «-5», «+5», « 5 » o dígitos de otros alfabetos: un recuento así no es válido y no se interpreta.
- `test_el_total_del_servidor_acepta_cadenas_de_digitos_ascii` ×3
- `test_un_archivo_cuyo_elements_no_es_una_lista_queda_modificado_aunque_tenga_la_longitud_esperada` — `elements` como cadena de 4 caracteres tiene `len` 4, como los 4 elementos del manifiesto: se comprueba el tipo.
- `test_la_huella_solo_contiene_hashes_recuentos_y_fechas_no_datos` — Es lo que se versiona en git: por archivo, sha256, elementos, fecha pedida, espejo y fecha de descarga. Ningún elemento de OSM, ni etiquetas, ni posiciones.
- `test_la_huella_coincide_con_el_manifiesto_archivo_por_archivo` — Los valores anclados son los del manifiesto verificado (sha256 incluido).
- `test_no_se_ancla_lo_que_no_esta_verificado_como_completo` — Sin `--verificar` previo (o con algún archivo incompleto) la huella se niega: no se ancla lo no comprobado.
- `test_no_se_ancla_una_descarga_incompleta` — Si falta algún trozo del plan en el manifiesto, no se escribe la huella.
- `test_no_se_ancla_un_archivo_con_verificacion_incompleta` — Un solo archivo INCOMPLETO impide anclar toda la descarga.
- `test_alterar_un_archivo_y_el_manifiesto_a_juego_se_detecta_con_la_huella` — Sin ancla externa, un archivo cambiado con el manifiesto recalculado pasa todas las comprobaciones locales; con la huella versionada, el sha256 del manifiesto ya no coincide con el anclado y queda MODIFICADO.
- `test_sin_huella_una_alteracion_conjunta_de_archivo_y_manifiesto_no_se_detecta_y_esta_declarado` — LÍMITE DECLARADO (y probado, para que nadie crea lo contrario): sin ancla externa, un manifiesto que vive junto a los datos no puede detectar que se alteraron ambos a la vez. Por eso se avisa y se recomienda versionar la huella.
- `test_cada_campo_de_la_huella_se_comprueba` ×4 — Si el manifiesto difiere de la huella en cualquiera de sus campos, el archivo queda MODIFICADO.
- `test_un_archivo_que_no_figura_en_la_huella_queda_modificado` — Un trozo que no está anclado no puede darse por íntegro.
- `test_una_huella_intacta_deja_pasar_los_archivos_intactos` — Con la huella correcta y los datos sin tocar, todo sale completo (no hay falsos positivos).
- `test_cargar_huella_sin_archivo_devuelve_none_y_con_archivo_roto_falla_a_la_vista` — Que no exista la huella es un caso normal (aviso); que exista y esté rota no se ignora en silencio.
- `test_main_huella_escribe_la_huella_y_se_niega_si_no_esta_verificado` — `--huella` escribe docs/HUELLA_OSM_HISTORY.json solo con todo verificado; si no, sale con 1 y lo explica.
- `test_main_verificar_usa_la_huella_si_existe_y_avisa_si_no` — Sin huella versionada, `--verificar` avisa de que se comprueba solo contra el manifiesto; con huella, la usa.
- `test_la_huella_real_versionada_tiene_la_forma_prometida` — `docs/HUELLA_OSM_HISTORY.json` (la real, en git) cubre exactamente los 7 trozos del plan, solo con los campos permitidos y sin ningún dato de OSM. En el CI no están los datos descargados, así que aquí solo se comprueba la forma; el contenido se contrasta con `--verificar` donde estén los datos.
- `test_una_nueva_descarga_no_sobrescribe_los_trozos_anclados_en_la_huella` — Esos datos NO están en git: volver a descargar (`--instantes hoy` o la descarga completa) los pisaría sin remedio y, además, los dejaría «MODIFICADOS» frente a la huella. Con la huella dada, se omiten y se anotan en `omitidos`.
- `test_con_sobrescribir_si_se_vuelve_a_descargar_lo_anclado` — `sobrescribir=True` (`--sobrescribir`) es la salida explícita para forzar la descarga de lo anclado.
- `test_un_trozo_que_no_esta_anclado_si_se_descarga_aunque_haya_huella` — Solo se protege lo que figura en la huella y existe en disco: un trozo ausente se descarga normalmente.
- `test_el_procedimiento_para_reanclar_tras_sobrescribir_tiene_salida` — Sin esta salida era un callejón: tras sobrescribir, la huella vieja marca MODIFICADO y no se podía volver a anclar. Con `--verificar --sin-huella` se verifica sin exigirla, y entonces `--huella` ancla lo nuevo.
- `test_main_verificar_con_sin_huella_no_exige_la_huella` — `--sin-huella` verifica sin comparar con la huella (y sin el aviso de que no existe).
- `test_una_interrupcion_al_escribir_no_deja_un_archivo_a_medias_ni_un_completo_caducado` — Ctrl+C o un fallo de disco mientras se reescribe un trozo: el archivo antiguo queda íntegro (escritura atómica) o, si ya se había quitado su entrada, el manifiesto no lo da por «completo»: nunca archivo nuevo + entrada antigua.
- `test_el_manifiesto_se_guarda_tras_cada_trozo_y_no_solo_al_final` — Si la descarga muere a mitad (aquí, al tercer trozo), el manifiesto ya recoge los dos primeros.
- `test_exigir_datos_verificados_devuelve_las_rutas_si_todo_esta_completo` — Con los 7 trozos completos, intactos y que coinciden con la huella, devuelve `{archivo: ruta}`.
- `test_exigir_datos_verificados_se_niega_si_algo_no_esta_verificado` — Descargado pero sin `--verificar`: el análisis no puede usarlo.
- `test_exigir_datos_verificados_se_niega_si_el_archivo_en_disco_ya_no_es_el_verificado` — Una descarga interrumpida (archivo nuevo junto a un manifiesto antiguo «completo») no pasa: se compara el sha256 del archivo EN DISCO con el verificado.
- `test_exigir_datos_verificados_lista_todos_los_problemas_y_sin_manifiesto_falla` — Sin descargar nada: error claro. Con varios problemas: se listan todos, no solo el primero.
- `test_exigir_datos_verificados_detecta_una_alteracion_conjunta_si_se_da_la_huella` — Archivo y manifiesto alterados a juego: con la huella del repo, el análisis se niega.
- `test_escribir_huella_se_niega_a_anclar_un_archivo_distinto_del_verificado` — Si en disco hay otro archivo (descarga interrumpida) con el manifiesto antiguo «completo», no se ancla su hash viejo.
- `test_main_con_una_huella_rota_sale_con_error_claro_no_con_un_traceback` — Una huella ilegible no se ignora en silencio, pero tampoco revienta: mensaje y código 1 (en cualquier modo).
- `test_main_verificar_sin_manifiesto_sale_con_error_claro` — Sin descargar nada o con un manifiesto ilegible: mensaje y código 1, no un traceback.
- `test_cargar_huella_rechaza_entradas_que_no_son_objetos` ×3 — Una entrada que no sea un objeto reventaría más tarde con un AttributeError: se rechaza al cargar.
- `test_huella_con_otro_out_no_puede_sobrescribir_la_huella_real` — `--huella --out <otra carpeta>` escribiría hashes de otros datos en docs/HUELLA_OSM_HISTORY.json: se niega y pide un destino explícito.
- `test_huella_no_se_combina_con_otros_modos` ×4 — Antes `--huella` ignoraba en silencio `--verificar` y `--dry-run`: ahora es un error explícito.
- `test_sin_huella_solo_vale_con_verificar`
- `test_la_pausa_que_indica_el_usuario_tambien_se_aplica_tras_el_canario` — Con `pausa_s=7` la pausa tras cada canario nuevo es de 7 s, no la constante de 12 (antes `--pausa 0` seguía esperando).
- `test_descargar_aplica_su_pausa_tras_el_canario_y_entre_trozos` — Con `pausa_s=7` (lo que sería `--pausa 7`): 7 s tras el canario de 2022 y 7 s entre los dos trozos.
- `test_escribir_atomico_deja_intacto_el_archivo_si_falla_el_reemplazo` — La escritura es de verdad atómica: se escribe a un temporal y se reemplaza. Si el reemplazo falla (disco, permisos, interrupción), el archivo definitivo conserva su contenido anterior ENTERO (no se queda a medias).
- `test_escribir_atomico_sin_fallo_deja_el_contenido_nuevo_y_ningun_temporal`
- `test_escribir_huella_se_niega_si_se_verifico_otro_archivo_distinto_del_que_hay_en_disco` — Aunque el manifiesto y el disco coincidan, si `sha256_verificado` es de OTRO archivo (verificado antes de que cambiara), «completo» no corresponde a lo que hay: no se ancla.
- `test_main_al_descargar_respeta_lo_anclado_y_con_sobrescribir_lo_vuelve_a_bajar` — De extremo a extremo por la línea de comandos: con la huella versionada, `main` no pisa lo anclado (lo dice y sale con 0); con `--sobrescribir` sí lo descarga.
- `test_escribir_huella_se_niega_si_el_sha256_del_manifiesto_no_es_el_del_disco` — Aunque `sha256_verificado` coincida con el disco, un `sha256` del manifiesto que no sea el del archivo actual indica un manifiesto desfasado: no se ancla.
- `test_sin_sha256_verificado_el_analisis_no_acepta_el_archivo` — Una entrada «completo» sin constancia de qué archivo se verificó NO es utilizable: antes el campo ausente se sustituía por el hash del manifiesto y pasaba.
- `test_sin_sha256_verificado_tampoco_se_ancla` — `escribir_huella` repetía el mismo fallback: ahora exige el campo y que coincida con el disco y el manifiesto.
- `test_el_procedimiento_para_recuperar_un_manifiesto_sin_sha256_verificado_es_verificar_de_nuevo` — El mensaje manda ejecutar `--verificar` de nuevo, y eso funciona: vuelve a registrar el campo y entonces sí se puede usar y anclar.

## `tests/test_ensemble_predictor.py`

> Unit tests for ensemble predictor.

- `test_ensemble_initialization` — Test ensemble predictor initialization.
- `test_feature_preparation` — Test feature preparation.
- `test_model_training` — Test ensemble model training.
- `test_prediction_output` — Test prediction output format.
- `test_anomaly_detection` — Test anomaly detection.
- `test_insufficient_data` — Test handling of insufficient data.
- `test_train_informa_la_r2_fuera_de_muestra_ademas_de_la_de_entrenamiento` — Cada modelo trae `r2_entrenamiento` (en muestra) y `r2` y `mae` fuera de muestra; el resumen va en `holdout`.
- `test_con_ruido_puro_la_r2_en_muestra_engana_y_la_de_fuera_de_muestra_no` — Los bosques profundos se aprenden de memoria los datos de entrenamiento: con ruido puro la R² en muestra sale alta (lo que se informaba antes) y fuera de muestra no pasa de ~0. Es la razón de medir fuera de muestra.
- `test_el_corte_es_cronologico_aunque_las_filas_lleguen_de_la_mas_reciente_a_la_mas_antigua` — La base entrega las filas de la más reciente a la más antigua: el corte debe ordenarlas antes, y el tramo de prueba es el 20 % más reciente por fecha.
- `test_la_referencia_de_ultimo_valor_se_calcula_con_la_medicion_anterior_de_la_misma_fuente` — Con dos fuentes alternando, el «último valor» de cada fila es el de la misma fuente, no el de la fila contigua.
- `test_el_tramo_de_prueba_es_el_mas_reciente_y_la_media_de_referencia_sale_del_entrenamiento` — Con un cambio de nivel al final (10 min las primeras 320 filas, 30 las últimas 80), el tramo de prueba tiene que ser el final: la media del entrenamiento (10) se equivoca en ~20 min sobre él. Si se midiera con el tramo antiguo, o la media se calculara con el de prueba, ese error sería muy distinto.
- `test_supera_a_ultimo_valor_es_verdadero_cuando_las_variables_si_predicen` — Si el tiempo de viaje depende de la hora (par o impar) y la fila anterior siempre es de la otra paridad, repetir la última medición se equivoca en 10 min y el ensemble, que ve la hora, casi no: tiene que ganar.
- `test_el_ensemble_pondera_los_modelos_y_normaliza_los_pesos_sobre_los_que_hay` — La predicción del ensemble es el promedio ponderado de los modelos disponibles, con los pesos normalizados: sin xgboost instalado, los pesos de los otros dos se reescalan para sumar 1.
- `test_con_pocas_filas_no_se_mide_fuera_de_muestra_y_solo_queda_la_r2_en_muestra` — Con menos de 100 filas no hay tramo de prueba fiable: se entrena igualmente, pero sin `r2`, y se dice por qué.
- `test_sin_timestamp_no_hay_corte_cronologico` — Sin columna de fecha no se puede ordenar el tiempo: no se inventa un corte.
- `test_el_modelo_definitivo_se_reajusta_con_todos_los_datos` — Tras medir con el 80 %, el modelo que se guarda y se usa para predecir se ajusta con las 400 filas.
- `test_model_save_load` — Test model saving and loading.

## `tests/test_forecasting.py`

> Tests del pronóstico horario (src/forecasting.py) y de su validación (tools/validate_forecast.py).

- `test_el_sarima_converge_y_pronostica_en_escala_original` — El pronóstico a 24 h converge (antes no lo hacía), queda en la escala 0-1 y el IC lo envuelve.
- `test_el_sarima_aprende_el_ciclo_diario` — Con un ciclo diario claro, el pronóstico sigue el perfil mejor que una media plana.
- `test_las_horas_sin_dato_no_se_inventan` — hourly_share deja NaN en las horas sin mediciones; solo se interpolan huecos cortos al ajustar.
- `test_perfil_horario_y_su_pronostico` — La referencia usa la media de cada hora del día; para una hora sin historia cae a la media global.
- `test_mae_ignora_las_posiciones_sin_dato` — El MAE salta las posiciones con NaN y devuelve `None` si no queda ninguna con dato.
- `test_los_cortes_exigen_horizonte_y_pasado_con_datos` — Un corte de validación exige una semana de pasado con datos y un horizonte que no esté vacío; si el horizonte queda en NaN deja de ser elegible.
- `test_las_referencias_no_usan_datos_del_futuro` — Cambiar los valores a partir del corte no debe alterar ninguna referencia.
- `test_la_validacion_compara_con_las_referencias` — evaluate + summarize: con un ciclo diario limpio el perfil y el SARIMA ganan a media y persistencia.
- `test_la_validacion_lee_la_base_en_solo_lectura` — load_hourly_share abre la base con immutable=1: no crea -wal/-shm ni modifica el archivo.

## `tests/test_formatter_pins.py`

> Las versiones de black e isort están fijadas en varios sitios; que no se desincronicen.
>
> Cada versión mayor de black puede cambiar el formato, así que el CI y `requirements-dev.txt` tienen que
> usar la misma. Si una copia se actualiza y otra no, el chequeo bloqueante pasa en local y falla en el CI.

- `test_black_tiene_la_misma_version_fijada_en_el_ci_los_requisitos_y_el_readme` — `black==X` aparece con la misma versión en el workflow, en requirements-dev.txt y en el README.
- `test_isort_tiene_la_misma_version_fijada_en_el_ci_los_requisitos_y_el_readme` — `isort==X` aparece con la misma versión en el workflow, en requirements-dev.txt y en el README.
- `test_el_ci_comprueba_el_formato_de_todos_los_archivos_de_codigo_sin_neutralizar_el_paso` — Black e isort se ejecutan en modo comprobación sobre todo el código, sin `|| true` ni opciones propias.
- `test_los_archivos_formateados_existen_y_pyproject_fija_la_configuracion` — Las rutas que formatea el CI existen, y la línea de 120 y el perfil black salen de pyproject.toml.

## `tests/test_foursquare_client.py`

> Pruebas de la categorización y de los puntos de búsqueda de Foursquare.
>
> No hacen llamadas de red: solo ejercitan la lógica pura del cliente.

- `test_categoriza_nombres_reales_de_foursquare` ×17 — Cada nombre de categoría real de Foursquare (parametrizado) cae en el balde esperado.
- `test_barbershop_no_se_confunde_con_bar` — Regresión: "bar" dentro de "Barbershop" no puede mandarlo a restaurant (se usa \b, no un simple `in`).
- `test_nunca_descarta_un_poi_sin_categoria` — Una lista de categorías vacía, `None` o un nombre desconocido devuelve «other»; el POI nunca se descarta.
- `test_sin_rutas_solo_devuelve_las_zonas` — Sin rutas, los puntos de búsqueda son solo las zonas.
- `test_con_las_rutas_actuales_son_27_llamadas` — El README documenta 7 zonas + 20 puntos intermedios = 27 llamadas por refresco (~117/mes con refresco semanal, 23% del límite gratis).
- `test_no_duplica_corredores_en_sentido_inverso` — Valletta->Birkirkara y Birkirkara->Valletta son el mismo tramo físico.
- `test_puntos_intermedios_quedan_entre_origen_y_destino` — Los puntos intermedios de una ruta larga caen dentro del rectángulo que forman su origen y su destino.
- `test_ignora_rutas_con_zonas_desconocidas` — Una ruta con una zona que no existe se ignora y no añade puntos.
- `test_acepta_la_forma_nueva_de_la_respuesta` — Se interpreta la respuesta nueva de la API (`fsq_place_id` con latitud y longitud planas).
- `test_acepta_la_forma_antigua_con_geocodes` — Se interpreta la respuesta antigua de la API (`fsq_id` con coordenadas dentro de `geocodes`).
- `test_descarta_lugares_sin_id_o_sin_coordenadas` — Un lugar sin identificador o sin coordenadas se descarta.
- `test_cliente_exige_api_key` — Crear el cliente con una clave de API vacía lanza `ValueError`.

## `tests/test_hybrid_scheduler.py`

> Pruebas para HybridScheduler: cada fuente debe dispararse en su propio
> intervalo, sin interferir con la otra, y Ctrl+C debe cerrar ambos clientes.

- `test_ors_and_tomtom_fire_on_independent_schedules` — Con 15/27 min en 120 min simulados: ORS 9 veces, TomTom 5 veces.
- `test_both_sources_fire_immediately_on_first_tick` — En el minuto 0 (last_run=None), ambas fuentes deben disparar de inmediato.
- `test_signal_handler_requests_stop_and_close_closes_both_collectors` — La señal (Ctrl+C o SIGTERM) solo pide parar, sin salir: el ciclo en curso termina. Al salir del bucle, close() cierra los clientes (traffic_client y weather) de AMBOS collectors.

## `tests/test_license.py`

> Tests de la licencia del repositorio: el archivo LICENSE, su declaración en setup.py y su mención en el README.

- `test_el_archivo_license_es_el_texto_estandar_de_mit_con_el_titular` — LICENSE existe, es MIT y lleva el año y el titular elegidos (rodgutzal).
- `test_setup_declara_la_licencia_mit_y_no_un_clasificador_obsoleto` — setup.py declara license="MIT" (expresión SPDX). No usa el clasificador "License :: ...", obsoleto en setuptools moderno, ni conserva el comentario que decía que el repo no tenía licencia.
- `test_el_readme_enlaza_la_licencia_y_avisa_de_que_no_cubre_los_datos_de_terceros` — El README dice que el código es MIT, enlaza LICENSE y advierte de que la licencia no cubre datos de terceros.
- `test_los_datos_de_terceros_que_el_readme_dice_que_estan_en_el_repositorio_existen` — El README enumera datos de terceros versionados; si se retiran del repositorio, el aviso debe actualizarse.

## `tests/test_location_scoring.py`

> Pruebas del sistema de puntuación de zonas (MCDA) de location_scoring.py.
>
> Usan una RouteDatabase real sobre un directorio temporal (no mocks), para
> ejercitar también los métodos de database.py que consume el módulo.

- `test_haversine_conocida` — La distancia haversine da el valor conocido (0,01 grados de latitud son unos 1112 m) y 0 para el mismo punto.
- `test_normalize_minmax_basico` — La normalización min-max lleva el mínimo a 0, el máximo a 1 y el punto medio a 0,5.
- `test_normalize_minmax_sin_variacion_queda_en_medio_no_en_cero` — Si todos los valores son iguales, la normalización los deja en 0,5 y no en 0.
- `test_normalize_minmax_conserva_nan` — La normalización min-max conserva los NaN y normaliza el resto.
- `test_demanda_sin_demografia_es_nan_no_cero` — Sin datos demográficos, la demanda de cada zona es NaN, no 0.
- `test_demanda_lee_poblacion_guardada` — La demanda de una zona es su población guardada; las zonas sin dato quedan en NaN.
- `test_competencia_cuenta_solo_dentro_del_radio` — La competencia cuenta solo los comercios dentro del radio de la zona y la marca como observada.
- `test_competencia_filtra_por_categoria` — La competencia solo cuenta los POIs de la categoría pedida.
- `test_competencia_food_drink_se_corrige_por_cobertura_de_osm` — En restauración y bares, la competencia se corrige dividiendo entre la cobertura de OpenStreetMap y lo indica en el método.
- `test_competencia_sin_pois_es_cero` — Sin POIs, la competencia de todas las zonas es 0.
- `test_accesibilidad_promedia_rutas_que_tocan_la_zona` — La accesibilidad de una zona es el tiempo de viaje medio de las rutas que la tocan; una zona sin rutas queda en NaN.
- `test_pesos_por_defecto_suman_uno` — Los pesos por defecto suman 1 y valen 0,40, 0,35 y 0,25.
- `test_pesos_que_no_suman_uno_lanzan_error` — Unos pesos que no suman 1 lanzan `ValueError`.
- `test_mas_demanda_mejora_el_puntaje` — A igualdad de lo demás, más demanda mejora el puntaje de la zona.
- `test_mas_competencia_empeora_el_puntaje` — A igualdad de lo demás, más competencia empeora el puntaje.
- `test_mas_tiempo_de_viaje_empeora_el_puntaje` — A igualdad de lo demás, más tiempo de viaje empeora el puntaje.
- `test_zona_sin_dato_se_trata_como_neutral_no_como_la_peor` — Una zona sin dato en una dimensión se trata como neutral (0,5), no como la peor, y se anota cuántas dimensiones tenían dato.
- `test_un_peso_en_cero_ignora_esa_dimension` — Un peso en 0 hace que esa dimensión no influya en el puntaje.
- `test_el_puntaje_queda_entre_0_y_1` — El puntaje de cada zona queda entre 0 y 1.
- `test_recomienda_de_extremo_a_extremo` — La recomendación de extremo a extremo devuelve todas las zonas ordenadas por puntaje y con el desglose completo, no solo el puntaje final.
- `test_recomendar_con_texto_incomprensible_lanza_error` — Un texto que no se entiende como negocio lanza `ValueError`.
- `test_recomendar_acepta_pesos_personalizados` — Con pesos personalizados, todo el peso en demanda hace ganar a la zona más poblada.
- `test_recomendar_con_modelo_usa_el_modelo_solo_si_las_palabras_clave_no_reconocen` — Un texto que las palabras clave no reconocen se interpreta con el modelo; uno que sí reconocen ignora al modelo.
- `test_recomendar_sin_modelo_sigue_fallando_con_un_texto_que_las_palabras_clave_no_reconocen` — Sin modelo (el comportamiento por defecto) un texto desconocido da el mismo error de siempre.
- `test_recomendar_por_categoria_da_lo_mismo_que_recomendar_por_texto` — `recommend_for_category` es la segunda mitad de `recommend_locations`: para la misma categoría, el mismo resultado.

## `tests/test_locations.py`

> Pruebas para el módulo de ubicaciones.

- `test_locations_exist` — Verifica que todas las ubicaciones estén definidas.
- `test_routes_exist` — Verifica que todas las rutas estén configuradas.
- `test_get_location` — Verifica que se puede obtener una ubicación por nombre.
- `test_get_all_unique_locations` — Verifica que se retornan todas las ubicaciones únicas.
- `test_invalid_location` — Verifica que se lanza error para ubicación inexistente.

## `tests/test_medallion.py`

> Pruebas del pipeline medallion (Bronze -> Silver -> Gold).

- `test_bronze_inserta_las_filas_validas` — Bronze inserta todas las filas válidas y devuelve cuántas.
- `test_bronze_es_idempotente_reingerir_no_duplica` — Regresión: Bronze no tenía restricción UNIQUE y reingerir las mismas filas (p. ej. al correr run_medallion_pipeline dos veces) las duplicaba.
- `test_bronze_ingiere_solo_lo_nuevo` — Bronze ingiere solo las filas nuevas: las que ya existen no se vuelven a insertar.
- `test_bronze_rechaza_datos_sin_columnas_requeridas` — Bronze rechaza un lote al que le falta una columna requerida.
- `test_bronze_descarta_duplicados_dentro_del_lote` — Bronze descarta los duplicados dentro del mismo lote.
- `test_bronze_descarta_tiempos_fuera_de_rango_y_nulos` — Bronze descarta las filas con tiempo de viaje fuera de rango o nulo.
- `test_bronze_guarda_timestamps_iso_con_t` — Regresión: pandas.to_sql guardaba un espacio en vez de 'T' y el collector nunca encontraba las filas de Bronze para pasárselas a Silver.
- `test_silver_transforma_y_agrega_variables_temporales` — Silver transforma las filas de Bronze y calcula el retraso, el nivel de congestión y las variables temporales como la hora y el fin de semana.
- `test_silver_sin_tiempo_sin_trafico_deja_el_retraso_desconocido` — ORS no reporta tiempo sin tráfico: el retraso no se inventa.
- `test_silver_no_duplica_al_transformar_dos_veces` — Transformar dos veces el mismo lote en Silver no duplica filas.
- `test_silver_perfil_de_ruta_calcula_la_desviacion_sin_stddev_de_sql` — Regresión: get_route_profile usaba STDDEV(), que SQLite no trae.
- `test_silver_agregacion_horaria` — Silver agrega los datos por hora y crea un registro por cada grupo.
- `test_gold_calcula_kpis_por_ruta` — Gold calcula los KPI de cada ruta del día: promedio, número de muestras y fiabilidad entre 0 y 100.
- `test_gold_recalcular_el_mismo_dia_no_falla_ni_duplica` — Regresión: el INSERT plano chocaba con UNIQUE(date, origin, destination) la segunda vez que se calculaban las KPIs de un mismo día.
- `test_gold_dia_sin_datos` — Gold devuelve «no_data» para un día sin datos.
- `test_gold_ranking_ordena_por_fiabilidad` — El ranking de Gold ordena las rutas por fiabilidad y pone primero la más estable.
- `test_gold_metricas_de_periodo` — Las métricas de periodo de Gold dan promedio y fiabilidad con datos, y valores vacíos con cero filas si el periodo no tiene.
- `test_gold_resumen_ejecutivo_en_base_vacia_devuelve_ceros_no_error` — Regresión: AVG()/SUM() sin filas dan NULL y float(NaN) reventaba, así que en un clon limpio (sin histórico) Executive mostraba "Error loading summary data".
- `test_gold_resumen_ejecutivo_con_datos` — El resumen ejecutivo de Gold cuenta rutas y mediciones y da el tiempo de viaje promedio del sistema.
- `test_pipeline_completo_es_idempotente` — El pipeline completo (Bronze, Silver y Gold) es idempotente: ejecutarlo de nuevo no cambia los recuentos de cada capa.

## `tests/test_merge_legacy_data.py`

> Pruebas de la herramienta de fusión heredada (`tools/merge_legacy_data.py`).

- `test_sin_el_csv_de_tomtom_se_detiene_sin_tocar_la_base` — El CSV de TomTom ya no se publica. La herramienta borra la base unificada antes de regenerarla, así que sin ese archivo debe salir con un mensaje claro y dejar la base intacta (no sustituirla por una a medias).

## `tests/test_migrations.py`

> Tests de las migraciones del CSV histórico: a SQLite (src/migration.py) y a TimescaleDB (src/timescale_migration.py).
>
> Sin Postgres real: `psycopg2` se sustituye por un módulo falso que guarda las filas que se habrían insertado.

- `test_migra_el_csv_a_sqlite` — Migra las filas del CSV a SQLite conservando la fuente, el tiempo de viaje, el clima y los nulos.
- `test_dry_run_no_crea_la_base` — Con `dry_run`, cuenta las filas pero no crea la base de datos.
- `test_descarta_filas_sin_campos_obligatorios` — Se descartan las filas a las que les falta el timestamp o el origen.
- `test_data_source_vacio_o_ausente_pasa_a_unknown` — Una fuente de datos vacía o ausente en el CSV se guarda como «unknown».
- `test_un_valor_numerico_ilegible_queda_nulo_sin_romper_la_migracion` — Un valor numérico ilegible queda como nulo y la fila se migra igualmente.
- `test_csv_inexistente_vacio_o_sin_columnas_obligatorias_devuelve_cero` — Un CSV inexistente, vacío o sin las columnas obligatorias devuelve 0 filas y no crea la base.
- `test_las_lineas_corruptas_del_csv_se_saltan` — Las líneas corruptas del CSV se saltan y se migran las demás.
- `test_migrar_dos_veces_no_duplica_filas` — El índice único de Bronze/route_measurements hace idempotente la migración.
- `test_cli_dry_run_no_pide_confirmacion` — La línea de comandos con `--dry-run` no pide confirmación y migra en modo ensayo.
- `test_cli_cancelada_no_migra` — Si el usuario cancela la confirmación, no se migra nada.
- `test_cli_confirmada_o_con_skip_migra_y_usa_las_rutas_del_proyecto` — Con confirmación o `--skip-confirmation` se migra usando las rutas del CSV y de la base del proyecto.
- `test_cli_devuelve_error_si_no_se_importa_nada_o_falla` — La línea de comandos devuelve código de error si no se importa ninguna fila o la migración falla.
- `test_backfill_inserta_las_filas_con_el_orden_de_columnas_de_traffic_trips` — El backfill a Timescale inserta cada fila de `traffic_trips` con el orden de columnas correcto y hace commit.
- `test_backfill_celdas_vacias_van_como_null_y_no_como_nan` — Regresión: una celda vacía llegaba como NaN (float) incluso a columnas de texto (origin_weather), que Postgres rechaza; con ello fallaba y se revertía todo el backfill. Ahora es None (NULL), y data_source vacío pasa a 'unknown' como en la migración a SQLite.
- `test_backfill_con_error_hace_rollback_y_devuelve_cero` — Si el backfill falla, hace rollback, cierra la conexión y devuelve 0.
- `test_backfill_csv_inexistente_o_vacio_no_se_conecta` — Con un CSV inexistente o vacío, el backfill no abre ninguna conexión.
- `test_backfill_sin_psycopg2_instalado_devuelve_cero` — Si `psycopg2` no está instalado, el backfill devuelve 0 en vez de fallar.
- `test_backfill_main_devuelve_el_codigo_segun_las_filas` — `main` del backfill devuelve 0 si migró filas y 1 si no migró ninguna.

## `tests/test_ml_context.py`

> Tests de la fase 1b: contexto de OpenStreetMap (src/ml/osm_context.py) y su efecto en las lentes, las variables y los
> modelos, y la herramienta de descarga tools/download_osm_context.py (sin red: cliente falso).

- `test_edificios_se_convierten_con_su_tipo_y_yes_por_defecto` — Los edificios de OSM se convierten en POIs de categoría «edificio» con su tipo como subcategoría, y «yes» si no tienen tipo.
- `test_los_elementos_sin_coordenadas_se_descartan` — Los elementos de OSM sin coordenadas se descartan.
- `test_transporte_conserva_paradas_y_descarta_las_posiciones_duplicadas` — En transporte se conservan paradas, estaciones, andenes y terminales de ferry, y se descartan las posiciones de parada duplicadas.
- `test_alojamiento_e_industria` — Alojamiento e industria se convierten en POIs con el tipo de OSM como subcategoría.
- `test_un_tema_desconocido_o_sin_uso_da_un_dataframe_vacio_con_las_columnas` — Un tema desconocido o que no se usa devuelve una tabla vacía pero con sus columnas.
- `test_load_context_lee_los_json_ignora_los_corruptos_y_un_directorio_vacio_da_vacio` — `load_context` lee los JSON de la carpeta, ignora los corruptos y devuelve una tabla vacía si el directorio no tiene datos.
- `test_no_residenciales_excluye_lo_que_no_es_vivienda` — La lista de edificios no residenciales incluye los industriales, iglesias, escuelas y garajes, y no las viviendas.
- `test_las_celdas_activas_no_cambian_al_cargar_el_contexto` — Un edificio lejos de cualquier POI no activa una celda: así el conjunto de celdas es el mismo con y sin contexto.
- `test_residentes_cuenta_edificios_pero_no_los_industriales` — La lente de residentes cuenta los edificios de vivienda de la celda pero no los industriales.
- `test_los_hoteles_cuentan_como_turistas_aunque_no_haya_atracciones` — Los hoteles cuentan como turistas en su celda aunque no haya atracciones.
- `test_sin_contexto_residentes_y_turistas_siguen_sin_datos` — Sin contexto de OSM, las lentes de residentes y turistas quedan sin dato (NaN).
- `test_el_indice_de_mercado_va_de_0_a_1_y_los_edificios_no_aplastan_a_los_demas_segmentos` — Regresión: mercado_total sumaba conteos en bruto, y con ~90 edificios por celda frente a ~1 colegio el índice era solo 'cuántos edificios hay'. Ahora cada segmento se escala por su máximo antes de promediar.
- `test_el_indice_de_mercado_es_una_media_y_no_una_suma` — Una celda que es el máximo en TODOS los segmentos con datos vale exactamente 1 (con una suma valdría 2).
- `test_las_variables_incluyen_el_contexto_solo_si_se_piden` — Las variables del modelo incluyen las de contexto solo si se piden, y el índice de celdas es el mismo.
- `test_boosting_poi_no_usa_las_variables_de_contexto_y_solo_edificios_solo_esas` — El modelo `boosting_poi` no usa las variables de contexto y `solo_edificios` usa únicamente las de edificios.
- `test_los_modelos_opcionales_predicen_valores_positivos` — Los modelos opcionales (parametrizado) predicen valores positivos, por encima del mínimo esperado.
- `test_el_boosting_con_contexto_gana_al_que_no_lo_tiene_cuando_la_senal_esta_en_el_contexto` — Cuando la señal está en el contexto, el boosting con contexto gana al que no lo usa y la comparación lo marca como mejora.
- `test_compare_models_con_el_mismo_modelo_es_indistinguible` — Comparar un modelo consigo mismo da diferencia cero y veredicto «indistinguible».
- `test_validate_location_model_con_contexto_informa_si_el_contexto_aporta` — El script de validación con contexto informa de si el contexto aporta y no modifica la base de datos.
- `test_validate_location_model_sin_contexto_no_evalua_los_modelos_opcionales` — Sin contexto, el script de validación no evalúa los modelos opcionales.
- `test_validate_location_model_con_un_directorio_de_contexto_vacio_valida_sin_contexto` — Con un directorio de contexto vacío, el script valida sin contexto y lo avisa.
- `test_measure_lens_variance_con_contexto_da_datos_a_residentes` — El script de varianza de lentes, con contexto, da datos a la lente de residentes.
- `test_las_franjas_cubren_toda_el_area_sin_huecos_ni_solapes` — Las franjas de descarga cubren toda el área sin huecos ni solapes, y pedir 0 franjas lanza `ValueError`.
- `test_la_consulta_lleva_el_bbox_el_timeout_del_servidor_y_pide_centro_y_etiquetas` — La consulta lleva el rectángulo, el timeout del servidor y pide el centro y las etiquetas.
- `test_el_plan_pide_siete_trozos_y_el_edificado_va_en_franjas` — El plan de descarga pide siete trozos y el edificado va dividido en tres franjas.
- `test_descargar_guarda_un_archivo_por_trozo_y_resume` — La descarga guarda un archivo por trozo y devuelve el resumen de elementos y trozos por tema.
- `test_se_espera_entre_peticiones_pero_no_despues_de_la_ultima` — Cortesía con el servicio público: pausa entre peticiones, y ninguna espera inútil al terminar.
- `test_si_un_espejo_falla_se_prueba_el_siguiente` — Si un espejo de Overpass falla, se prueba el siguiente.
- `test_si_todos_los_espejos_fallan_lanza_runtimeerror` — Si todos los espejos fallan, se lanza `RuntimeError`.
- `test_un_trozo_fallido_se_anota_y_el_resto_se_descarga` — Un trozo fallido se anota en el resumen y el resto se descarga.
- `test_dry_run_no_hace_llamadas_de_red_ni_crea_la_carpeta` — Con `--dry-run` no se crea el cliente, no hay llamadas de red y no se crea la carpeta de salida.
- `test_main_descarga_con_un_cliente_falso_y_devuelve_el_codigo_segun_los_fallos` — `main` devuelve 0 si la descarga va bien y 1 si algún trozo falla.
- `test_la_descarga_no_escribe_fuera_del_directorio_indicado` — La descarga solo escribe dentro de la carpeta indicada.

## `tests/test_ml_grid.py`

> Tests de la rejilla de ~250 m (src/ml/grid.py) y de los conteos por celda (src/ml/cell_counts.py).

- `test_la_rejilla_es_fija_y_cubre_el_area` — La rejilla tiene forma fija (45 por 51 celdas) y cubre los POIs conocidos y los centros de las 7 zonas.
- `test_las_celdas_miden_unos_250_m_en_las_dos_direcciones` — Las celdas miden unos 250 m en latitud y en longitud.
- `test_un_punto_cae_en_la_celda_cuyo_centro_esta_cerca` — Un punto cae en la celda correcta y su centro queda a menos de 0,71 veces el lado de la celda.
- `test_puntos_fuera_de_la_rejilla_o_sin_coordenadas_dan_menos_uno` — Un punto fuera de la rejilla o sin coordenadas recibe el índice -1.
- `test_los_bordes_de_la_rejilla` — Los bordes de la rejilla: la esquina suroeste está dentro y justo fuera da -1.
- `test_identificadores_de_celda` — Los identificadores de celda se escriben `rNNcNN`, se leen de vuelta y un formato incorrecto lanza `ValueError`.
- `test_cells_frame_tiene_todas_las_celdas_y_cada_centro_cae_en_su_celda` — La tabla de celdas tiene todas las celdas, con identificador único, y el centro de cada una cae en su propia celda.
- `test_count_grid_cuenta_por_celda_e_ignora_lo_de_fuera` — `count_grid` cuenta los puntos por celda e ignora los que están fuera de la rejilla.
- `test_los_anillos_tienen_las_celdas_esperadas` ×4 — Cada anillo de vecindad (parametrizado) cubre el número de celdas esperado.
- `test_la_suma_por_anillos_pondera_la_vecindad` — La suma por vecindad pondera 1 la celda, 0,5 el primer anillo y 0,25 el segundo, y nada más allá.
- `test_los_bordes_no_dan_la_vuelta` — La suma por vecindad no da la vuelta en los bordes de la rejilla.
- `test_activas_son_las_celdas_con_algun_poi_en_ella_o_en_su_vecindad` — Las celdas activas son las que tienen algún POI en ellas o en su vecindad.
- `test_selector_toda_la_categoria_un_subconjunto_o_todo_menos_algo` — Un selector puede abarcar toda una categoría, un subconjunto de subcategorías o todo salvo algunas.
- `test_los_conteos_se_separan_por_categoria_y_subcategoria` — Los conteos por celda se separan por categoría y subcategoría y se pueden agregar con un selector.
- `test_subcategoria_vacia_o_nula_se_cuenta_como_cadena_vacia` — Una subcategoría vacía o nula se cuenta como cadena vacía.
- `test_los_pois_fuera_de_la_rejilla_se_cuentan_aparte` — Los POIs fuera de la rejilla o sin categoría no entran en la cuenta de celdas y los de fuera se cuentan aparte.
- `test_sin_pois_los_conteos_estan_vacios_pero_las_consultas_funcionan` — Sin POIs los conteos quedan vacíos pero las consultas siguen funcionando.
- `test_exclude_quita_del_conteo_lo_que_cumple_el_objetivo` — `exclude` quita del conteo lo que cumple el selector excluido.
- `test_la_tabla_celda_por_subcategoria` — La tabla celda por subcategoría tiene solo las celdas activas, con conteos enteros y una columna por subcategoría.

## `tests/test_ml_inputs_bundle.py`

> Tests de la fase 1c: paquete de entrada del ML para entrenar en otra máquina (src/ml/inputs_bundle.py), su
> exportador tools/export_ml_inputs.py y que las herramientas de la fase 0 y 1 aceptan el paquete en `--db`.

- `test_table_hash_no_depende_del_orden_de_las_filas` — El hash de una tabla es el mismo aunque cambie el orden de las filas.
- `test_table_hash_detecta_un_cambio_de_valor` — Cambiar un solo valor cambia el hash.
- `test_table_hash_distingue_columnas_y_nulos` — Un nulo no es lo mismo que un 0, y otra columna con los mismos valores da otro hash.
- `test_table_hash_tabla_vacia_es_estable` — Una tabla sin filas tiene un hash definido (no falla) y depende de sus columnas.
- `test_el_paquete_se_lee_igual_que_la_base` — Las funciones de data_access devuelven lo mismo con el paquete que con la base de origen.
- `test_las_rutas_se_agregan_por_par_origen_destino` — El paquete guarda un tiempo medio por par (no las mediciones) y lleva cuántas mediciones lo respaldan.
- `test_el_paquete_no_trae_la_polilinea_ni_columnas_innecesarias` — Se excluye lo que el ML no usa (la polilínea es lo que más pesa en la base real).
- `test_el_paquete_pesa_mucho_menos_que_la_base` — Con mediciones de rutas voluminosas, el paquete es una fracción del tamaño de la base.
- `test_exportar_no_modifica_la_base_de_origen` — La base de origen queda byte a byte igual.
- `test_no_pisa_un_paquete_existente_sin_sobrescribir` — Con el archivo ya creado falla, y con sobrescribir=True lo reemplaza.
- `test_el_paquete_no_puede_ser_la_base_de_origen` — Exportar sobre la propia base está prohibido incluso con sobrescribir (la destruiría).
- `test_sin_pois_no_hay_nada_que_exportar` — Una base sin POIs (o sin la tabla) se rechaza en lugar de producir un paquete vacío.
- `test_las_tablas_opcionales_ausentes_quedan_vacias` — Sin Foursquare, demografía ni rutas, el paquete se crea y las zonas quedan con NaN, no con 0.
- `test_un_paquete_recien_exportado_es_integro` — verify_bundle no encuentra problemas en un paquete sin tocar.
- `test_verify_detecta_un_valor_alterado` — Cambiar un valor sin cambiar el número de filas se detecta por el hash.
- `test_verify_detecta_filas_perdidas` — Una copia truncada se detecta por el número de filas.
- `test_verify_detecta_una_tabla_ausente` — Si falta una tabla, lo dice por su nombre.
- `test_verify_detecta_un_formato_distinto` — Un paquete de otro formato se rechaza aunque su contenido sea coherente.
- `test_verify_de_la_base_completa_o_de_un_archivo_que_no_es_paquete` — La base completa no tiene manifiesto: se informa en vez de lanzar una excepción.
- `test_is_bundle_distingue_el_paquete_de_la_base` — Solo el paquete tiene manifiesto; un archivo inexistente no lo es.
- `test_el_manifiesto_registra_commit_versiones_y_filas` — El manifiesto deja constancia de con qué se produjo el paquete.
- `test_el_contexto_viaja_dentro_del_paquete` — El contexto de OSM se guarda normalizado y data_access lo devuelve sin necesidad del directorio de JSON.
- `test_con_la_base_completa_y_sin_directorio_no_hay_contexto` — Con la base completa no hay tabla osm_context: el resultado es un DataFrame vacío con las columnas correctas.
- `test_el_directorio_tiene_prioridad_sobre_la_tabla_del_paquete` — Si se da --contexto, se usa ese directorio aunque el paquete traiga su propia tabla.
- `test_sin_contexto_la_tabla_va_vacia_pero_integra` — Exportar sin contexto da una tabla osm_context vacía y el paquete sigue siendo íntegro.
- `test_provenance_incluye_el_hash_del_archivo_y_los_datos_del_manifiesto` — La procedencia de un resultado dice qué paquete y qué versiones lo produjeron.
- `test_provenance_con_la_base_completa_no_tiene_datos_de_manifiesto` — Con la base completa no hay manifiesto; la procedencia lo omite en vez de fallar.
- `test_export_ml_inputs_crea_y_verifica` — La herramienta escribe el paquete, lo verifica y se niega a pisarlo sin --force.
- `test_export_ml_inputs_verify_falla_con_un_paquete_alterado` — --verify sale con 1 y nombra la tabla alterada.
- `test_export_ml_inputs_avisa_si_el_directorio_de_contexto_esta_vacio` — Un directorio de contexto sin JSON válidos no rompe la exportación, pero avisa.
- `test_export_ml_inputs_no_exporta_sobre_la_base` — Apuntar --out a la base de origen se rechaza sin tocarla.
- `test_validate_location_model_rechaza_un_paquete_alterado` — La herramienta de validación comprueba el paquete antes de entrenar y no sigue si no coincide.
- `test_measure_lens_variance_da_lo_mismo_con_el_paquete_que_con_la_base` — Los indicadores de las lentes salen idénticos desde la base y desde el paquete (sin contexto en ambos).
- `test_measure_lens_variance_usa_el_contexto_del_paquete` — Sin --contexto, el contexto que lleva el paquete se suma a los conteos y se informa.
- `test_requirements_fija_las_librerias_cientificas` — scikit-learn, scipy, statsmodels y matplotlib van con == (antes >=): una versión nueva puede cambiar resultados o no tener wheels para el Python de Docker y CI.
- `test_requirements_ml_fija_versiones_exactas` — requirements-ml.txt fija con == las librerías que cambian los números, y coinciden con las de requirements.txt cuando esta también las fija.

## `tests/test_ml_lenses.py`

> Tests de los perfiles de negocio, las tres lentes y las variables con control de fuga (src/ml/*)
> y de la herramienta tools/measure_lens_variance.py.

- `test_hay_un_perfil_por_cada_categoria_de_overpass` — Hay un perfil de negocio por cada categoría de Overpass.
- `test_cada_perfil_es_coherente` — Cada perfil (parametrizado) es coherente: tiene nombre y competencia directa, sus segmentos y proveedores existen y sus selectores usan categorías reales.
- `test_los_selectores_de_segmentos_y_proveedores_usan_categorias_reales` — Los selectores de segmentos y proveedores usan categorías que existen en Overpass o en el contexto de OSM.
- `test_residentes_usan_edificios_y_los_distribuidores_sanitarios_siguen_sin_proxy` — El segmento de residentes usa los edificios como proxy y los distribuidores sanitarios siguen sin proxy.
- `test_perfil_inexistente_lanza_error` — Pedir el perfil de una categoría que no existe lanza `ValueError`.
- `test_el_comercio_generico_no_cuenta_las_oficinas_como_competencia` — En el comercio genérico, las oficinas no cuentan como competencia pero sí las tiendas.
- `test_ajustar_no_modifica_el_perfil_por_defecto` — Ajustar un perfil devuelve uno nuevo marcado como personalizado y no modifica el perfil por defecto.
- `test_una_lente_no_puede_quedar_vacia_y_se_conserva_el_valor_por_defecto` — Una lente no puede quedar vacía: se conserva el valor por defecto y se avisa de cada una.
- `test_una_lente_que_ya_estaba_vacia_por_defecto_puede_seguir_vacia` — Una lente que ya estaba vacía por defecto puede seguir vacía sin avisos.
- `test_los_nombres_desconocidos_se_descartan_con_aviso` — Los nombres de segmento o proveedor desconocidos se descartan con un aviso.
- `test_quitar_mas_de_la_mitad_de_la_competencia_avisa_de_optimismo` — Quitar más de la mitad de la competencia del perfil por defecto avisa de que el resultado será optimista; quitar menos no.
- `test_anadir_competencia_no_cuenta_como_desviacion` — Añadir competencia al perfil no cuenta como desviación del perfil por defecto.
- `test_el_perfil_por_defecto_tiene_desviacion_cero_y_cambiarlo_todo_da_uno` — El perfil por defecto tiene desviación 0 y cambiar toda su competencia da 1.
- `test_el_umbral_de_aviso_es_la_mitad` — El umbral de desviación a partir del cual se avisa es 0,5.
- `test_la_competencia_se_pondera_por_vecindad` — La competencia directa se pondera por vecindad: 1 en la celda, 0,5 en la vecina y 0,25 en el segundo anillo.
- `test_solo_salen_las_celdas_activas_y_el_indice_es_cell_id` — Solo salen las celdas activas, con `cell_id` como índice; con una máscara completa salen las 2295.
- `test_segmento_sin_pois_es_nan_y_no_cero` — Un segmento sin proxy o sin POIs en los datos queda en NaN, no en 0, y uno con datos se calcula por vecindad.
- `test_cero_y_sin_datos_son_cosas_distintas` — Cero (hay datos y no hay nada cerca) y NaN (no se sabe) son cosas distintas en las lentes.
- `test_proveedores_total_y_diversidad` — Los proveedores se suman por tipo, con el total y la diversidad (cuántos de los tipos del perfil están presentes).
- `test_el_apoyo_cuenta_pois_sin_ponderar_en_la_celda_y_sus_8_vecinas` — El apoyo de competencia cuenta POIs sin ponderar en la celda y sus 8 vecinas.
- `test_un_poi_cuenta_en_una_sola_lente_la_competencia_manda` — Precedencia: un bar es competencia de un restaurante y NO también 'vida nocturna'; una panadería, aquí proveedor, tampoco es competencia.
- `test_los_museos_no_son_a_la_vez_competencia_y_turistas_en_ocio` — En ocio, un museo cuenta como competencia pero no como segmento de turistas.
- `test_lentes_con_datos_cuenta_cuantas_lentes_se_pueden_calcular` — `lentes_con_datos` cuenta cuántas lentes se pueden calcular en cada celda.
- `test_ajustar_el_perfil_cambia_la_lente_sin_tocar_los_datos` — Ajustar el perfil cambia el valor de la lente sin tocar los datos.
- `test_con_cero_pois_las_lentes_no_fallan` — Con cero POIs, las lentes devuelven una tabla vacía sin fallar.
- `test_cobertura_de_las_lentes` — La cobertura cuenta cuántos POIs alimentan cada lente y cada tipo del perfil.
- `test_las_variables_no_incluyen_el_objetivo_ni_en_la_celda_ni_en_la_vecindad` — Control de fuga: mover o añadir restaurantes NO cambia ninguna variable (si cambiara, el modelo de oferta esperada copiaría su propia etiqueta).
- `test_las_otras_categorias_si_entran_en_la_celda_y_en_los_anillos` — Las demás categorías cuentan en la celda y en los anillos de vecindad como variables del modelo.
- `test_nombres_y_numero_de_variables` — Las variables del modelo tienen los nombres esperados, 24 en total, y las de población y tiempo de viaje quedan en NaN sin datos de zona.
- `test_el_objetivo_cuenta_solo_la_propia_celda` — El objetivo cuenta solo los POIs de la propia celda.
- `test_distancia_al_centro_de_zona_mas_cercano` — La distancia al centro de la zona más cercana es corta para una celda que contiene un centro de zona.
- `test_poblacion_y_accesibilidad_suavizadas_con_las_zonas` — La población y el tiempo de viaje suavizados quedan dentro del rango de las zonas y más cerca de la zona cercana.
- `test_una_zona_sin_dato_se_omite_y_los_pesos_se_renormalizan` — Una zona sin dato se omite al suavizar y los pesos de las demás se renormalizan.
- `test_la_herramienta_lee_en_solo_lectura` — La herramienta lee los POIs de la base en solo lectura: no la modifica ni crea archivos.
- `test_describe_lens_excluye_nan_y_los_cuenta_aparte` — `describe_lens` excluye los NaN, los cuenta aparte y calcula media, desviación, coeficiente de variación y porcentaje de ceros.
- `test_la_serie_constante_no_da_cv_infinito` — Una serie constante en cero da un coeficiente de variación NaN, no infinito.
- `test_cuadrante_de_oportunidad` — La proporción de celdas de oportunidad (mercado alto y competencia baja) es 0,25 si son independientes y 0 si están correlacionadas.
- `test_la_herramienta_imprime_un_informe_por_perfil` — La herramienta imprime un informe por cada perfil con las celdas activas y la correlación de Spearman entre lentes.

## `tests/test_ml_panorama.py`

> Tests de la fase 2a: panorama por celda (src/ml/panorama.py) — lentes con percentiles y confianza, brecha exploratoria
> etiquetada, archivos de salida con manifiesto, reconstrucción de los conteos para recalcular con otro perfil y la
> herramienta tools/build_panorama.py.

- `test_from_frame_es_la_inversa_de_to_frame` — Reconstruir los conteos desde la tabla da las mismas matrices en las celdas de la tabla.
- `test_las_lentes_recalculadas_desde_la_tabla_son_identicas` — Con los conteos reconstruidos desde toda celda con algún conteo, cada perfil por defecto da exactamente las mismas lentes: el dashboard puede recalcular sin la base de datos.
- `test_cell_counts_incluye_el_contexto_de_celdas_inactivas` — Regresión: las celdas activas se definen solo con POIs de Overpass, pero un edificio en una celda inactiva vecina suma en las lentes de la activa. Si cell_counts.csv solo trajera las activas, recalcular daría otros números.
- `test_from_frame_conserva_la_subcategoria_vacia` — Una subcategoría vacía se guarda como 'categoria|' y vuelve como ''.
- `test_from_frame_con_tabla_vacia_no_falla` — Sin columnas no hay conteos, pero tampoco error.
- `test_percentile_rank_conserva_los_nan_y_es_monotono` — Sin datos sigue siendo NaN (no una posición baja) y el orden se respeta.
- `test_percentile_rank_empates_reciben_el_rango_medio` — Valores iguales tienen el mismo percentil.
- `test_confianza_una_lente_sin_datos_cuenta_cero` — Con apoyo de sobra pero una lente sin datos, la confianza máxima es 2/3 (nivel media-alta, nunca 1).
- `test_confianza_toda_la_informacion_da_uno_y_ninguna_da_cero` — Los extremos: apoyo suficiente en las tres lentes = 1; sin datos en ninguna = 0 (baja).
- `test_confianza_competencia_usa_los_pois_de_la_vecindad_no_los_competidores` — Una celda sin competidores pero rodeada de POIs tiene confianza ALTA en competencia: cero competidores es una observación creíble donde hay mucho mapeado. (Con el número de competidores saldría baja, y penalizaría justo las celdas de oportunidad.)
- `test_confianza_niveles_en_los_umbrales` — Los umbrales son 1/3 y 2/3, inclusivos hacia arriba.
- `test_locate_da_la_zona_mas_cercana_y_su_distancia` — El centro de la celda de una zona se asigna a esa zona, a menos de media celda de distancia.
- `test_panorama_sin_brecha_deja_la_brecha_vacia_y_no_validada` — Sin tabla de brecha, sus columnas son NaN, no hay modelo y brecha_validada es False.
- `test_panorama_incluye_las_lentes_sin_alterarlas` — Las columnas de lentes del panorama son exactamente las de compute_lenses.
- `test_panorama_percentiles_entre_cero_y_uno` — Cada percentil está en (0, 1] y la celda con más competencia tiene el máximo.
- `test_panorama_con_brecha_se_alinea_por_celda` — La brecha se une por cell_id: las celdas sin brecha quedan en NaN y las sobrantes se ignoran.
- `test_pois_vecindad_cuenta_solo_pois_de_overpass_no_el_contexto` — El apoyo general de la confianza son POIs de Overpass en la celda y sus 8 vecinas; los edificios del contexto de OSM no cuentan (no dicen cuán completo está el mapa de comercios).
- `test_la_brecha_no_modifica_ninguna_otra_columna` — Con o sin brecha, las lentes, percentiles y confianza son idénticos: la brecha no entra en nada más.
- `test_brecha_validada_se_propaga_solo_si_hay_brecha` — brecha_validada=True solo se refleja cuando se entrega una brecha; sin ella el panorama no afirma nada.
- `test_el_modulo_del_panorama_no_importa_scikit_learn` — El dashboard debe poder importar el panorama sin cargar scikit-learn (el contenedor tiene 1 GiB). scipy sí: la rejilla ya lo usa y está en requirements.txt.
- `test_gap_from_evaluation_calcula_esperado_brecha_y_percentiles` — Con predicciones conocidas: el esperado es la media entre repeticiones y la brecha, la relativa de la media.
- `test_gap_from_evaluation_una_repeticion_no_tiene_dispersion` — Con una sola repetición los percentiles coinciden con la brecha de esa repetición.
- `test_los_archivos_se_escriben_y_se_verifican` — Se escriben los tres archivos y la verificación no encuentra problemas.
- `test_el_panorama_leido_coincide_con_el_escrito` — La ida y vuelta por CSV conserva columnas, índice y valores (con la precisión escrita).
- `test_los_conteos_leidos_dan_las_mismas_lentes` — read_counts reconstruye los conteos: las lentes recalculadas coinciden con las de los conteos originales.
- `test_escribir_dos_veces_da_los_mismos_bytes` — La salida es determinista (sin fechas dentro de los CSV): el hash no cambia entre ejecuciones.
- `test_los_tres_archivos_se_escriben_con_saltos_de_linea_lf` — Los archivos salen iguales en Windows y Linux (sin CRLF), para que la tabla versionada no cambie según dónde se genere.
- `test_verify_detecta_un_csv_alterado` — Cambiar un valor del panorama se detecta por el hash y read_panorama se niega a leerlo.
- `test_verify_detecta_archivos_ausentes_y_manifiesto_roto` — Falta un CSV, falta el manifiesto, o el formato no es el esperado.
- `test_el_manifiesto_no_puede_omitir_un_archivo` — Un CSV que existe pero no figura en el manifiesto se reporta.
- `test_la_tabla_versionada_coincide_con_su_manifiesto` — data/ml/ (la tabla que llevará el dashboard) está íntegra: los hashes del manifiesto coinciden con los archivos y ningún saneamiento de saltos de línea los alteró (ver .gitattributes).
- `test_la_tabla_versionada_declara_la_brecha_como_lo_dice_la_validacion` — La brecha solo aparece en food_drink y business; brecha_validada coincide con la decisión del manifiesto (hoy ninguna) y las otras cinco categorías no afirman nada. Si algún día un candidato gana, habrá que regenerarla.
- `test_la_tabla_versionada_recalcula_las_mismas_lentes` — Con data/ml/cell_counts.csv, el panorama de cada perfil sale igual que el guardado: es lo que hará el dashboard.
- `test_build_panorama_sin_brecha_de_punta_a_punta` — La herramienta escribe los tres archivos con la procedencia del paquete y las siete categorías.
- `test_build_panorama_con_brecha_la_etiqueta_como_exploratoria` — Con brecha, solo food_drink y business la llevan; el manifiesto declara la decisión y la advertencia, y la columna brecha_validada solo es True si un candidato superó a la línea base.
- `test_build_panorama_rechaza_un_paquete_alterado` — Antes de calcular se verifica el paquete; si no coincide, no se escribe nada.

## `tests/test_ml_panorama_view.py`

> Tests de la fase 2b, parte sin interfaz (src/ml/panorama_view.py): opciones de competencia, perfil personalizado con sus
> avisos, panorama recalculado con ese perfil, brecha precalculada que no cambia con el perfil y filtro de oportunidad.

- `test_expand_selectors_separa_las_subcategorias_y_etiqueta_el_resto` — Cada subcategoría de un selector queda por separado; una categoría entera y un «todo salvo» tienen su etiqueta.
- `test_expandir_no_cambia_lo_que_se_cuenta` — La unión de los selectores expandidos cuenta lo mismo que los originales: dividir no altera el perfil.
- `test_available_pairs_omite_el_contexto_y_lo_vacio` — Edificios y transporte no son comercios: no se ofrecen como competencia. La subcategoría vacía se etiqueta.
- `test_competition_options_incluye_los_defectos_y_son_disjuntos` — Los valores por defecto de directa e indirecta están entre las opciones y no se solapan.
- `test_sin_cambios_devuelve_el_perfil_por_defecto_sin_avisos` — Si el usuario no toca nada, el perfil es el de por defecto (no personalizado) y no hay ningún aviso.
- `test_el_orden_de_la_seleccion_no_cuenta_como_cambio` — Elegir lo mismo en otro orden no hace personalizado el perfil.
- `test_cambiar_un_segmento_personaliza_el_perfil` — Quitar un segmento da un perfil personalizado con ese segmento menos, sin avisos si es razonable.
- `test_quitar_todos_los_segmentos_conserva_los_de_por_defecto_y_avisa` — Una lente que el perfil tiene no puede quedar vacía: se conserva y se avisa.
- `test_quitar_toda_la_competencia_directa_avisa` — Sin competencia directa se conserva la de por defecto, con aviso.
- `test_quitar_mas_de_la_mitad_de_la_competencia_avisa_del_optimismo` — Quitar la competencia indirecta (3 de 4 elementos) supera el umbral y avisa de que el panorama será más optimista.
- `test_anadir_competencia_no_avisa_de_optimismo` — Añadir competencia hace el panorama más conservador: personaliza el perfil pero sin aviso.
- `test_un_elemento_en_directa_e_indirecta_cuenta_solo_como_directa` — Si se elige en las dos, se avisa y solo cuenta una vez (en la directa).
- `test_same_profile_distingue_competencia_segmentos_y_proveedores` — Cualquiera de las tres definiciones distinta hace que los perfiles no sean el mismo.
- `test_gap_table_solo_existe_para_las_categorias_con_brecha` — food_drink y business tienen brecha (no validada); hospital no.
- `test_la_vista_por_defecto_coincide_con_la_tabla_guardada` — Recalcular el perfil por defecto desde los conteos da las lentes del panorama guardado.
- `test_un_perfil_distinto_cambia_las_lentes_pero_no_la_brecha` — Quitar la competencia indirecta baja la competencia directa+indirecta pero la brecha sigue siendo la precalculada.
- `test_un_segmento_menos_cambia_el_mercado` — Con solo «residentes» el índice de mercado es el de residentes escalado, distinto del combinado.
- `test_filtro_de_oportunidad_en_los_umbrales` — Mercado ≥ 0,75 y competencia ≤ 0,25 (inclusivos) y confianza no baja.
- `test_filtro_de_oportunidad_ignora_las_celdas_sin_datos` — Un NaN en un percentil nunca cuenta como oportunidad.
- `test_capas_disponibles_omiten_lo_que_no_tiene_datos` — La brecha solo es una capa si la categoría la tiene; una lente toda NaN no se ofrece.
- `test_layer_values_devuelve_la_columna_correcta` — Cada capa muestra su columna; la de brecha, la brecha relativa.
- `test_cell_label_incluye_celda_zona_y_distancia` — La etiqueta de la lista de celdas dice dónde está.
- `test_el_modulo_no_importa_scikit_learn` — La interfaz usa este módulo en el contenedor del dashboard, que no carga scikit-learn.

## `tests/test_ml_text_classifier.py`

> Tests de la fase 3: clasificador de texto del tipo de negocio (src/ml/text_classifier.py, src/ml/text_training.py y
> tools/evaluate_text_classifier.py) — inferencia con solo numpy que reproduce a scikit-learn, abstención, regla de
> decisión y que los datos de evaluación no se usan para entrenar ni para elegir el umbral.

- `test_los_ngramas_coinciden_con_los_de_scikit_learn` ×14 — Los n-gramas de caracteres son exactamente los del analizador `char_wb` de scikit-learn (incluidas las palabras más cortas que n, los espacios repetidos y la ñ).
- `test_normalizar_quita_tildes_y_enie_y_pasa_a_minusculas` — Sin tildes ni mayúsculas; la ñ pasa a n.
- `test_las_probabilidades_coinciden_con_scikit_learn_en_todas_las_frases` — Para todas las frases del proyecto, las probabilidades de la inferencia de solo numpy difieren de las de scikit-learn en menos de 1e-9.
- `test_las_probabilidades_suman_uno_y_un_texto_desconocido_no_falla` — Un texto sin ningún n-grama conocido da una distribución válida (solo el intercepto).
- `test_una_frase_clara_se_clasifica_y_devuelve_su_confianza` — «una farmacia» se clasifica como hospital con confianza alta.
- `test_texto_vacio_o_en_blanco_no_responde` — Sin texto no hay respuesta ni confianza.
- `test_gana_ninguna_y_no_responde` — Una frase que no describe un negocio no recibe categoría.
- `test_por_debajo_del_umbral_no_responde_y_el_umbral_se_puede_cambiar` — Con un umbral imposible no se responde; con uno nulo responde si la clase ganadora no es «ninguna».
- `test_guardar_y_cargar_da_el_mismo_modelo` — El JSON conserva todo: las probabilidades son idénticas y el archivo usa LF.
- `test_un_formato_o_unas_dimensiones_incoherentes_se_rechazan` — Un modelo de otro formato o con coeficientes que no cuadran con el vocabulario no se carga.
- `test_el_modulo_de_inferencia_no_importa_scikit_learn` — El dashboard debe poder cargar el modelo sin scikit-learn.
- `test_aciertos_equivocadas_y_perdidas_tienen_el_significado_documentado` — Una frase fuera de alcance se acierta no respondiendo; responderle es una respuesta equivocada; no responder a un negocio es una pérdida, no un error.
- `test_el_hibrido_prefiere_las_palabras_clave_y_usa_el_modelo_solo_si_se_abstienen` — Donde las palabras clave responden, manda su respuesta aunque el modelo diga otra cosa.
- `test_respuesta_aplica_la_abstencion` — Gana «ninguna» o no llega al umbral: None.
- `test_elegir_umbral_toma_el_mas_bajo_que_no_pasa_de_las_equivocadas_de_las_palabras_mas_la_tolerancia` — El umbral es el más bajo cuyo híbrido no comete más respuestas equivocadas que las palabras clave (+2 puntos). Aquí las palabras no responden nunca (0 equivocadas): a 0,6 o menos el clasificador contesta «hospital» a dos frases fuera de alcance (2 de 3 equivocadas); a 0,65 se abstiene y deja de equivocarse.
- `test_elegir_umbral_la_tolerancia_incluye_el_borde_y_se_pasa_a_la_siguiente_rejilla` — Con 98 frases de hospital bien respondidas y 2 fuera de alcance respondidas mal (2 %), el borde de la tolerancia (palabras 0 % + 2 puntos) se cumple y sale el umbral más bajo; con 3 mal (3 %) ya no y hay que subirlo.
- `test_elegir_umbral_si_ninguno_cumple_toma_el_mas_alto` — Una frase fuera de alcance a la que el clasificador responde con 0,99 se contesta mal con cualquier umbral: sin umbral válido se elige el más alto (el más prudente), no el más bajo.
- `test_elegir_umbral_mide_el_hibrido_no_el_clasificador_solo` — Si las palabras clave ya responden bien una frase, lo que el clasificador diría de ella no cuenta: el híbrido solo lo consulta cuando las palabras se abstienen. Aquí el clasificador solo se equivocaría siempre, el híbrido nunca.
- `test_bootstrap_pareado_con_diferencia_constante_y_con_diferencia_nula` — Si a acierta siempre y b nunca, el IC es [1, 1]; si son iguales, la diferencia es 0.
- `test_la_regla_adopta_solo_si_mejora_y_no_sube_los_errores` — Las tres salidas posibles de la regla fijada: adoptar, fallar por exactitud y fallar por errores.
- `test_la_tolerancia_de_errores_es_de_dos_puntos` — Justo en la tolerancia (+2 puntos) todavía cumple; por encima, no.
- `test_por_tipo_agrupa_las_metricas` — Una fila por tipo con su número de frases y sus tasas.
- `test_los_datos_versionados_son_validos_y_el_conjunto_de_evaluacion_es_el_prometido` — Sin categorías raras, sin repetidas, sin frases en ambos conjuntos; ≥200 frases de evaluación con los cinco tipos del diseño y las siete categorías más las fuera de alcance.
- `test_validar_datos_detecta_cada_problema` — Categoría desconocida, frases repetidas o vacías, y fuga de evaluación a entrenamiento.
- `test_la_decision_es_la_regla_aplicada_a_las_cifras` — `adoptar` es la conjunción de las dos condiciones y las cifras del resumen son las de los sistemas.
- `test_el_hibrido_nunca_cambia_una_respuesta_de_las_palabras_clave` — Donde las palabras clave responden, el híbrido da lo mismo.
- `test_el_umbral_no_depende_de_la_evaluacion` — El umbral sale solo del entrenamiento: si se barajan las etiquetas de la evaluación no cambia.
- `test_ninguna_frase_de_evaluacion_entra_en_el_entrenamiento` — El vocabulario del modelo sale solo del entrenamiento: añadir una frase con n-gramas inéditos a la evaluación no lo cambia.
- `test_la_evaluacion_es_determinista` — Mismos datos y semilla, mismas cifras.
- `test_la_sensibilidad_recorre_los_umbrales_y_a_mayor_umbral_menos_respuestas` — A mayor umbral el híbrido responde menos (más «sin respuesta»); la tabla es descriptiva.
- `test_main_imprime_la_decision_y_exporta_modelo_y_manifiesto` — La herramienta termina bien, imprime la decisión, y con --exportar escribe un modelo cuyo hash está en el manifiesto y que se carga y clasifica.
- `test_main_se_niega_a_evaluar_con_datos_invalidos` — Si una frase de evaluación está también en el entrenamiento, no se evalúa.
- `test_sin_mlp_se_omiten_la_red_y_su_comparacion` — Con con_mlp=False no hay sistema MLP, ni su umbral, ni la comparación logística-MLP; el resto se calcula igual.
- `test_con_mlp_se_comparan_la_red_y_la_logistica` — Con la red incluida hay umbral propio, sistema híbrido con la red y la comparación pareada.
- `test_la_regla_exige_que_el_intervalo_quede_por_encima_de_cero_no_solo_la_media` — Una mejora pequeña (2 aciertos más de 40) tiene media positiva pero un IC que llega a 0: no cumple la exactitud.
- `test_el_bootstrap_da_un_intervalo_con_anchura_que_contiene_la_media` — Con diferencias variables el IC tiene anchura positiva y rodea a la media.
- `test_el_softmax_es_estable_con_logits_enormes` — Con coeficientes gigantes no hay desbordamiento: las probabilidades siguen siendo válidas.
- `test_la_evaluacion_v2_cumple_las_cuotas_fijadas_y_no_solapa_con_el_entrenamiento` — El conjunto escrito por Codex tiene la composición fijada en el protocolo (§3.L2): 200 frases con las cuotas por tipo y por categoría, sin repetidas ni coincidencias con el entrenamiento, y con la etiqueta ciega de cada una.
- `test_solo_coincidentes_deja_las_frases_donde_autor_y_etiquetador_ciego_coinciden` — Las ambiguas (etiqueta distinta) se quitan de la evaluación principal; no se tocan ni se reetiquetan las demás.
- `test_validar_datos_rechaza_una_etiqueta_ciega_desconocida` — Una etiqueta del etiquetador que no es una categoría (p. ej. una errata suya) invalida la evaluación.
- `test_main_con_solo_coincidentes_evalua_las_192_y_el_manifiesto_dice_quien_escribio_las_frases` — Con --solo-coincidentes se evalúan solo las frases con la misma etiqueta del autor y del etiquetador ciego, se informa de cuántas se dejan fuera, y la advertencia del manifiesto ya no dice «mismo autor».
- `test_main_solo_coincidentes_sin_columna_ciego_se_niega` — El archivo de evaluación antiguo no tiene la columna `ciego`: la opción lo dice en vez de fallar a medias.
- `test_ambiguas_es_el_complemento_de_solo_coincidentes` — Cada frase está en exactamente uno de los dos conjuntos: las coincidentes se evalúan y las ambiguas se informan.

## `tests/test_ml_validation.py`

> Tests de la fase 1 del ML de recomendación: lectura de datos en solo lectura (src/ml/data_access.py), modelos de
> oferta esperada (src/ml/models.py), validación espacial (src/ml/validation.py) y tools/validate_location_model.py.

- `test_la_lectura_es_de_solo_lectura` — Leer POIs, POIs de Foursquare y la tabla de zonas no modifica la base de datos ni crea archivos.
- `test_foursquare_es_opcional` — Sin tabla de Foursquare, la carga devuelve una tabla vacía con sus columnas.
- `test_tabla_de_zonas_con_poblacion_y_tiempo_de_viaje` — La tabla de zonas trae la población y el tiempo de viaje medio de las rutas que tocan cada zona; las zonas sin dato quedan en NaN.
- `test_la_densidad_suma_las_categorias_en_log` — La densidad suma todas las categorías de la celda y de los anillos y aplica el logaritmo.
- `test_cada_modelo_usa_solo_sus_variables` — Cada modelo de referencia usa solo sus variables: cambiar la población no altera `solo_distancia` ni `solo_densidad`, pero sí `solo_poblacion`.
- `test_las_predicciones_son_positivas_y_tienen_una_por_fila` — Cada modelo (parametrizado) da una predicción finita y positiva por cada fila de prueba.
- `test_una_linea_base_sin_su_unica_variable_degrada_a_la_media` — Regresión: sin demografía cargada la población llega toda NaN, se descarta y solo_poblacion fallaba con KeyError.
- `test_la_media_es_el_promedio_de_entrenamiento` — El modelo `media` predice el promedio del objetivo de entrenamiento.
- `test_fit_predict_es_determinista_con_la_misma_semilla` — `fit_predict` da las mismas predicciones con la misma semilla.
- `test_modelo_desconocido_lanza_error` — Un nombre de modelo desconocido lanza `ValueError`.
- `test_el_boosting_aprende_la_senal_y_gana_a_la_media` — Sobre datos sintéticos con señal, el boosting aprende y baja la desviación de Poisson al menos un 10 % respecto a la media.
- `test_una_variable_toda_nan_no_rompe_el_ajuste` ×3 — Regresión: sin datos de rutas la accesibilidad llega toda NaN y el boosting fallaba al discretizarla (ValueError: window shape cannot be larger than input array shape).
- `test_el_conjunto_da_media_y_dispersion` — El conjunto de modelos da media, desviación y percentiles 10 y 90; con un solo modelo la desviación es 0.
- `test_las_celdas_de_un_bloque_comparten_etiqueta_y_el_desplazamiento_la_cambia` — Las celdas de un mismo bloque comparten etiqueta y desplazar los bloques cambia la etiqueta.
- `test_los_pliegues_no_parten_un_bloque_y_estan_equilibrados` — Los pliegues no parten ningún bloque, están equilibrados y son reproducibles con la misma semilla.
- `test_la_desviacion_de_poisson_coincide_con_scikit_learn_y_los_casos_limite` — La desviación de Poisson coincide con la de scikit-learn y maneja los casos límite (cero observado, predicción cero).
- `test_precision_en_las_k_primeras_y_spearman` — La precisión en las k primeras y la correlación de Spearman dan los valores esperados, incluidos k mayor que n y una serie constante.
- `test_evaluate_devuelve_predicciones_fuera_de_muestra_para_todas_las_celdas` — `evaluate` devuelve predicciones fuera de muestra para todas las celdas y repeticiones, y el resumen ordena los modelos por desviación.
- `test_la_prediccion_de_una_celda_no_usa_su_propio_valor` — Fuera de muestra de verdad: cambiar el valor real de una celda no cambia su propia predicción.
- `test_el_bootstrap_de_bloques_con_predicciones_identicas_da_cero` — El bootstrap de bloques con predicciones idénticas da diferencia e intervalo en cero.
- `test_el_bootstrap_detecta_una_mejora_uniforme_y_es_prudente_si_solo_hay_un_bloque_mejor` — El bootstrap detecta una mejora uniforme y es prudente (el intervalo incluye 0) si la mejora está solo en un bloque; es reproducible con la misma semilla.
- `test_decide_publica_solo_si_el_intervalo_queda_por_debajo_de_cero` — `decide` declara ganador solo si el intervalo de la diferencia queda por debajo de cero frente al mejor modelo de referencia.
- `test_decide_sin_mejora_clara_no_hay_ganador_y_marca_al_que_empeora` — Sin mejora clara no hay ganador, y se marca como «peor» al modelo que empeora.
- `test_decide_no_depende_de_cuantas_repeticiones_se_promedien` — Regresión: antes se promediaban las predicciones entre repeticiones y DESPUÉS se calculaba la desviación. Un candidato muy inestable (cada repetición falla mucho, pero en promedio acierta) salía como 'mejora' solo por ser un conjunto de modelos, y el veredicto cambiaba con el número de repeticiones.
- `test_la_brecha_relativa_no_premia_solo_a_las_celdas_grandes` — La brecha relativa no premia solo a las celdas grandes, a diferencia de la brecha absoluta, y es 0 si lo esperado es igual a lo observado.
- `test_auc_y_artefacto_de_cartografia` — El AUC de presencia da 1 con una puntuación perfecta y NaN si todo es positivo; la proporción de brecha explicada por la cartografía se calcula frente a su referencia.
- `test_conteos_de_foursquare_por_celda` — Los conteos de Foursquare por celda cuentan solo las categorías pedidas e ignoran los puntos fuera de la rejilla.
- `test_zona_mas_cercana` — La zona más cercana a la celda de Valletta es Valletta.
- `test_la_herramienta_valida_un_objetivo_de_punta_a_punta` — La herramienta valida un objetivo de punta a punta: imprime la decisión y el contraste con Foursquare, y no modifica la base de datos.
- `test_run_target_devuelve_todo_lo_necesario` — `run_target` devuelve esperado, observado, brecha, variables, resumen y decisión, con la brecha igual a esperado menos observado.
- `test_la_herramienta_sin_foursquare_no_hace_el_contraste` — Sin datos de Foursquare, la herramienta avisa y no hace el contraste.

## `tests/test_normalize_bronze_timestamps.py`

> Pruebas de tools/normalize_bronze_timestamps.py.
>
> Todo ocurre sobre bases temporales: ninguna prueba toca data/mobility.db.

- `test_is_legacy_y_normalize` — `is_legacy` reconoce el formato antiguo de timestamp, `normalize` lo pasa a ISO y normalizar dos veces da lo mismo.
- `test_plan_clasifica_cada_fila` — El plan clasifica cada fila: gemelas de otra fila ISO, duplicadas entre antiguas, a renombrar y las que no se tocan.
- `test_misma_hora_en_otra_ruta_no_es_gemela` — Una fila con la misma hora pero en otra ruta no es gemela y solo se renombra.
- `test_base_sin_filas_antiguas_no_necesita_cambios` — Una base sin filas en formato antiguo no necesita cambios.
- `test_el_ensayo_no_modifica_nada_ni_crea_archivos` — El ensayo (sin `--apply`) no modifica la base ni crea archivos, y lo dice en su salida.
- `test_main_con_base_inexistente_o_sin_tabla` — Con una base inexistente devuelve código 2; con una base sin tabla indica que no hay nada que normalizar.
- `test_aplicar_borra_duplicados_renombra_el_resto_y_deja_un_respaldo` — `--apply` borra las gemelas y duplicadas, renombra el resto al formato ISO y deja un respaldo de la base.
- `test_aplicar_es_idempotente` — Aplicar dos veces da el mismo resultado, la segunda dice que no hay nada que hacer y no crea otro respaldo.
- `test_antes_de_correr_el_pipeline_solo_renombra` — Caso de la base real hoy: filas antiguas sin gemela ISO todavía.
- `test_despues_de_normalizar_reingerir_la_misma_medicion_no_duplica` — El objetivo del script: que correr el pipeline no reinserte las filas antiguas.
- `test_el_indice_unico_sigue_vigente` — Tras normalizar, el índice único de Bronze sigue vigente y rechaza una fila igual a una ya normalizada.
- `test_no_toca_otras_tablas` — La normalización no modifica otras tablas, como `route_measurements`.
- `test_si_la_base_esta_en_uso_aborta_sin_cambiar_nada` — Otro proceso (el collector) con una escritura abierta: no se aplica nada.
- `test_si_la_verificacion_falla_se_revierte_todo` — Si la verificación final falla, se revierte todo y la base queda como estaba.
- `test_el_respaldo_se_puede_omitir_solo_por_codigo` — La línea de comandos siempre respalda; `backup=False` existe solo para pruebas.

## `tests/test_operations_dashboard.py`

> Pantalla Operations (AppTest): se abre con datos y un error en una sección no tumba las demás.

- `test_operations_abre_con_datos_y_muestra_sus_cuatro_secciones` — Operations se abre sin excepciones con datos, y muestra las cuatro secciones y el aviso final.
- `test_operations_la_tabla_de_alertas_marca_la_ruta_lenta` — Con una ruta de más de 30 min de media en la última hora, las alertas la listan.
- `test_operations_un_error_en_una_seccion_se_muestra_en_ella_y_no_tumba_la_pagina` — Cada sección (parametrizado) se aísla: se dice cuál falló y por qué, y la página sigue hasta el aviso final.
- `test_operations_las_demas_secciones_siguen_mostrandose_cuando_una_falla` — Con las alertas rotas, la tabla de estado y el resumen de 24 h (que vienen después) se siguen viendo.
- `test_operations_una_seccion_que_falla_a_mitad_no_deja_lo_que_ya_habia_dibujado` — Si una sección dibuja un título y luego falla, ese título a medias se retira: solo queda el aviso.
- `test_operations_el_fallo_de_una_seccion_queda_en_el_registro` — El mensaje en pantalla es corto; el traceback completo va al registro de la aplicación.
- `test_operations_st_stop_dentro_de_una_seccion_no_se_trata_como_un_error` — Solo se captura Exception: `st.stop()` usa una excepción de control y debe seguir deteniendo el script. Si se capturara, se registraría como un fallo de la sección que no lo es, así que se comprueba el registro.

## `tests/test_operations_status.py`

> Pruebas del estado por ruta del dashboard Operations.
>
> Regresión: el estado salía de `traffic_delay_min` de la última fila, y `_safe()`
> convertía el NULL en 0. ORS no reporta tráfico (el 100% de sus filas lo trae
> NULL), así que cualquier ruta cuya última medición fuera de ORS aparecía como
> "🟢 Free Flow" sin ningún dato detrás.

- `test_ultima_medicion_de_cada_ruta_en_una_consulta` — `get_latest_per_route` devuelve la medición más reciente de cada ruta en una sola consulta.
- `test_no_trae_la_polilinea` — `get_latest_per_route` no trae la polilínea ni columnas auxiliares.
- `test_require_column_trae_la_ultima_fila_que_tiene_ese_dato` — Con `require_column`, trae la última fila que sí tiene ese dato, aunque haya otra más reciente sin él.
- `test_require_column_omite_las_rutas_que_nunca_tuvieron_ese_dato` — Con `require_column`, se omiten las rutas que nunca tuvieron ese dato.
- `test_require_column_rechaza_columnas_inexistentes` — `require_column` rechaza con `ValueError` una columna que no existe o con inyección SQL.
- `test_base_vacia` — Con una base vacía, `get_latest_per_route` devuelve una tabla vacía.
- `test_ruta_cuya_ultima_medicion_es_de_ors_usa_la_lectura_de_tomtom` — Si la última medición de una ruta es de ORS, el estado y el retraso salen de la última lectura de TomTom, no de un 0 inventado.
- `test_ruta_sin_ninguna_lectura_de_trafico_nunca_se_pinta_de_verde` — El bug: la última fila es de ORS (delay NULL) -> antes '🟢 Free Flow'.
- `test_lectura_de_trafico_desactualizada_se_avisa` — Si la última lectura de tráfico es demasiado antigua, el estado indica «Lectura desactualizada».
- `test_umbrales_de_estado` ×6 — El estado de la ruta (libre, moderado o denso) sigue los umbrales de retraso (parametrizado).
- `test_una_fila_por_ruta_con_las_columnas_esperadas` — La tabla de estado tiene una fila por ruta y las columnas esperadas.

## `tests/test_ors_null_fields.py`

> Pruebas de regresión: campos que vienen NULL con DATA_SOURCE=ors
> (traffic_delay_min, no_traffic_time_min) no deben romper comparaciones ni
> formateo en ningún dashboard.
>
> Ver INTEGRATION_NOTES.md, bug #12: con ORS (la fuente por defecto),
> traffic_delay_min/no_traffic_time_min/traffic_length_km vienen NULL, y
> dict.get(key, default) / pd.Series.get(key, default) NO usan `default`
> cuando la clave existe pero su valor es None — solo cuando la clave falta.
> Varios puntos de streamlit_app/dashboards/operations_dashboard.py y
> streamlit_app/legacy_reference/ asumían lo contrario y crasheaban con
> `TypeError: '<=' not supported between instances of 'NoneType' and 'int'`.

- `test_ors_row_traffic_delay_is_none_not_nan` — Confirma la forma exacta del bug: con una sola fila ORS, .get() devuelve None (no NaN), que rompe comparaciones directas sin guardar.
- `test_safe_helper_handles_none_and_nan` — El helper _safe() (duplicado en operations_dashboard.py y legacy_reference/components.py) debe neutralizar tanto None como NaN.

## `tests/test_poi_extraction.py`

> Pruebas de los dos recolectores de POIs (`src/poi_extraction.py`, Overpass, y
> `src/poi_extraction_foursquare.py`, Foursquare).
>
> No hacen llamadas de red: el cliente es un doble y la base de datos es un SQLite
> temporal. Los archivos que los módulos escriben en `logs/` (heartbeat, contador de
> llamadas) se redirigen a `tmp_path`.

- `test_overpass_run_once_guarda_los_pois_y_escribe_el_heartbeat` — `run_once` de Overpass guarda los POIs en la base y escribe el heartbeat.
- `test_overpass_run_once_pasa_el_margen_al_cliente` — `run_once` de Overpass pasa el margen indicado al cliente.
- `test_overpass_un_segundo_ciclo_actualiza_en_vez_de_duplicar` — Un segundo ciclo de Overpass actualiza los POIs existentes en vez de duplicarlos.
- `test_overpass_si_la_descarga_falla_devuelve_0_y_no_toca_nada` — Si la descarga de Overpass falla, `run_once` devuelve 0, no guarda nada y no escribe el heartbeat.
- `test_overpass_heartbeat_contiene_una_fecha_iso_utc` — El heartbeat de Overpass contiene una fecha ISO en UTC reciente.
- `test_overpass_heartbeat_no_rompe_si_no_puede_escribir` — El heartbeat de Overpass no rompe el ciclo si no puede escribirse; deja un aviso en el log.
- `test_overpass_main_sin_intervalo_hace_un_ciclo_y_cierra_el_cliente` — `main` de Overpass sin intervalo hace un único ciclo con el margen indicado y cierra el cliente.
- `test_overpass_main_con_intervalo_repite_y_ctrl_c_sale_con_0` — `main` de Overpass con intervalo repite los ciclos esperando el intervalo en horas, y Ctrl+C sale con código 0.
- `test_overpass_main_un_error_fatal_sale_con_1_y_cierra_el_cliente` — Un error fatal en `main` de Overpass sale con código 1 y cierra el cliente.
- `test_contador_nuevo_empieza_en_las_llamadas_dadas_y_guarda_el_mes` — El contador mensual nuevo empieza con las llamadas dadas y guarda el mes en curso.
- `test_contador_acumula_dentro_del_mismo_mes` — El contador mensual acumula las llamadas dentro del mismo mes.
- `test_contador_se_reinicia_al_cambiar_de_mes` — El contador mensual se reinicia al cambiar de mes.
- `test_contador_corrupto_se_reinicia_sin_fallar` — Un contador corrupto se reinicia sin fallar.
- `test_contador_no_rompe_si_no_puede_guardar` — El contador devuelve la cuenta aunque no pueda guardarla y deja un aviso en el log.
- `test_foursquare_run_once_guarda_los_pois_cuenta_las_llamadas_y_escribe_el_heartbeat` — `run_once` de Foursquare guarda los POIs, suma las llamadas del ciclo al contador y escribe el heartbeat.
- `test_foursquare_run_once_pide_zonas_y_rutas_al_cliente` — `run_once` de Foursquare pide al cliente las zonas y las rutas.
- `test_foursquare_avisa_al_superar_el_limite_mensual` — Foursquare avisa al superar el límite mensual del tier gratis.
- `test_foursquare_no_avisa_si_queda_margen` — Foursquare no avisa si queda margen sobre el límite mensual.
- `test_foursquare_heartbeat_no_rompe_si_no_puede_escribir` — El heartbeat de Foursquare no rompe el ciclo si no puede escribirse; deja un aviso en el log.
- `test_foursquare_main_sin_clave_sale_con_1_sin_crear_el_cliente` — Sin `FOURSQUARE_API_KEY`, `main` de Foursquare sale con código 1 sin crear el cliente.
- `test_foursquare_main_con_clave_hace_un_ciclo_y_cierra_el_cliente` — Con clave, `main` de Foursquare hace un único ciclo y cierra el cliente.
- `test_foursquare_main_con_intervalo_repite_y_ctrl_c_sale_con_0` — `main` de Foursquare con intervalo repite los ciclos esperando el intervalo en horas, y Ctrl+C sale con código 0.
- `test_foursquare_main_un_error_fatal_sale_con_1_y_cierra_el_cliente` — Un error fatal en `main` de Foursquare sale con código 1 y cierra el cliente.

## `tests/test_predictive_modeling_dashboard.py`

> Pruebas de la preparación de datos del dashboard de modelado predictivo.
>
> Regresión: con datos reales, unas pocas filas (OpenWeather falló en ese ciclo)
> tienen el clima en NULL, y una sola basta para que `LogisticRegression` lance
> `Input X contains NaN`. Esa excepción cortaba toda la vista Analyst.

- `test_clima_ausente_no_se_convierte_en_lluvia` — Una fila sin clima queda como NaN en el grupo de clima, no como «lluvia».
- `test_descripciones_conocidas_y_desconocidas_se_agrupan_como_antes` — Las descripciones de clima conocidas y las desconocidas se agrupan igual que antes del cambio.
- `test_complete_cases_excluye_solo_las_filas_sin_clima` — `_complete_cases` descarta solo las filas sin clima y no modifica el DataFrame original.
- `test_sin_filas_incompletas_no_se_pierde_nada` — Si no hay filas incompletas, `_complete_cases` conserva todas.
- `test_regresion_no_falla_con_filas_sin_clima` — La regresión se ajusta sin fallar aunque haya filas sin clima.
- `test_clasificacion_no_falla_con_filas_sin_clima` — El caso exacto del bug: 'Input X contains NaN' en LogisticRegression.
- `test_el_temporal_y_el_clustering_conservan_las_filas_sin_clima` — Su tiempo de viaje es válido: no deben pasar por _complete_cases.
- `test_la_particion_cronologica_entrena_con_lo_antiguo_y_evalua_con_lo_reciente` — El 80 % más antiguo entrena y el 20 % más reciente evalúa, aunque las filas lleguen desordenadas.
- `test_un_mismo_ciclo_no_se_reparte_entre_entrenamiento_y_prueba` — Las rutas de un ciclo comparten marca de tiempo: caen todas del mismo lado del corte, no una en cada.
- `test_la_regresion_se_evalua_con_las_filas_mas_recientes` — El conjunto de prueba de la regresión son exactamente las filas más recientes (con clima), no una muestra al azar.
- `test_la_clasificacion_se_evalua_con_las_filas_mas_recientes` — Igual en la clasificación: el tramo de prueba es el final de la serie.
- `test_la_validacion_cruzada_de_la_clasificacion_respeta_el_orden_temporal` — La elección de `max_features` valida con `TimeSeriesSplit` (cada pliegue prueba con filas posteriores a las que entrena, por orden de filas), no con pliegues barajados: si no, el AUC de validación cruzada vuelve a ser optimista. Corta por filas, no por fecha: un ciclo puede quedar a caballo entre dos tramos de un pliegue (como mucho uno).
- `test_el_orden_de_llegada_de_las_filas_no_cambia_la_particion` — La base entrega las filas de la más reciente a la más antigua: el resultado no debe depender de ello.

## `tests/test_predictive_modeling_ondemand.py`

> Pruebas del modelado predictivo BAJO DEMANDA del dashboard.
>
> Regresión: Streamlit ejecuta el contenido de TODAS las pestañas en cada rerun, así que los
> cuatro modelos se entrenaban de golpe al abrir Analyst (con la base real: ~75 s con 16 CPUs y
> ~9 min dentro del contenedor del dashboard, de 1 CPU y 1 GiB, donde además rozaba el límite de
> memoria). Ahora se entrena solo lo que el usuario pide.

- `test_las_secciones_coinciden_con_los_modelos` — Las secciones de la pantalla coinciden con los modelos que se pueden entrenar.
- `test_al_abrir_no_se_entrena_nada` — Al abrir la pantalla no se entrena ningún modelo; solo se muestran los botones y las métricas baratas de resumen.
- `test_pulsar_un_boton_entrena_solo_esa_seccion` — Pulsar el botón de una sección entrena solo esa y el botón se reemplaza por su resultado.
- `test_lo_pedido_se_mantiene_en_la_sesion` — Lo ya pedido se conserva entre reejecuciones de la página, sin pedir de nuevo otras secciones.
- `test_el_boton_de_todos_entrena_las_cuatro_secciones` — El botón de «todos» entrena las cuatro secciones.
- `test_el_forecast_temporal_funciona_con_low_memory` — El SARIMA usa fit(low_memory=True): se comprueba que el pronóstico y su intervalo se pueden obtener (sin resultados suavizados ni predicción en muestra, que low_memory no ofrece), y que la pantalla muestra la referencia y la nota de validación.

## `tests/test_query_measurements_polyline.py`

> Pruebas de `include_polyline` en RouteDatabase.query_measurements.
>
> Regresión: query_measurements hacía `SELECT *` e incluía `polyline` (el JSON de la
> geometría de la ruta, ~4,5 KB por fila). En la base real eso es el 93% del tamaño en
> memoria de la tabla (339 de 365 MB con 78.561 filas) y, repetido por cada pestaña y por
> la caché de Streamlit, agotaba el límite de 1 GiB del contenedor del dashboard al abrir
> Analyst (el proceso moría por falta de memoria).

- `test_por_defecto_no_carga_la_polilinea` — Por defecto `query_measurements` no carga la columna `polyline`.
- `test_include_polyline_la_devuelve_intacta` — Con `include_polyline=True` la polilínea vuelve idéntica a la guardada.
- `test_las_demas_columnas_son_exactamente_las_mismas` — Sin polyline tampoco se lee created_at (va después de polyline y leerla recorre las páginas de desbordamiento de todas las filas); el resto de columnas no cambia.
- `test_por_defecto_tampoco_lee_created_at_pero_con_include_polyline_si` — `created_at` solo se lee con `include_polyline=True`.
- `test_los_filtros_y_el_orden_no_cambian` — Los filtros por origen, destino y fecha y el orden (más reciente primero) siguen igual que antes.
- `test_sin_la_polilinea_la_memoria_baja_mucho` — No es una cifra mágica: con polilíneas de ~12 KB, cargarlas pesa >10× lo que pesa el resto.
- `test_base_vacia_no_falla` — Con una base vacía `query_measurements` devuelve un DataFrame vacío sin fallar.
- `test_export_route_data_conserva_la_polilinea` — La exportación por ruta no cambia: sigue incluyendo la geometría.

## `tests/test_recommendation_dashboard.py`

> Pruebas de la tabla de resultados del dashboard de Recomendación.
>
> El README promete que el desglose muestra cada dimensión CRUDA y NORMALIZADA
> ("nunca solo el número final"). Esto lo verifica sin abrir Streamlit.

- `test_la_tabla_muestra_cada_factor_crudo_y_normalizado` — La tabla de resultados trae, por cada factor, el valor crudo y el normalizado, y una fila por zona.
- `test_las_columnas_normalizadas_estan_entre_0_y_1` — Las columnas normalizadas (demanda, baja competencia, accesibilidad) quedan entre 0 y 1.
- `test_mas_alto_siempre_es_mejor_en_las_tres_columnas` — La zona con más competencia tiene el menor 'Baja competencia'.
- `test_el_puntaje_es_la_suma_ponderada_de_las_columnas_mostradas` — Lo que dice el pie de la tabla: Puntaje = suma ponderada de las tres columnas (0-1), con 0.5 donde falta el dato.
- `test_una_zona_sin_dato_queda_en_blanco_y_se_nota` — Una zona sin dato queda en blanco (NaN) en vez de en 0 y su recuento de datos completos baja de 3.
- `test_normalize_weights_conserva_proporciones_y_suma_uno` — Los pesos normalizados conservan las proporciones y suman 1; con todo en cero se usan los pesos por defecto sin dividir entre cero.

## `tests/test_recommendation_interpretacion_ui.py`

> Tests de pantalla (Streamlit AppTest) de cómo Recomendación interpreta el texto: palabras clave primero, el modelo
> entrenado solo donde ellas no reconocen el negocio (con su lectura marcada como decidida por el modelo) y la posibilidad de
> corregir la categoría (docs/DISENO_ML_RECOMENDACION.md §3.L2).

- `test_una_palabra_clave_se_interpreta_sin_aviso_del_modelo_y_se_puede_corregir` — Con una palabra clave se muestra la interpretación de siempre, sin aviso, y el selector de categoría está disponible pero plegado.
- `test_un_texto_que_solo_entiende_el_modelo_se_marca_como_decidido_por_el_modelo` — Si las palabras clave no reconocen el negocio y responde el modelo, la pantalla lo dice, da su confianza y deja el selector abierto para revisarlo.
- `test_corregir_la_categoria_es_la_que_llega_al_puntaje` — La categoría que elige el usuario sustituye a la interpretada: es la que se usa para calcular el puntaje, y la pantalla dice que se usa la elegida.
- `test_la_correccion_no_se_arrastra_a_la_siguiente_busqueda` — Una corrección vale para esa búsqueda: con otro texto, la categoría vuelve a ser la interpretada.
- `test_un_texto_que_nadie_entiende_da_el_error_de_siempre` — Si ni las palabras clave ni el modelo responden, se muestra el mensaje de siempre y no se calcula nada.
- `test_sin_modelo_la_pantalla_funciona_como_antes` — Si el artefacto falta o no se verifica (`get_text_model` devuelve None), solo responden las palabras clave: una errata que antes no se entendía sigue sin entenderse y no hay aviso del modelo.
- `test_con_el_modelo_real_una_errata_se_entiende_y_se_marca` — Con el artefacto versionado en data/ml/: «una pizeria» (errata) la entiende el modelo como restauración, con aviso de que lo decidió el modelo, y se calcula el puntaje de esa categoría.

## `tests/test_recommendation_panorama_ui.py`

> Tests de pantalla de la fase 2b (Streamlit AppTest): el panorama por celda dentro de Recomendación, con la tabla
> versionada en data/ml/. Comprueban lo que promete el diseño: lentes por separado sin puntaje combinado, el perfil usado
> siempre indicado, los controles que recalculan, la brecha etiquetada como exploratoria y que no cambia con el perfil.

- `test_la_seccion_abre_para_cada_categoria` — Las siete categorías muestran el mapa, la lista de celdas y los cuatro controles de perfil.
- `test_declara_que_no_hay_puntaje_combinado` — El texto explicativo dice que no hay puntaje y que son conteos, no una predicción.
- `test_siempre_indica_el_perfil_usado` — Con el perfil por defecto lo dice; no aparece el aviso de perfil personalizado.
- `test_las_capas_son_las_tres_lentes_y_la_brecha_solo_donde_existe` — food_drink ofrece la brecha como capa exploratoria; hospital no la tiene.
- `test_la_lista_de_celdas_empieza_por_las_de_mercado_alto_y_competencia_baja` — La primera opción lleva la estrella del filtro de oportunidad, y la nota dice cuántas celdas son.
- `test_el_porcentaje_de_candidatas_no_se_redondea_a_cero` — 5 de 1139 es 0,4 %: con cero decimales se leía «0%», que parece «ninguna celda». Se muestra con un decimal.
- `test_el_mapa_rotula_la_celda_elegida` — El punto azul de la celda elegida lleva su identificador, para que se sepa cuál es sin abrir la ficha.
- `test_el_mapa_sin_celda_elegida_no_dibuja_el_marcador` — Si no hay celda elegida no se añade ningún marcador (ni rótulo) extra.
- `test_los_puntos_del_mapa_son_legibles` — Los puntos de celda no son diminutos ni casi transparentes (se confundían con las etiquetas del mapa base).
- `test_la_ficha_muestra_las_tres_lentes_y_la_confianza` — La ficha de la celda elegida trae competencia, mercado, proveedores y la confianza (que no es una probabilidad).
- `test_el_mapa_y_la_ficha_usan_el_perfil_elegido` — Una celda con competencia indirecta la pierde al quitar ese tipo de competencia: las lentes se recalculan con el perfil del usuario, no con el de por defecto.
- `test_la_brecha_de_la_ficha_se_etiqueta_como_exploratoria_y_no_validada` — Donde hay brecha, la ficha la muestra con la advertencia de que no está validada y el intervalo no es de confianza.
- `test_sin_brecha_no_hay_advertencia_de_brecha` — En una categoría sin brecha no aparece ninguna advertencia sobre ella.
- `test_elegir_la_capa_de_brecha_muestra_la_advertencia_de_capa` — Cambiar a la capa de brecha añade el aviso de que es exploratoria y puede reflejar solo la saturación.
- `test_quitar_un_segmento_marca_el_perfil_como_personalizado` — Al cambiar un control, la pantalla lo dice y el perfil ya no es el por defecto.
- `test_volver_al_perfil_por_defecto_quita_el_aviso` — Restaurar la selección original devuelve el perfil por defecto.
- `test_quitar_la_competencia_indirecta_avisa_de_que_el_panorama_es_mas_optimista` — Quitar más de la mitad de la competencia por defecto genera el aviso del diseño.
- `test_dejar_vacia_la_competencia_directa_avisa_y_conserva_la_de_por_defecto` — No se puede quedar sin competencia directa: se avisa y se usa la de por defecto.
- `test_cambiar_el_perfil_no_cambia_la_brecha_y_la_pantalla_lo_dice` — La brecha de la misma celda es idéntica con el perfil por defecto y con uno personalizado, y la ficha avisa de que usa las categorías estándar.
- `test_sin_tabla_la_seccion_lo_dice_y_no_falla` — Con un directorio vacío no hay excepción: se informa y se indica cómo generarla.
- `test_con_la_tabla_alterada_la_seccion_se_niega_a_mostrarla` — Si un CSV no coincide con el hash del manifiesto, no se muestra nada de él.
- `test_la_pagina_muestra_el_panorama_despues_de_buscar` — Sin pulsar el botón no hay resultados; al buscar aparecen el MCDA por zona y debajo el panorama por celda.
- `test_los_resultados_sobreviven_a_cambiar_un_control_del_panorama` — Regresión: cada cambio de un control vuelve a ejecutar la página con el botón en False; antes los resultados desaparecían. Ahora se recuerda el texto buscado.
- `test_buscar_con_texto_vacio_avisa_y_no_deja_resultados_viejos` — Un texto vacío da el aviso de siempre y borra lo buscado antes.
- `test_cambiar_de_negocio_no_arrastra_los_ajustes_del_anterior` — Los controles del panorama son propios de cada categoría: tras ajustar el perfil de un restaurante y buscar una farmacia, el perfil de la farmacia es el de por defecto.

## `tests/test_tests_documentation.py`

> La documentación de los tests no puede quedarse atrás del código.
>
> Hay una regla del proyecto: todos los tests están documentados. Este archivo la hace cumplir en el CI:
>   1. docs/TESTS.md (el catálogo, una línea por test) debe coincidir con lo que genera
>      tools/generate_tests_doc.py a partir de tests/;
>   2. todo archivo `tests/test_*.py` debe aparecer en la tabla de la sección *Tests* del README, y
>      la tabla no puede citar un archivo que ya no exista.
>
> Si falla, el mensaje dice exactamente qué hacer.

- `test_el_catalogo_de_tests_esta_al_dia` — `docs/TESTS.md` coincide con lo que genera `tools/generate_tests_doc.py` a partir de los tests actuales.
- `test_el_catalogo_menciona_cada_funcion_de_test` — Ninguna función `test_*` puede faltar en el catálogo (aunque el resto del texto cambie).
- `test_todo_archivo_de_test_esta_en_la_tabla_del_readme` — Cada archivo `tests/test_*.py` tiene su fila en la tabla de tests del README.
- `test_la_tabla_del_readme_no_cita_archivos_que_ya_no_existen` — La tabla de tests del README no cita archivos de test que ya no existen.
- `test_parametrize_con_literales_cuenta_los_casos` — Un `parametrize` con una lista literal cuenta sus casos.
- `test_parametrize_apilado_multiplica` — Dos `parametrize` apilados multiplican sus casos.
- `test_parametrize_con_valores_no_literales_no_se_puede_contar` — Si los valores de `parametrize` no son literales, el número de casos es `None`.
- `test_sin_parametrize_es_un_caso` — Un test sin `parametrize` cuenta como un caso.
- `test_el_generador_encuentra_funciones_y_metodos_de_clases_test` — El generador del catálogo encuentra las funciones de test y los métodos de clases `Test*`, usa la primera frase del docstring e ignora lo que no es test.

## `tests/test_text_hibrido.py`

> Pruebas del sistema híbrido de interpretación del texto (src/ml/text_hibrido.py) y de la carga verificada del modelo
> adoptado en la fase 3: palabras clave primero y, solo si se abstienen, el clasificador entrenado.

- `test_las_palabras_clave_mandan_aunque_el_modelo_diga_otra_cosa` — Si las palabras clave reconocen el negocio, esa es la respuesta y ni siquiera se consulta al modelo.
- `test_el_modelo_solo_entra_cuando_las_palabras_clave_se_abstienen` — Con un texto que las palabras clave no reconocen, responde el modelo y se indica su confianza.
- `test_si_el_modelo_tambien_se_abstiene_no_se_adivina` — Sin respuesta de ninguno de los dos, no hay categoría (nunca se elige una al azar).
- `test_sin_modelo_el_comportamiento_es_el_de_las_palabras_clave_solas` — Sin modelo (no hay artefacto o no se verificó) se vuelve al comportamiento anterior.
- `test_un_texto_vacio_o_nulo_no_falla` — Vacío, solo espacios o None no rompen la pantalla ni el modelo: no hay categoría.
- `test_con_el_modelo_real_una_errata_se_entiende_y_sin_el_no` — Caso de extremo a extremo con el artefacto versionado: «una pizeria» no es una palabra clave, pero el modelo la entiende como restauración; sin modelo no se entendía.
- `test_el_modelo_versionado_se_carga_y_su_hash_coincide_con_el_manifiesto` — El artefacto de data/ml/ está adoptado, completo y es el que describe su manifiesto.
- `test_sin_archivos_no_hay_modelo_y_se_avisa` — Sin modelo en la carpeta devuelve None y deja un aviso, en vez de fallar.
- `test_un_modelo_que_el_manifiesto_no_da_por_adoptado_no_se_usa` — Aunque el archivo exista y su hash cuadre, si el manifiesto dice adoptado=false no se usa.
- `test_un_modelo_alterado_no_se_usa` — Si el archivo del modelo cambia (hash distinto al del manifiesto), no se carga.
- `test_un_manifiesto_roto_o_incompleto_no_rompe_la_carga` — JSON inválido o sin el hash del modelo: se vuelve a las palabras clave en vez de lanzar una excepción.
- `test_la_aplicacion_da_la_misma_respuesta_que_la_evaluacion_para_cada_frase` — El híbrido de la aplicación y el de la evaluación de la fase 3 coinciden frase a frase sobre las 192 del conjunto principal (mismo modelo, mismo umbral, mismas palabras clave). Así las cifras de docs/DISENO_ML_RECOMENDACION.md §3.L2 (76,0 % de exactitud, 6,2 % de respuestas equivocadas) son las de lo que ve el usuario.

## `tests/test_time_series.py`

> Unit tests for time series analysis.

- `test_initialization` — Test TimeSeriesAnalytics initialization.
- `test_seasonal_decomposition` — Test seasonal decomposition.
- `test_stationarity_tests` — Test stationarity tests (ADF, KPSS).
- `test_autocorrelation_analysis` — Test autocorrelation analysis.
- `test_change_point_detection` — Test change point detection.
- `test_day_of_week_patterns` — Test day of week pattern analysis.
- `test_hourly_patterns` — Test hourly pattern analysis.
- `test_correlation_analysis` — Test correlation analysis.
- `test_forecast_summary` — Test forecast summary.
- `test_insufficient_data` — Test handling of insufficient data.

## `tests/test_travel_time_predictor.py`

> Tests del modelo simple por ruta: src/models/travel_time_model.py (TravelTimePredictor) y src/predictor.py
> (RoutePredictor, el orquestador que usa train_models.py).

- `test_prepare_features_devuelve_las_seis_variables_y_el_objetivo` — `prepare_features` devuelve las seis variables esperadas y el objetivo, con la hora entre 0 y 23 y el día de la semana entre 0 y 6.
- `test_prepare_features_acepta_columnas_sin_prefijo_origin` — `prepare_features` acepta columnas de clima sin el prefijo `origin_`.
- `test_prepare_features_rellena_nulos_con_cero` — `prepare_features` rellena los nulos con 0.
- `test_prepare_features_sin_una_columna_necesaria_devuelve_vacio` ×4 — Si falta una columna necesaria (parametrizado), `prepare_features` devuelve tablas vacías.
- `test_prepare_features_con_dataframe_vacio` — `prepare_features` con un DataFrame vacío devuelve tablas vacías.
- `test_entrena_y_registra_las_features` — El modelo entrena, registra sus variables y su estado, y las importancias suman 1.
- `test_no_entrena_con_pocas_muestras_ni_sin_columnas` — No entrena con menos muestras que el mínimo ni si faltan columnas, y lo indica devolviendo `False`.
- `test_no_entrena_si_el_objetivo_tiene_nulos` — RandomForest no admite NaN en el objetivo: el error se captura y train() devuelve False.
- `test_predict_devuelve_tiempo_y_confianza_razonables` — Regresión: predict() devolvía SIEMPRE None, porque se le pasaban al escalador columnas con otro nombre (origin_temperature/origin_humidity) que las del ajuste (temperature/humidity) y sklearn lo rechazaba; el except lo ocultaba. El modelo por ruta que documenta el README no producía ninguna predicción.
- `test_predict_responde_a_los_datos_de_entrada` — El modelo aprende la relación: con un tiempo sin tráfico mayor, predice más.
- `test_predict_sin_entrenar_devuelve_none` — Predecir sin haber entrenado devuelve `None`, y la importancia de variables queda vacía.
- `test_predict_usa_el_historico_como_lag_y_si_falta_el_tiempo_sin_trafico` — `historical_avg or no_traffic_time`: con histórico se usa como lag; con None o 0 (falsy) se usa el tiempo sin tráfico. Se espía la entrada que recibe el escalador.
- `test_el_lag_es_la_media_de_las_5_mediciones_anteriores_sin_la_actual` — travel_time_min_lag de la fila i = media de las hasta 5 mediciones ANTERIORES; la primera fila, sin historia, usa no_traffic_time_min (el mismo respaldo que al predecir sin histórico).
- `test_el_lag_no_depende_del_objetivo_ni_de_lo_posterior` — Regresión de la fuga: el lag incluía la propia medición que se quiere predecir (y, al llegar las filas de más reciente a más antigua, también mediciones posteriores). Cambiar el valor de la fila i y de las siguientes no debe alterar el lag de la fila i; cambiar las anteriores sí.
- `test_las_filas_en_orden_inverso_dan_las_mismas_variables_que_en_orden_cronologico` — La base entrega las filas de la más reciente a la más antigua (ORDER BY timestamp DESC): el orden de entrada no debe cambiar las variables ni el objetivo de cada medición.
- `test_guardar_y_cargar_reproduce_las_predicciones` — Un modelo guardado y vuelto a cargar da las mismas predicciones.
- `test_no_guarda_un_modelo_sin_entrenar_y_carga_falla_con_gracia` — No guarda un modelo sin entrenar y cargar un archivo inexistente, corrupto o incompleto devuelve `False` sin lanzar excepción.
- `test_el_nombre_del_archivo_del_modelo_no_tiene_espacios` — El nombre del archivo del modelo de una ruta cambia los espacios por guiones bajos y cuelga del directorio de modelos.
- `test_crea_el_directorio_de_modelos_y_cachea_el_modelo_por_ruta` — Se crea el directorio de modelos y el modelo de cada ruta se reutiliza; la ruta inversa es otro modelo.
- `test_entrena_una_ruta_con_suficientes_datos_y_guarda_el_modelo` — Una ruta con suficientes datos se entrena y su modelo queda guardado en disco.
- `test_no_entrena_una_ruta_con_pocas_muestras` — Una ruta con pocas muestras no se entrena ni se guarda.
- `test_min_samples_del_predictor_llega_al_modelo` — Regresión: el predictor comprobaba su min_samples pero el modelo usaba su propio mínimo (50), así que con min_samples=30 (como train_models.py) una ruta de 40 muestras fallaba al entrenar.
- `test_train_all_models_devuelve_un_resultado_por_ruta` — `train_all_models` devuelve un resultado por ruta: entrenada o no.
- `test_predice_el_tiempo_de_viaje_de_una_ruta_entrenada` — Una ruta entrenada predice un tiempo de viaje plausible con una confianza entre 50 y 100.
- `test_sin_modelo_entrenado_no_hay_prediccion` — Sin modelo entrenado para la ruta no hay predicción (`None`).
- `test_al_predecir_el_lag_es_la_media_de_las_5_mediciones_mas_recientes` — Regresión: se promediaban las 100 últimas, una variable distinta de la que el modelo vio al entrenar.
- `test_un_predictor_nuevo_reutiliza_los_modelos_guardados` — Un predictor nuevo carga los modelos ya guardados en disco.
- `test_el_estado_de_los_modelos` — El estado de los modelos lista todas las rutas; las entrenadas incluyen la importancia de variables y las demás no.

## `tests/test_validate_ensemble_model.py`

> Tests de tools/validate_ensemble_model.py: validación fuera de muestra del ensemble por ruta, y la demostración de que la
> R² en muestra (la que se informaba antes) engaña.

- `test_evaluate_route_devuelve_las_metricas_y_mide_el_20_por_ciento_mas_reciente` — Devuelve R² en y fuera de muestra, el MAE del ensemble y el de las dos referencias, sobre el 20 % más reciente.
- `test_las_rutas_con_pocas_filas_se_omiten` — Una ruta con menos filas que el mínimo no se evalúa.
- `test_con_ruido_puro_la_r2_en_muestra_es_mayor_que_la_de_fuera_de_muestra` — La demostración: la R² en muestra (la que se informaba antes) supera a la honesta, que con ruido no pasa de ~0.
- `test_el_orden_de_las_filas_de_entrada_no_cambia_el_resultado` — La base entrega las filas de la más reciente a la más antigua; el corte las ordena, así que el resultado no depende del orden de entrada (con tolerancia: los bosques multihilo suman en un orden que varía).
- `test_summarize_anade_la_fila_media_sin_ponderar` — La tabla trae una fila por ruta y una fila MEDIA con el promedio simple entre rutas.
- `test_el_veredicto_dice_que_no_mejora_si_pierde_frente_a_repetir_la_ultima_medicion` — Si el ensemble tiene más error que repetir la última medición de la misma fuente, el veredicto lo dice y cuenta en cuántas rutas gana.
- `test_el_veredicto_dice_que_mejora_si_gana_en_la_media` — Si el ensemble tiene menos error medio que la referencia, el veredicto dice que mejora.
- `test_main_es_de_solo_lectura_y_muestra_las_dos_r2` — La herramienta no modifica la base ni crea archivos junto a ella, e imprime la R² en muestra, la de fuera y el veredicto.
- `test_main_sin_rutas_suficientes_devuelve_error` — Si ninguna ruta llega al mínimo de filas, devuelve 1 y lo dice.

## `tests/test_validate_travel_time_model.py`

> Tests de tools/validate_travel_time_model.py: validación cronológica del modelo simple por ruta, y la demostración
> de que el `lag` antiguo filtraba el objetivo.

- `test_la_construccion_antigua_filtraba_el_objetivo_y_la_nueva_no` — Con una serie de ruido puro nada del pasado predice el presente: un modelo honesto no puede ganar mucho a la media, pero el lag antiguo (que incluía la medición a predecir) daba un error artificialmente bajo.
- `test_la_version_anterior_solo_se_calcula_si_se_pide`
- `test_las_rutas_con_pocas_filas_se_omiten`
- `test_el_corte_es_cronologico_se_mide_en_el_20_por_ciento_mas_reciente`
- `test_el_orden_de_las_filas_de_entrada_no_cambia_el_resultado` — Con tolerancia: el bosque aleatorio multihilo suma en un orden que varía y deja diferencias de ~1e-15 min entre ejecuciones idénticas (medido: en la mitad de ellas), así que una igualdad exacta fallaba al azar.
- `test_el_ultimo_valor_se_toma_de_la_misma_fuente` — Alternando fuentes con valores muy distintos, 'último de la misma fuente' acierta y 'último a secas' no.
- `test_el_veredicto_depende_de_si_el_modelo_gana_a_la_persistencia`
- `test_la_herramienta_lee_en_solo_lectura_e_imprime_el_informe`
- `test_sin_rutas_suficientes_devuelve_error`
- `test_load_measurements_ignora_filas_sin_tiempo_de_viaje_y_parsea_fechas`
- `test_features_version_anterior_documenta_el_orden_y_la_inclusion_de_la_fila_actual` — La versión antigua (solo para comparar) ordena de la más reciente a la más antigua e incluye la fila actual.

## Archivos de apoyo (no contienen tests)

- `tests/conftest.py` — Configuración común de pytest.
