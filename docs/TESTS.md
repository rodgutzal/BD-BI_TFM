# Catálogo de tests

> **Archivo generado automáticamente. No editar a mano.** Se deriva del código de `tests/` con
> `python tools/generate_tests_doc.py`; el CI (`tests/test_tests_documentation.py`) falla si
> está desactualizado. Para añadir un test: escríbelo con un nombre y un docstring descriptivos,
> añade su archivo a la tabla de la sección *Tests* del README (si es un archivo nuevo) y
> regenera este catálogo.

**43 archivos · 709 funciones de test · 798 casos** (un caso es una ejecución: un test parametrizado genera varios).

| Archivo | Funciones | Casos |
|---|---:|---:|
| [`tests/test_analyst_quality.py`](#teststest_analyst_qualitypy) | 6 | 6 |
| [`tests/test_analyst_tabs.py`](#teststest_analyst_tabspy) | 22 | 30+ |
| [`tests/test_analytics.py`](#teststest_analyticspy) | 3 | 3 |
| [`tests/test_api.py`](#teststest_apipy) | 14 | 20 |
| [`tests/test_api_clients.py`](#teststest_api_clientspy) | 22 | 22+ |
| [`tests/test_business_type_classifier.py`](#teststest_business_type_classifierpy) | 7 | 20 |
| [`tests/test_causal_analysis.py`](#teststest_causal_analysispy) | 21 | 30 |
| [`tests/test_check_collection_gaps.py`](#teststest_check_collection_gapspy) | 10 | 10 |
| [`tests/test_collector.py`](#teststest_collectorpy) | 38 | 38+ |
| [`tests/test_config.py`](#teststest_configpy) | 4 | 4 |
| [`tests/test_dashboards_executive_maps.py`](#teststest_dashboards_executive_mapspy) | 23 | 34+ |
| [`tests/test_data_profile.py`](#teststest_data_profilepy) | 15 | 15 |
| [`tests/test_database.py`](#teststest_databasepy) | 4 | 4 |
| [`tests/test_database_windows.py`](#teststest_database_windowspy) | 12 | 12 |
| [`tests/test_demographics.py`](#teststest_demographicspy) | 15 | 15 |
| [`tests/test_ensemble_predictor.py`](#teststest_ensemble_predictorpy) | 7 | 7 |
| [`tests/test_forecasting.py`](#teststest_forecastingpy) | 9 | 9 |
| [`tests/test_foursquare_client.py`](#teststest_foursquare_clientpy) | 12 | 28 |
| [`tests/test_hybrid_scheduler.py`](#teststest_hybrid_schedulerpy) | 3 | 3 |
| [`tests/test_location_scoring.py`](#teststest_location_scoringpy) | 22 | 22 |
| [`tests/test_locations.py`](#teststest_locationspy) | 5 | 5 |
| [`tests/test_medallion.py`](#teststest_medallionpy) | 20 | 20 |
| [`tests/test_migrations.py`](#teststest_migrationspy) | 18 | 18 |
| [`tests/test_ml_context.py`](#teststest_ml_contextpy) | 33 | 33+ |
| [`tests/test_ml_grid.py`](#teststest_ml_gridpy) | 19 | 22 |
| [`tests/test_ml_inputs_bundle.py`](#teststest_ml_inputs_bundlepy) | 36 | 36 |
| [`tests/test_ml_lenses.py`](#teststest_ml_lensespy) | 38 | 38+ |
| [`tests/test_ml_panorama.py`](#teststest_ml_panoramapy) | 36 | 36 |
| [`tests/test_ml_panorama_view.py`](#teststest_ml_panorama_viewpy) | 23 | 23 |
| [`tests/test_ml_text_classifier.py`](#teststest_ml_text_classifierpy) | 34 | 47 |
| [`tests/test_ml_validation.py`](#teststest_ml_validationpy) | 31 | 33+ |
| [`tests/test_normalize_bronze_timestamps.py`](#teststest_normalize_bronze_timestampspy) | 15 | 15 |
| [`tests/test_operations_status.py`](#teststest_operations_statuspy) | 11 | 16 |
| [`tests/test_ors_null_fields.py`](#teststest_ors_null_fieldspy) | 2 | 2 |
| [`tests/test_poi_extraction.py`](#teststest_poi_extractionpy) | 23 | 23 |
| [`tests/test_predictive_modeling_dashboard.py`](#teststest_predictive_modeling_dashboardpy) | 7 | 7 |
| [`tests/test_predictive_modeling_ondemand.py`](#teststest_predictive_modeling_ondemandpy) | 6 | 6 |
| [`tests/test_query_measurements_polyline.py`](#teststest_query_measurements_polylinepy) | 8 | 8 |
| [`tests/test_recommendation_dashboard.py`](#teststest_recommendation_dashboardpy) | 6 | 6 |
| [`tests/test_recommendation_panorama_ui.py`](#teststest_recommendation_panorama_uipy) | 25 | 25+ |
| [`tests/test_tests_documentation.py`](#teststest_tests_documentationpy) | 9 | 9 |
| [`tests/test_time_series.py`](#teststest_time_seriespy) | 10 | 10 |
| [`tests/test_travel_time_predictor.py`](#teststest_travel_time_predictorpy) | 25 | 28 |

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

- `test_la_api_usa_la_base_indicada_por_variable_de_entorno`
- `test_ruta_sin_datos_responde_404_y_no_400` ×5
- `test_el_detail_del_404_es_el_mensaje_original`
- `test_analisis_invalido_es_422`
- `test_parametros_fuera_de_rango_son_422` ×3
- `test_health`
- `test_routes`
- `test_rankings_con_gold_vacio_no_falla`
- `test_statistics`
- `test_anomalies`
- `test_json_safe_sustituye_nan_e_infinito_por_none` — JSON no admite NaN/inf: se convierten en None, también dentro de dicts y listas anidados. Los escalares de numpy (np.bool_, np.float64) pasan a tipos nativos de Python.
- `test_time_series_patrones_con_un_dia_de_una_sola_muestra` — Regresión: un día con 1 muestra tiene desviación típica NaN y el endpoint devolvía 500 (dependía de la hora a la que se ejecutaba: justo tras la medianoche UTC).
- `test_time_series_patrones`
- `test_predict_devuelve_json_serializable_y_modelos_entrenados` — De punta a punta: entrena el ensemble con los datos y responde. Cubre también que el resultado se serialice (antes `model_predictions` se apuntaba a sí mismo).

## `tests/test_api_clients.py`

> Tests de los clientes HTTP (TomTom, OpenRouteService, OpenWeather, Overpass).
>
> Sin red: se sustituye `client.session` por una sesión falsa que devuelve respuestas fijas o lanza
> excepciones de `requests`, y se comprueba la petición que se habría enviado y el parseo del resultado.

- `test_la_sesion_reintenta_solo_errores_transitorios` — Cada cliente monta reintentos sobre https: 4 intentos, solo para 429/5xx y solo para su método HTTP.
- `test_close_cierra_la_sesion`
- `test_tomtom_parsea_la_ruta_y_envia_la_peticion_correcta`
- `test_tomtom_sin_campos_opcionales_deduce_el_tiempo_sin_trafico` — Sin trafico ni noTrafficTravelTime: retraso 0 y tiempo sin tráfico = tiempo de viaje; sin polyline.
- `test_tomtom_con_tiempo_cero_no_divide_por_cero`
- `test_tomtom_propaga_los_errores`
- `test_ors_parsea_la_ruta_con_las_mismas_claves_que_tomtom`
- `test_ors_envia_longitud_antes_que_latitud_y_la_clave_en_la_cabecera`
- `test_ors_propaga_los_errores`
- `test_weather_parsea_y_pide_unidades_metricas`
- `test_weather_respuesta_incompleta_da_none_y_unknown`
- `test_weather_usa_la_cache_por_ubicacion_y_caduca`
- `test_weather_un_error_no_se_guarda_en_cache`
- `test_weather_propaga_los_errores`
- `test_overpass_clasifica_por_prioridad_y_toma_el_valor_como_subcategoria`
- `test_overpass_la_query_cubre_todas_las_categorias`
- `test_overpass_parsea_nodos_y_ways_y_descarta_lo_inutil`
- `test_overpass_fetch_calcula_el_bbox_con_margen_y_el_timeout_del_servidor`
- `test_overpass_prueba_el_siguiente_espejo_si_uno_falla`
- `test_overpass_json_invalido_cuenta_como_fallo_del_espejo`
- `test_overpass_si_todos_los_espejos_fallan_lanza_runtimeerror`
- `test_overpass_envia_un_user_agent_descriptivo`

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

- `test_el_constructor_ordena_por_tiempo_parsea_utc_y_no_modifica_el_original`
- `test_recupera_un_efecto_positivo_conocido`
- `test_sin_efecto_no_sale_significativo`
- `test_un_efecto_negativo_lleva_signo_negativo`
- `test_sin_variables_de_ajuste_no_hay_propensity_score`
- `test_usa_otra_columna_de_clima_si_se_pide`
- `test_ignora_las_filas_con_nulos_y_exige_30_filas`
- `test_columnas_ausentes_devuelven_error`
- `test_la_simulacion_recupera_el_coeficiente_y_escenarios_coherentes`
- `test_la_simulacion_valida_los_datos`
- `test_mide_una_mejora_antes_despues`
- `test_una_degradacion_se_marca_como_tal`
- `test_sin_cambio_no_es_significativo_y_el_efecto_es_despreciable`
- `test_intervencion_valida_columna_y_tamano_de_los_periodos`
- `test_serie_constante_no_divide_por_cero`
- `test_detecta_la_hora_como_confusor_cuando_afecta_a_temperatura_y_trafico`
- `test_la_hora_no_es_confusor_si_solo_afecta_a_una_de_las_dos_variables` — Un confusor debe afectar al tratamiento Y al resultado: con solo uno de los dos no se marca.
- `test_detecta_el_dia_de_la_semana_si_el_trafico_varia_mas_de_un_20_por_ciento`
- `test_sin_confusores_la_lista_esta_vacia_y_hay_recomendaciones`
- `test_interpretacion_del_p_valor` ×4
- `test_interpretacion_de_cohen` ×7

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

## `tests/test_collector.py`

> Tests del orquestador de recolección (src/collector.py): DataCollector de punta a punta y el bucle real de
> HybridScheduler.
>
> Sin red ni esperas: los clientes TomTom/ORS/OpenWeather se sustituyen por falsos, `time.sleep` por un contador y
> `signal.signal` por un registro (para no tocar el manejador de Ctrl+C de pytest). La base es temporal y el
> heartbeat se redirige (el real vive en logs/heartbeat y lo lee el HEALTHCHECK de Docker).

- `test_rechaza_una_fuente_desconocida`
- `test_la_fuente_elige_el_cliente`
- `test_timescale_solo_se_activa_con_configuracion`
- `test_el_manejador_de_parada_solo_se_registra_si_se_pide` — Se escuchan Ctrl+C y SIGTERM (la de `docker stop`); antes solo SIGINT y Docker acababa matando con SIGKILL.
- `test_una_senal_de_parada_baja_la_bandera_sin_salir_ni_cerrar_los_clientes` — Antes el manejador hacía sys.exit(0) y cerraba los clientes en cualquier punto del ciclo: se perdía el ciclo (si estaba pidiendo datos) o se guardaba a medias (CSV sí, SQLite no). Ahora solo pide parar.
- `test_una_segunda_senal_sale_sin_esperar`
- `test_la_senal_durante_un_ciclo_deja_que_termine_y_lo_guarda` — Si llega la señal a mitad de un ciclo, el ciclo se completa y se guarda; después el bucle sale y cierra los clientes.
- `test_close_no_falla_si_un_cliente_ya_estaba_cerrado_o_falla`
- `test_run_continuous_cierra_los_clientes_aunque_el_ciclo_lance_una_excepcion`
- `test_un_ciclo_guarda_todas_las_rutas_en_csv_y_sqlite`
- `test_cada_ruta_lleva_el_clima_de_su_origen_y_destino_y_se_pide_una_vez_por_lugar`
- `test_el_nivel_de_movilidad_cambia_justo_por_encima_de_20_minutos` — > 20 min es 'Alta demora'; 20 exactos todavía es normal (umbral estricto).
- `test_si_falla_el_clima_de_un_lugar_la_ruta_se_guarda_sin_clima`
- `test_si_falla_una_ruta_se_siguen_guardando_las_demas`
- `test_si_fallan_todas_las_rutas_no_se_guarda_nada_ni_hay_latido`
- `test_si_falla_el_guardado_devuelve_cero_y_no_hay_latido`
- `test_con_timescale_activo_se_guarda_tambien_alli_con_su_configuracion`
- `test_sin_timescale_no_se_intenta_guardar_alli`
- `test_el_heartbeat_se_escribe_en_logs_del_proyecto_con_la_hora_del_ciclo`
- `test_un_heartbeat_que_no_se_puede_escribir_no_rompe_el_ciclo`
- `test_el_ciclo_alimenta_bronze_silver_y_gold_solo_con_sus_registros`
- `test_cada_ciclo_procesa_solo_sus_propios_registros_en_silver` — El medallón es incremental: el 2º ciclo transforma únicamente las filas de Bronze de ese ciclo, no todo el histórico (sería lento y reprocesaría datos ya vistos).
- `test_sin_medallon_no_se_crean_las_capas`
- `test_un_fallo_del_medallon_no_impide_guardar_ni_cambia_el_resultado` — Executive es una vista adicional: si Bronze revienta, CSV/SQLite ya están guardados y el ciclo cuenta.
- `test_si_bronze_no_responde_success_se_omite_silver_y_gold`
- `test_run_once_hace_un_solo_ciclo`
- `test_run_continuous_espera_el_intervalo_segundo_a_segundo_y_se_detiene`
- `test_run_continuous_termina_si_se_detiene_durante_el_ciclo`
- `test_el_hibrido_registra_un_unico_manejador_y_guarda_los_intervalos`
- `test_en_el_primer_tick_corren_las_dos_fuentes_y_despues_ninguna_hasta_su_intervalo`
- `test_una_fuente_vencida_corre_y_la_otra_no`
- `test_si_se_detiene_durante_un_ciclo_no_dispara_la_otra_fuente`
- `test_el_hibrido_ante_una_senal_baja_la_bandera_sin_salir`
- `test_el_hibrido_con_una_segunda_senal_sale_sin_esperar`
- `test_el_hibrido_termina_el_ciclo_en_curso_y_cierra_los_dos_collectors` — La señal llega durante el ciclo de ORS: ese ciclo termina, no se dispara el de TomTom y se cierran ambos.
- `test_el_hibrido_cierra_los_collectors_aunque_el_ciclo_lance_una_excepcion`
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

- `test_executive_abre_con_datos_y_muestra_las_tarjetas`
- `test_executive_tablas_de_mejores_y_peores_rutas`
- `test_executive_sin_periodo_anterior_no_inventa_deltas`
- `test_executive_con_periodo_anterior_calcula_el_delta_con_los_datos`
- `test_delta` ×5
- `test_executive_alertas_segun_los_umbrales` ×6
- `test_executive_si_el_resumen_falla_muestra_el_error_y_no_sigue`
- `test_executive_con_la_base_vacia_no_lanza_excepciones`
- `test_executive_con_la_base_vacia_no_muestra_un_0_por_ciento_ni_una_alerta_falsa` — Sin mediciones la fiabilidad no es 0 %: es desconocida. Antes salía «0.0%» y la alerta «Low system reliability».
- `test_executive_con_datos_sigue_mostrando_las_cifras_y_las_alertas` — El aviso de «sin mediciones» no aparece cuando sí las hay.
- `test_hay_datos_solo_si_el_resumen_tiene_mediciones` ×3
- `test_color_segun_el_retraso`
- `test_el_mapa_dibuja_una_traza_por_ruta_mas_las_ubicaciones_y_colorea_por_retraso`
- `test_el_mapa_ignora_rutas_con_ubicaciones_desconocidas`
- `test_maps_abre_con_datos_y_la_tabla_de_estado_cubre_todas_las_rutas`
- `test_los_limites_de_los_estados_de_la_tabla_son_1_y_4_minutos_de_retraso` — <=1 libre, <=4 moderado, >4 denso (los mismos umbrales que el color del mapa).
- `test_maps_con_la_base_vacia_marca_todas_las_rutas_sin_dato`
- `test_maps_sin_rutas_seleccionadas_avisa`
- `test_maps_sin_pois_explica_como_cargarlos`
- `test_maps_con_pois_de_overpass_dibuja_la_capa_y_cuenta_los_elementos`
- `test_las_categorias_de_overpass_por_defecto_excluyen_las_masivas`
- `test_la_capa_de_pois_usa_la_fuente_indicada_y_no_mezcla_las_dos` — school/mall existen en los dos catálogos: elegir una fuente no debe dibujar los de la otra.
- `test_la_capa_de_pois_no_hace_nada_sin_categorias_o_con_fuente_invalida`

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
- `test_latest_observation_ignora_zonas_sin_observaciones`
- `test_latest_observation_prefiere_la_fecha_mas_reciente_en_el_mismo_anio`
- `test_summarize_history_encuentra_anios_comunes`
- `test_summarize_history_sin_anio_comun_o_con_zona_sin_datos`
- `test_reconcile_proyecta_con_la_tasa_nacional`
- `test_reconcile_no_toca_un_dato_igual_o_mas_nuevo_que_el_objetivo`
- `test_reconcile_respeta_un_anio_objetivo_explicito`
- `test_reconcile_omite_zonas_sin_tasa_nacional_para_su_anio`
- `test_reconcile_sin_serie_nacional`
- `test_reconcile_se_guarda_y_se_recupera_de_la_base`
- `test_guardar_solo_el_dcid_no_borra_la_poblacion_ya_guardada` — El upsert usa COALESCE: resolver un dcid no debe pisar datos existentes.
- `test_historial_de_poblacion_es_upsert`
- `test_clean_normaliza_nulos`
- `test_el_cliente_exige_api_key`

## `tests/test_ensemble_predictor.py`

> Unit tests for ensemble predictor.

- `test_ensemble_initialization` — Test ensemble predictor initialization.
- `test_feature_preparation` — Test feature preparation.
- `test_model_training` — Test ensemble model training.
- `test_prediction_output` — Test prediction output format.
- `test_anomaly_detection` — Test anomaly detection.
- `test_insufficient_data` — Test handling of insufficient data.
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

## `tests/test_location_scoring.py`

> Pruebas del sistema de puntuación de zonas (MCDA) de location_scoring.py.
>
> Usan una RouteDatabase real sobre un directorio temporal (no mocks), para
> ejercitar también los métodos de database.py que consume el módulo.

- `test_haversine_conocida`
- `test_normalize_minmax_basico`
- `test_normalize_minmax_sin_variacion_queda_en_medio_no_en_cero`
- `test_normalize_minmax_conserva_nan`
- `test_demanda_sin_demografia_es_nan_no_cero`
- `test_demanda_lee_poblacion_guardada`
- `test_competencia_cuenta_solo_dentro_del_radio`
- `test_competencia_filtra_por_categoria`
- `test_competencia_food_drink_se_corrige_por_cobertura_de_osm`
- `test_competencia_sin_pois_es_cero`
- `test_accesibilidad_promedia_rutas_que_tocan_la_zona`
- `test_pesos_por_defecto_suman_uno`
- `test_pesos_que_no_suman_uno_lanzan_error`
- `test_mas_demanda_mejora_el_puntaje`
- `test_mas_competencia_empeora_el_puntaje`
- `test_mas_tiempo_de_viaje_empeora_el_puntaje`
- `test_zona_sin_dato_se_trata_como_neutral_no_como_la_peor`
- `test_un_peso_en_cero_ignora_esa_dimension`
- `test_el_puntaje_queda_entre_0_y_1`
- `test_recomienda_de_extremo_a_extremo`
- `test_recomendar_con_texto_incomprensible_lanza_error`
- `test_recomendar_acepta_pesos_personalizados`

## `tests/test_locations.py`

> Pruebas para el módulo de ubicaciones.

- `test_locations_exist` — Verifica que todas las ubicaciones estén definidas.
- `test_routes_exist` — Verifica que todas las rutas estén configuradas.
- `test_get_location` — Verifica que se puede obtener una ubicación por nombre.
- `test_get_all_unique_locations` — Verifica que se retornan todas las ubicaciones únicas.
- `test_invalid_location` — Verifica que se lanza error para ubicación inexistente.

## `tests/test_medallion.py`

> Pruebas del pipeline medallion (Bronze -> Silver -> Gold).

- `test_bronze_inserta_las_filas_validas`
- `test_bronze_es_idempotente_reingerir_no_duplica` — Regresión: Bronze no tenía restricción UNIQUE y reingerir las mismas filas (p. ej. al correr run_medallion_pipeline dos veces) las duplicaba.
- `test_bronze_ingiere_solo_lo_nuevo`
- `test_bronze_rechaza_datos_sin_columnas_requeridas`
- `test_bronze_descarta_duplicados_dentro_del_lote`
- `test_bronze_descarta_tiempos_fuera_de_rango_y_nulos`
- `test_bronze_guarda_timestamps_iso_con_t` — Regresión: pandas.to_sql guardaba un espacio en vez de 'T' y el collector nunca encontraba las filas de Bronze para pasárselas a Silver.
- `test_silver_transforma_y_agrega_variables_temporales`
- `test_silver_sin_tiempo_sin_trafico_deja_el_retraso_desconocido` — ORS no reporta tiempo sin tráfico: el retraso no se inventa.
- `test_silver_no_duplica_al_transformar_dos_veces`
- `test_silver_perfil_de_ruta_calcula_la_desviacion_sin_stddev_de_sql` — Regresión: get_route_profile usaba STDDEV(), que SQLite no trae.
- `test_silver_agregacion_horaria`
- `test_gold_calcula_kpis_por_ruta`
- `test_gold_recalcular_el_mismo_dia_no_falla_ni_duplica` — Regresión: el INSERT plano chocaba con UNIQUE(date, origin, destination) la segunda vez que se calculaban las KPIs de un mismo día.
- `test_gold_dia_sin_datos`
- `test_gold_ranking_ordena_por_fiabilidad`
- `test_gold_metricas_de_periodo`
- `test_gold_resumen_ejecutivo_en_base_vacia_devuelve_ceros_no_error` — Regresión: AVG()/SUM() sin filas dan NULL y float(NaN) reventaba, así que en un clon limpio (sin histórico) Executive mostraba "Error loading summary data".
- `test_gold_resumen_ejecutivo_con_datos`
- `test_pipeline_completo_es_idempotente`

## `tests/test_migrations.py`

> Tests de las migraciones del CSV histórico: a SQLite (src/migration.py) y a TimescaleDB (src/timescale_migration.py).
>
> Sin Postgres real: `psycopg2` se sustituye por un módulo falso que guarda las filas que se habrían insertado.

- `test_migra_el_csv_a_sqlite`
- `test_dry_run_no_crea_la_base`
- `test_descarta_filas_sin_campos_obligatorios`
- `test_data_source_vacio_o_ausente_pasa_a_unknown`
- `test_un_valor_numerico_ilegible_queda_nulo_sin_romper_la_migracion`
- `test_csv_inexistente_vacio_o_sin_columnas_obligatorias_devuelve_cero`
- `test_las_lineas_corruptas_del_csv_se_saltan`
- `test_migrar_dos_veces_no_duplica_filas` — El índice único de Bronze/route_measurements hace idempotente la migración.
- `test_cli_dry_run_no_pide_confirmacion`
- `test_cli_cancelada_no_migra`
- `test_cli_confirmada_o_con_skip_migra_y_usa_las_rutas_del_proyecto`
- `test_cli_devuelve_error_si_no_se_importa_nada_o_falla`
- `test_backfill_inserta_las_filas_con_el_orden_de_columnas_de_traffic_trips`
- `test_backfill_celdas_vacias_van_como_null_y_no_como_nan` — Regresión: una celda vacía llegaba como NaN (float) incluso a columnas de texto (origin_weather), que Postgres rechaza; con ello fallaba y se revertía todo el backfill. Ahora es None (NULL), y data_source vacío pasa a 'unknown' como en la migración a SQLite.
- `test_backfill_con_error_hace_rollback_y_devuelve_cero`
- `test_backfill_csv_inexistente_o_vacio_no_se_conecta`
- `test_backfill_sin_psycopg2_instalado_devuelve_cero`
- `test_backfill_main_devuelve_el_codigo_segun_las_filas`

## `tests/test_ml_context.py`

> Tests de la fase 1b: contexto de OpenStreetMap (src/ml/osm_context.py) y su efecto en las lentes, las variables y los
> modelos, y la herramienta de descarga tools/download_osm_context.py (sin red: cliente falso).

- `test_edificios_se_convierten_con_su_tipo_y_yes_por_defecto`
- `test_los_elementos_sin_coordenadas_se_descartan`
- `test_transporte_conserva_paradas_y_descarta_las_posiciones_duplicadas`
- `test_alojamiento_e_industria`
- `test_un_tema_desconocido_o_sin_uso_da_un_dataframe_vacio_con_las_columnas`
- `test_load_context_lee_los_json_ignora_los_corruptos_y_un_directorio_vacio_da_vacio`
- `test_no_residenciales_excluye_lo_que_no_es_vivienda`
- `test_las_celdas_activas_no_cambian_al_cargar_el_contexto` — Un edificio lejos de cualquier POI no activa una celda: así el conjunto de celdas es el mismo con y sin contexto.
- `test_residentes_cuenta_edificios_pero_no_los_industriales`
- `test_los_hoteles_cuentan_como_turistas_aunque_no_haya_atracciones`
- `test_sin_contexto_residentes_y_turistas_siguen_sin_datos`
- `test_el_indice_de_mercado_va_de_0_a_1_y_los_edificios_no_aplastan_a_los_demas_segmentos` — Regresión: mercado_total sumaba conteos en bruto, y con ~90 edificios por celda frente a ~1 colegio el índice era solo 'cuántos edificios hay'. Ahora cada segmento se escala por su máximo antes de promediar.
- `test_el_indice_de_mercado_es_una_media_y_no_una_suma` — Una celda que es el máximo en TODOS los segmentos con datos vale exactamente 1 (con una suma valdría 2).
- `test_las_variables_incluyen_el_contexto_solo_si_se_piden`
- `test_boosting_poi_no_usa_las_variables_de_contexto_y_solo_edificios_solo_esas`
- `test_los_modelos_opcionales_predicen_valores_positivos`
- `test_el_boosting_con_contexto_gana_al_que_no_lo_tiene_cuando_la_senal_esta_en_el_contexto`
- `test_compare_models_con_el_mismo_modelo_es_indistinguible`
- `test_validate_location_model_con_contexto_informa_si_el_contexto_aporta`
- `test_validate_location_model_sin_contexto_no_evalua_los_modelos_opcionales`
- `test_validate_location_model_con_un_directorio_de_contexto_vacio_valida_sin_contexto`
- `test_measure_lens_variance_con_contexto_da_datos_a_residentes`
- `test_las_franjas_cubren_toda_el_area_sin_huecos_ni_solapes`
- `test_la_consulta_lleva_el_bbox_el_timeout_del_servidor_y_pide_centro_y_etiquetas`
- `test_el_plan_pide_siete_trozos_y_el_edificado_va_en_franjas`
- `test_descargar_guarda_un_archivo_por_trozo_y_resume`
- `test_se_espera_entre_peticiones_pero_no_despues_de_la_ultima` — Cortesía con el servicio público: pausa entre peticiones, y ninguna espera inútil al terminar.
- `test_si_un_espejo_falla_se_prueba_el_siguiente`
- `test_si_todos_los_espejos_fallan_lanza_runtimeerror`
- `test_un_trozo_fallido_se_anota_y_el_resto_se_descarga`
- `test_dry_run_no_hace_llamadas_de_red_ni_crea_la_carpeta`
- `test_main_descarga_con_un_cliente_falso_y_devuelve_el_codigo_segun_los_fallos`
- `test_la_descarga_no_escribe_fuera_del_directorio_indicado`

## `tests/test_ml_grid.py`

> Tests de la rejilla de ~250 m (src/ml/grid.py) y de los conteos por celda (src/ml/cell_counts.py).

- `test_la_rejilla_es_fija_y_cubre_el_area`
- `test_las_celdas_miden_unos_250_m_en_las_dos_direcciones`
- `test_un_punto_cae_en_la_celda_cuyo_centro_esta_cerca`
- `test_puntos_fuera_de_la_rejilla_o_sin_coordenadas_dan_menos_uno`
- `test_los_bordes_de_la_rejilla`
- `test_identificadores_de_celda`
- `test_cells_frame_tiene_todas_las_celdas_y_cada_centro_cae_en_su_celda`
- `test_count_grid_cuenta_por_celda_e_ignora_lo_de_fuera`
- `test_los_anillos_tienen_las_celdas_esperadas` ×4
- `test_la_suma_por_anillos_pondera_la_vecindad`
- `test_los_bordes_no_dan_la_vuelta`
- `test_activas_son_las_celdas_con_algun_poi_en_ella_o_en_su_vecindad`
- `test_selector_toda_la_categoria_un_subconjunto_o_todo_menos_algo`
- `test_los_conteos_se_separan_por_categoria_y_subcategoria`
- `test_subcategoria_vacia_o_nula_se_cuenta_como_cadena_vacia`
- `test_los_pois_fuera_de_la_rejilla_se_cuentan_aparte`
- `test_sin_pois_los_conteos_estan_vacios_pero_las_consultas_funcionan`
- `test_exclude_quita_del_conteo_lo_que_cumple_el_objetivo`
- `test_la_tabla_celda_por_subcategoria`

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
- `test_requirements_fija_scipy_y_statsmodels` — Las dos librerías estadísticas del dashboard van con == (antes >=): una versión nueva puede cambiar resultados o no tener wheels para el Python de Docker y CI.
- `test_requirements_ml_fija_versiones_exactas` — requirements-ml.txt fija con == las librerías que cambian los números, y coinciden con las de requirements.txt cuando esta también las fija.

## `tests/test_ml_lenses.py`

> Tests de los perfiles de negocio, las tres lentes y las variables con control de fuga (src/ml/*)
> y de la herramienta tools/measure_lens_variance.py.

- `test_hay_un_perfil_por_cada_categoria_de_overpass`
- `test_cada_perfil_es_coherente`
- `test_los_selectores_de_segmentos_y_proveedores_usan_categorias_reales`
- `test_residentes_usan_edificios_y_los_distribuidores_sanitarios_siguen_sin_proxy`
- `test_perfil_inexistente_lanza_error`
- `test_el_comercio_generico_no_cuenta_las_oficinas_como_competencia`
- `test_ajustar_no_modifica_el_perfil_por_defecto`
- `test_una_lente_no_puede_quedar_vacia_y_se_conserva_el_valor_por_defecto`
- `test_una_lente_que_ya_estaba_vacia_por_defecto_puede_seguir_vacia`
- `test_los_nombres_desconocidos_se_descartan_con_aviso`
- `test_quitar_mas_de_la_mitad_de_la_competencia_avisa_de_optimismo`
- `test_anadir_competencia_no_cuenta_como_desviacion`
- `test_el_perfil_por_defecto_tiene_desviacion_cero_y_cambiarlo_todo_da_uno`
- `test_el_umbral_de_aviso_es_la_mitad`
- `test_la_competencia_se_pondera_por_vecindad`
- `test_solo_salen_las_celdas_activas_y_el_indice_es_cell_id`
- `test_segmento_sin_pois_es_nan_y_no_cero`
- `test_cero_y_sin_datos_son_cosas_distintas`
- `test_proveedores_total_y_diversidad`
- `test_el_apoyo_cuenta_pois_sin_ponderar_en_la_celda_y_sus_8_vecinas`
- `test_un_poi_cuenta_en_una_sola_lente_la_competencia_manda` — Precedencia: un bar es competencia de un restaurante y NO también 'vida nocturna'; una panadería, aquí proveedor, tampoco es competencia.
- `test_los_museos_no_son_a_la_vez_competencia_y_turistas_en_ocio`
- `test_lentes_con_datos_cuenta_cuantas_lentes_se_pueden_calcular`
- `test_ajustar_el_perfil_cambia_la_lente_sin_tocar_los_datos`
- `test_con_cero_pois_las_lentes_no_fallan`
- `test_cobertura_de_las_lentes`
- `test_las_variables_no_incluyen_el_objetivo_ni_en_la_celda_ni_en_la_vecindad` — Control de fuga: mover o añadir restaurantes NO cambia ninguna variable (si cambiara, el modelo de oferta esperada copiaría su propia etiqueta).
- `test_las_otras_categorias_si_entran_en_la_celda_y_en_los_anillos`
- `test_nombres_y_numero_de_variables`
- `test_el_objetivo_cuenta_solo_la_propia_celda`
- `test_distancia_al_centro_de_zona_mas_cercano`
- `test_poblacion_y_accesibilidad_suavizadas_con_las_zonas`
- `test_una_zona_sin_dato_se_omite_y_los_pesos_se_renormalizan`
- `test_la_herramienta_lee_en_solo_lectura`
- `test_describe_lens_excluye_nan_y_los_cuenta_aparte`
- `test_la_serie_constante_no_da_cv_infinito`
- `test_cuadrante_de_oportunidad`
- `test_la_herramienta_imprime_un_informe_por_perfil`

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
- `test_elegir_umbral_toma_el_de_mayor_exactitud_y_en_empate_el_mas_alto` — Con probabilidades que no discriminan entre umbrales el empate lo gana el más alto (más prudente).
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

## `tests/test_ml_validation.py`

> Tests de la fase 1 del ML de recomendación: lectura de datos en solo lectura (src/ml/data_access.py), modelos de
> oferta esperada (src/ml/models.py), validación espacial (src/ml/validation.py) y tools/validate_location_model.py.

- `test_la_lectura_es_de_solo_lectura`
- `test_foursquare_es_opcional`
- `test_tabla_de_zonas_con_poblacion_y_tiempo_de_viaje`
- `test_la_densidad_suma_las_categorias_en_log`
- `test_cada_modelo_usa_solo_sus_variables`
- `test_las_predicciones_son_positivas_y_tienen_una_por_fila`
- `test_una_linea_base_sin_su_unica_variable_degrada_a_la_media` — Regresión: sin demografía cargada la población llega toda NaN, se descarta y solo_poblacion fallaba con KeyError.
- `test_la_media_es_el_promedio_de_entrenamiento`
- `test_fit_predict_es_determinista_con_la_misma_semilla`
- `test_modelo_desconocido_lanza_error`
- `test_el_boosting_aprende_la_senal_y_gana_a_la_media`
- `test_una_variable_toda_nan_no_rompe_el_ajuste` ×3 — Regresión: sin datos de rutas la accesibilidad llega toda NaN y el boosting fallaba al discretizarla (ValueError: window shape cannot be larger than input array shape).
- `test_el_conjunto_da_media_y_dispersion`
- `test_las_celdas_de_un_bloque_comparten_etiqueta_y_el_desplazamiento_la_cambia`
- `test_los_pliegues_no_parten_un_bloque_y_estan_equilibrados`
- `test_la_desviacion_de_poisson_coincide_con_scikit_learn_y_los_casos_limite`
- `test_precision_en_las_k_primeras_y_spearman`
- `test_evaluate_devuelve_predicciones_fuera_de_muestra_para_todas_las_celdas`
- `test_la_prediccion_de_una_celda_no_usa_su_propio_valor` — Fuera de muestra de verdad: cambiar el valor real de una celda no cambia su propia predicción.
- `test_el_bootstrap_de_bloques_con_predicciones_identicas_da_cero`
- `test_el_bootstrap_detecta_una_mejora_uniforme_y_es_prudente_si_solo_hay_un_bloque_mejor`
- `test_decide_publica_solo_si_el_intervalo_queda_por_debajo_de_cero`
- `test_decide_sin_mejora_clara_no_hay_ganador_y_marca_al_que_empeora`
- `test_decide_no_depende_de_cuantas_repeticiones_se_promedien` — Regresión: antes se promediaban las predicciones entre repeticiones y DESPUÉS se calculaba la desviación. Un candidato muy inestable (cada repetición falla mucho, pero en promedio acierta) salía como 'mejora' solo por ser un conjunto de modelos, y el veredicto cambiaba con el número de repeticiones.
- `test_la_brecha_relativa_no_premia_solo_a_las_celdas_grandes`
- `test_auc_y_artefacto_de_cartografia`
- `test_conteos_de_foursquare_por_celda`
- `test_zona_mas_cercana`
- `test_la_herramienta_valida_un_objetivo_de_punta_a_punta`
- `test_run_target_devuelve_todo_lo_necesario`
- `test_la_herramienta_sin_foursquare_no_hace_el_contraste`

## `tests/test_normalize_bronze_timestamps.py`

> Pruebas de tools/normalize_bronze_timestamps.py.
>
> Todo ocurre sobre bases temporales: ninguna prueba toca data/mobility.db.

- `test_is_legacy_y_normalize`
- `test_plan_clasifica_cada_fila`
- `test_misma_hora_en_otra_ruta_no_es_gemela`
- `test_base_sin_filas_antiguas_no_necesita_cambios`
- `test_el_ensayo_no_modifica_nada_ni_crea_archivos`
- `test_main_con_base_inexistente_o_sin_tabla`
- `test_aplicar_borra_duplicados_renombra_el_resto_y_deja_un_respaldo`
- `test_aplicar_es_idempotente`
- `test_antes_de_correr_el_pipeline_solo_renombra` — Caso de la base real hoy: filas antiguas sin gemela ISO todavía.
- `test_despues_de_normalizar_reingerir_la_misma_medicion_no_duplica` — El objetivo del script: que correr el pipeline no reinserte las filas antiguas.
- `test_el_indice_unico_sigue_vigente`
- `test_no_toca_otras_tablas`
- `test_si_la_base_esta_en_uso_aborta_sin_cambiar_nada` — Otro proceso (el collector) con una escritura abierta: no se aplica nada.
- `test_si_la_verificacion_falla_se_revierte_todo`
- `test_el_respaldo_se_puede_omitir_solo_por_codigo` — La línea de comandos siempre respalda; `backup=False` existe solo para pruebas.

## `tests/test_operations_status.py`

> Pruebas del estado por ruta del dashboard Operations.
>
> Regresión: el estado salía de `traffic_delay_min` de la última fila, y `_safe()`
> convertía el NULL en 0. ORS no reporta tráfico (el 100% de sus filas lo trae
> NULL), así que cualquier ruta cuya última medición fuera de ORS aparecía como
> "🟢 Free Flow" sin ningún dato detrás.

- `test_ultima_medicion_de_cada_ruta_en_una_consulta`
- `test_no_trae_la_polilinea`
- `test_require_column_trae_la_ultima_fila_que_tiene_ese_dato`
- `test_require_column_omite_las_rutas_que_nunca_tuvieron_ese_dato`
- `test_require_column_rechaza_columnas_inexistentes`
- `test_base_vacia`
- `test_ruta_cuya_ultima_medicion_es_de_ors_usa_la_lectura_de_tomtom`
- `test_ruta_sin_ninguna_lectura_de_trafico_nunca_se_pinta_de_verde` — El bug: la última fila es de ORS (delay NULL) -> antes '🟢 Free Flow'.
- `test_lectura_de_trafico_desactualizada_se_avisa`
- `test_umbrales_de_estado` ×6
- `test_una_fila_por_ruta_con_las_columnas_esperadas`

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

- `test_overpass_run_once_guarda_los_pois_y_escribe_el_heartbeat`
- `test_overpass_run_once_pasa_el_margen_al_cliente`
- `test_overpass_un_segundo_ciclo_actualiza_en_vez_de_duplicar`
- `test_overpass_si_la_descarga_falla_devuelve_0_y_no_toca_nada`
- `test_overpass_heartbeat_contiene_una_fecha_iso_utc`
- `test_overpass_heartbeat_no_rompe_si_no_puede_escribir`
- `test_overpass_main_sin_intervalo_hace_un_ciclo_y_cierra_el_cliente`
- `test_overpass_main_con_intervalo_repite_y_ctrl_c_sale_con_0`
- `test_overpass_main_un_error_fatal_sale_con_1_y_cierra_el_cliente`
- `test_contador_nuevo_empieza_en_las_llamadas_dadas_y_guarda_el_mes`
- `test_contador_acumula_dentro_del_mismo_mes`
- `test_contador_se_reinicia_al_cambiar_de_mes`
- `test_contador_corrupto_se_reinicia_sin_fallar`
- `test_contador_no_rompe_si_no_puede_guardar`
- `test_foursquare_run_once_guarda_los_pois_cuenta_las_llamadas_y_escribe_el_heartbeat`
- `test_foursquare_run_once_pide_zonas_y_rutas_al_cliente`
- `test_foursquare_avisa_al_superar_el_limite_mensual`
- `test_foursquare_no_avisa_si_queda_margen`
- `test_foursquare_heartbeat_no_rompe_si_no_puede_escribir`
- `test_foursquare_main_sin_clave_sale_con_1_sin_crear_el_cliente`
- `test_foursquare_main_con_clave_hace_un_ciclo_y_cierra_el_cliente`
- `test_foursquare_main_con_intervalo_repite_y_ctrl_c_sale_con_0`
- `test_foursquare_main_un_error_fatal_sale_con_1_y_cierra_el_cliente`

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

- `test_prepare_features_devuelve_las_seis_variables_y_el_objetivo`
- `test_prepare_features_acepta_columnas_sin_prefijo_origin`
- `test_prepare_features_rellena_nulos_con_cero`
- `test_prepare_features_sin_una_columna_necesaria_devuelve_vacio` ×4
- `test_prepare_features_con_dataframe_vacio`
- `test_entrena_y_registra_las_features`
- `test_no_entrena_con_pocas_muestras_ni_sin_columnas`
- `test_no_entrena_si_el_objetivo_tiene_nulos` — RandomForest no admite NaN en el objetivo: el error se captura y train() devuelve False.
- `test_predict_devuelve_tiempo_y_confianza_razonables` — Regresión: predict() devolvía SIEMPRE None, porque se le pasaban al escalador columnas con otro nombre (origin_temperature/origin_humidity) que las del ajuste (temperature/humidity) y sklearn lo rechazaba; el except lo ocultaba. El modelo por ruta que documenta el README no producía ninguna predicción.
- `test_predict_responde_a_los_datos_de_entrada` — El modelo aprende la relación: con un tiempo sin tráfico mayor, predice más.
- `test_predict_sin_entrenar_devuelve_none`
- `test_predict_usa_el_historico_como_lag_y_si_falta_el_tiempo_sin_trafico` — `historical_avg or no_traffic_time`: con histórico se usa como lag; con None o 0 (falsy) se usa el tiempo sin tráfico. Se espía la entrada que recibe el escalador.
- `test_el_lag_es_la_media_movil_de_5_valores_del_tiempo_de_viaje` — Documenta cómo se construye hoy `travel_time_min_lag`: media móvil de 5 filas que INCLUYE la fila actual (y las filas llegan de la base ordenadas de más reciente a más antigua). Ver README, limitaciones.
- `test_guardar_y_cargar_reproduce_las_predicciones`
- `test_no_guarda_un_modelo_sin_entrenar_y_carga_falla_con_gracia`
- `test_el_nombre_del_archivo_del_modelo_no_tiene_espacios`
- `test_crea_el_directorio_de_modelos_y_cachea_el_modelo_por_ruta`
- `test_entrena_una_ruta_con_suficientes_datos_y_guarda_el_modelo`
- `test_no_entrena_una_ruta_con_pocas_muestras`
- `test_min_samples_del_predictor_llega_al_modelo` — Regresión: el predictor comprobaba su min_samples pero el modelo usaba su propio mínimo (50), así que con min_samples=30 (como train_models.py) una ruta de 40 muestras fallaba al entrenar.
- `test_train_all_models_devuelve_un_resultado_por_ruta`
- `test_predice_el_tiempo_de_viaje_de_una_ruta_entrenada`
- `test_sin_modelo_entrenado_no_hay_prediccion`
- `test_un_predictor_nuevo_reutiliza_los_modelos_guardados`
- `test_el_estado_de_los_modelos`

## Archivos de apoyo (no contienen tests)

- `tests/conftest.py` — Configuración común de pytest.
