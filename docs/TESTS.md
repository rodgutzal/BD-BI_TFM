# Catálogo de tests

> **Archivo generado automáticamente. No editar a mano.** Se deriva del código de `tests/` con
> `python tools/generate_tests_doc.py`; el CI (`tests/test_tests_documentation.py`) falla si
> está desactualizado. Para añadir un test: escríbelo con un nombre y un docstring descriptivos,
> añade su archivo a la tabla de la sección *Tests* del README (si es un archivo nuevo) y
> regenera este catálogo.

**26 archivos · 240 funciones de test · 280 casos** (un caso es una ejecución: un test parametrizado genera varios).

| Archivo | Funciones | Casos |
|---|---:|---:|
| [`tests/test_analyst_quality.py`](#teststest_analyst_qualitypy) | 6 | 6 |
| [`tests/test_analytics.py`](#teststest_analyticspy) | 3 | 3 |
| [`tests/test_api.py`](#teststest_apipy) | 12 | 18 |
| [`tests/test_business_type_classifier.py`](#teststest_business_type_classifierpy) | 7 | 20 |
| [`tests/test_check_collection_gaps.py`](#teststest_check_collection_gapspy) | 10 | 10 |
| [`tests/test_config.py`](#teststest_configpy) | 4 | 4 |
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
| [`tests/test_normalize_bronze_timestamps.py`](#teststest_normalize_bronze_timestampspy) | 15 | 15 |
| [`tests/test_operations_status.py`](#teststest_operations_statuspy) | 11 | 16 |
| [`tests/test_ors_null_fields.py`](#teststest_ors_null_fieldspy) | 2 | 2 |
| [`tests/test_predictive_modeling_dashboard.py`](#teststest_predictive_modeling_dashboardpy) | 7 | 7 |
| [`tests/test_predictive_modeling_ondemand.py`](#teststest_predictive_modeling_ondemandpy) | 6 | 6 |
| [`tests/test_query_measurements_polyline.py`](#teststest_query_measurements_polylinepy) | 8 | 8 |
| [`tests/test_recommendation_dashboard.py`](#teststest_recommendation_dashboardpy) | 6 | 6 |
| [`tests/test_tests_documentation.py`](#teststest_tests_documentationpy) | 9 | 9 |
| [`tests/test_time_series.py`](#teststest_time_seriespy) | 10 | 10 |

## `tests/test_analyst_quality.py`

> Pruebas de Analyst: abrir la pantalla usa UN perfil de la base y no las consultas caras de antes.
>
> Regresión (medido en el bind mount de Windows de Docker, donde cada recorrido de la tabla cuesta ~8 s):
>   - `get_available_routes()` (un SELECT DISTINCT que recorre toda la tabla) se llamaba 4 veces;
>   - la completitud por ruta hacía 12 consultas (33 s);
>   - "Missing Values" cargaba 100 mil filas en un DataFrame (15 s);
>   - `get_all_routes_statistics()` recorría la tabla otra vez solo para contar filas por ruta.
> Todo eso sale ahora de `get_data_profile()`, una sola pasada.

- `test_abrir_analyst_no_usa_las_consultas_caras`
- `test_ninguna_consulta_carga_la_base_entera` — 'Missing Values' ya no carga 100 mil filas: toda lectura de filas es de UNA ruta.
- `test_las_metricas_de_calidad_son_las_del_perfil`
- `test_la_completitud_por_ruta_sale_del_perfil_y_cubre_todas_las_rutas`
- `test_las_muestras_por_ruta_de_model_performance_son_las_filas_reales`
- `test_el_panel_lateral_usa_el_ultimo_timestamp_y_no_el_resumen_completo` — app.py pedía get_database_summary() (con el DISTINCT de rutas) solo para la hora del último dato.

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
- `test_time_series_patrones`
- `test_predict_devuelve_json_serializable_y_modelos_entrenados` — De punta a punta: entrena el ensemble con los datos y responde. Cubre también que el resultado se serialice (antes `model_predictions` se apuntaba a sí mismo).

## `tests/test_business_type_classifier.py`

> Pruebas del clasificador de texto libre -> categoría de Overpass.

- `test_clasifica_negocios_comunes` ×10
- `test_barberia_no_se_confunde_con_bar` — Regresión: la palabra clave "bar" (comida y bebida) no debe matchear dentro de "barbería". Es el bug que ya ocurrió una vez con datos reales de Foursquare, y el clasificador usa límites de palabra (\b) para evitarlo.
- `test_ignora_mayusculas_tildes_y_espacios_de_mas`
- `test_sin_coincidencia_devuelve_none_y_nunca_adivina` ×5
- `test_todas_las_categorias_existen_en_overpass` — El clasificador solo puede devolver categorías que realmente guarda la tabla `pois` (CATEGORY_TAGS de poi_client.py).
- `test_ninguna_palabra_clave_choca_con_otra_categoria` — Una misma palabra no puede aparecer en dos categorías (el orden de las reglas decidiría en silencio), y ninguna palabra de una categoría puede estar contenida como palabra completa dentro de una frase de otra.
- `test_cantidad_de_palabras_clave_documentada` — El README dice 140 palabras clave (únicas).

## `tests/test_check_collection_gaps.py`

> Pruebas de tools/check_collection_gaps.py (detección de huecos de recolección).

- `test_find_gaps_detecta_solo_pausas_mayores_al_umbral`
- `test_find_gaps_sin_huecos`
- `test_find_gaps_ignora_duplicados_y_orden`
- `test_find_gaps_con_menos_de_dos_instantes`
- `test_fmt_h`
- `test_load_cycle_times_filtra_por_fecha_y_descarta_timestamps_invalidos`
- `test_load_cycle_times_es_de_solo_lectura`
- `test_report_avisa_si_ahora_mismo_no_llega_trafico`
- `test_report_mide_el_tiempo_total_sin_datos`
- `test_report_sin_datos`

## `tests/test_config.py`

> Pruebas para el módulo de configuración (BD_BI_TFM: selección de fuente de datos).

- `test_get_data_source_default` — Sin DATA_SOURCE definido, debe usar 'ors' por defecto.
- `test_get_data_source_tomtom` — Con DATA_SOURCE=tomtom en el entorno, debe respetarlo.
- `test_get_data_source_invalid` — Un valor inválido debe lanzar RuntimeError.
- `test_get_timescale_config_defaults` — Sin variables PG* definidas, deben usarse los valores de docker-compose.yml.

## `tests/test_data_profile.py`

> Pruebas del perfil de calidad de la base en UNA pasada (RouteDatabase.get_data_profile).
>
> Regresión: Analyst hacía más de diez consultas al abrirse (rutas únicas ×4, una consulta por ruta
> para la completitud, un resumen completo, 100 mil filas cargadas...). Cada recorrido de la tabla
> cuesta ~8 s en el bind mount de Windows de Docker (décimas de segundo en el host), así que sumaban
> ~87 s. Un único perfil agregado da todo eso en un recorrido.

- `test_totales_y_rutas`
- `test_fechas_primera_y_ultima`
- `test_los_nulos_coinciden_con_un_calculo_independiente_en_pandas`
- `test_completitud_por_ruta`
- `test_id_polyline_y_created_at_no_son_columnas_de_medicion`
- `test_una_polilinea_nula_no_cuenta_como_dato_faltante` — Las filas históricas de TomTom no tienen polyline: eso no debe bajar la completitud.
- `test_base_vacia`
- `test_cuenta_duplicados_de_ruta_instante_y_fuente` — La clave UNIQUE de la tabla real los impide; se prueba con una tabla SIN la restricción.
- `test_en_la_tabla_real_no_hay_duplicados`
- `test_el_perfil_hace_una_sola_consulta_sobre_la_tabla`
- `test_ultimo_timestamp`
- `test_ultimo_timestamp_de_base_vacia`
- `test_resumen_sin_rutas_omite_solo_las_rutas_unicas`
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
- `test_promedio_diario_cubre_toda_la_ventana`
- `test_promedio_diario_respeta_la_ventana`
- `test_promedio_diario_calcula_bien_el_promedio`
- `test_promedio_diario_base_vacia`
- `test_promedio_por_ruta_y_hora`
- `test_promedio_por_ruta_y_hora_no_pierde_filas_con_mucha_data`
- `test_columnas_numericas_excluyen_el_id_y_el_texto`
- `test_query_columns_trae_solo_lo_pedido_sin_limit`
- `test_query_columns_rechaza_columnas_que_no_existen`
- `test_query_columns_no_permite_inyeccion_sql`
- `test_query_columns_sin_columnas`

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
- `test_mae_ignora_las_posiciones_sin_dato`
- `test_los_cortes_exigen_horizonte_y_pasado_con_datos`
- `test_las_referencias_no_usan_datos_del_futuro` — Cambiar los valores a partir del corte no debe alterar ninguna referencia.
- `test_la_validacion_compara_con_las_referencias` — evaluate + summarize: con un ciclo diario limpio el perfil y el SARIMA ganan a media y persistencia.
- `test_la_validacion_lee_la_base_en_solo_lectura` — load_hourly_share abre la base con immutable=1: no crea -wal/-shm ni modifica el archivo.

## `tests/test_foursquare_client.py`

> Pruebas de la categorización y de los puntos de búsqueda de Foursquare.
>
> No hacen llamadas de red: solo ejercitan la lógica pura del cliente.

- `test_categoriza_nombres_reales_de_foursquare` ×17
- `test_barbershop_no_se_confunde_con_bar` — Regresión: "bar" dentro de "Barbershop" no puede mandarlo a restaurant (se usa \b, no un simple `in`).
- `test_nunca_descarta_un_poi_sin_categoria`
- `test_sin_rutas_solo_devuelve_las_zonas`
- `test_con_las_rutas_actuales_son_27_llamadas` — El README documenta 7 zonas + 20 puntos intermedios = 27 llamadas por refresco (~117/mes con refresco semanal, 23% del límite gratis).
- `test_no_duplica_corredores_en_sentido_inverso` — Valletta->Birkirkara y Birkirkara->Valletta son el mismo tramo físico.
- `test_puntos_intermedios_quedan_entre_origen_y_destino`
- `test_ignora_rutas_con_zonas_desconocidas`
- `test_acepta_la_forma_nueva_de_la_respuesta`
- `test_acepta_la_forma_antigua_con_geocodes`
- `test_descarta_lugares_sin_id_o_sin_coordenadas`
- `test_cliente_exige_api_key`

## `tests/test_hybrid_scheduler.py`

> Pruebas para HybridScheduler: cada fuente debe dispararse en su propio
> intervalo, sin interferir con la otra, y Ctrl+C debe cerrar ambos clientes.

- `test_ors_and_tomtom_fire_on_independent_schedules` — Con 15/27 min en 120 min simulados: ORS 9 veces, TomTom 5 veces.
- `test_both_sources_fire_immediately_on_first_tick` — En el minuto 0 (last_run=None), ambas fuentes deben disparar de inmediato.
- `test_signal_handler_closes_both_collectors` — Ctrl+C debe cerrar traffic_client y weather de AMBOS collectors.

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

## `tests/test_predictive_modeling_dashboard.py`

> Pruebas de la preparación de datos del dashboard de modelado predictivo.
>
> Regresión: con datos reales, unas pocas filas (OpenWeather falló en ese ciclo)
> tienen el clima en NULL, y una sola basta para que `LogisticRegression` lance
> `Input X contains NaN`. Esa excepción cortaba toda la vista Analyst.

- `test_clima_ausente_no_se_convierte_en_lluvia`
- `test_descripciones_conocidas_y_desconocidas_se_agrupan_como_antes`
- `test_complete_cases_excluye_solo_las_filas_sin_clima`
- `test_sin_filas_incompletas_no_se_pierde_nada`
- `test_regresion_no_falla_con_filas_sin_clima`
- `test_clasificacion_no_falla_con_filas_sin_clima` — El caso exacto del bug: 'Input X contains NaN' en LogisticRegression.
- `test_el_temporal_y_el_clustering_conservan_las_filas_sin_clima` — Su tiempo de viaje es válido: no deben pasar por _complete_cases.

## `tests/test_predictive_modeling_ondemand.py`

> Pruebas del modelado predictivo BAJO DEMANDA del dashboard.
>
> Regresión: Streamlit ejecuta el contenido de TODAS las pestañas en cada rerun, así que los
> cuatro modelos se entrenaban de golpe al abrir Analyst (con la base real: ~75 s con 16 CPUs y
> ~9 min dentro del contenedor del dashboard, de 1 CPU y 1 GiB, donde además rozaba el límite de
> memoria). Ahora se entrena solo lo que el usuario pide.

- `test_las_secciones_coinciden_con_los_modelos`
- `test_al_abrir_no_se_entrena_nada`
- `test_pulsar_un_boton_entrena_solo_esa_seccion`
- `test_lo_pedido_se_mantiene_en_la_sesion`
- `test_el_boton_de_todos_entrena_las_cuatro_secciones`
- `test_el_forecast_temporal_funciona_con_low_memory` — El SARIMA usa fit(low_memory=True): se comprueba que el pronóstico y su intervalo se pueden obtener (sin resultados suavizados ni predicción en muestra, que low_memory no ofrece), y que la pantalla muestra la referencia y la nota de validación.

## `tests/test_query_measurements_polyline.py`

> Pruebas de `include_polyline` en RouteDatabase.query_measurements.
>
> Regresión: query_measurements hacía `SELECT *` e incluía `polyline` (el JSON de la
> geometría de la ruta, ~4,5 KB por fila). En la base real eso es el 93% del tamaño en
> memoria de la tabla (339 de 365 MB con 78.561 filas) y, repetido por cada pestaña y por
> la caché de Streamlit, agotaba el límite de 1 GiB del contenedor del dashboard al abrir
> Analyst (el proceso moría por falta de memoria).

- `test_por_defecto_no_carga_la_polilinea`
- `test_include_polyline_la_devuelve_intacta`
- `test_las_demas_columnas_son_exactamente_las_mismas` — Sin polyline tampoco se lee created_at (va después de polyline y leerla recorre las páginas de desbordamiento de todas las filas); el resto de columnas no cambia.
- `test_por_defecto_tampoco_lee_created_at_pero_con_include_polyline_si`
- `test_los_filtros_y_el_orden_no_cambian`
- `test_sin_la_polilinea_la_memoria_baja_mucho` — No es una cifra mágica: con polilíneas de ~12 KB, cargarlas pesa >10× lo que pesa el resto.
- `test_base_vacia_no_falla`
- `test_export_route_data_conserva_la_polilinea` — La exportación por ruta no cambia: sigue incluyendo la geometría.

## `tests/test_recommendation_dashboard.py`

> Pruebas de la tabla de resultados del dashboard de Recomendación.
>
> El README promete que el desglose muestra cada dimensión CRUDA y NORMALIZADA
> ("nunca solo el número final"). Esto lo verifica sin abrir Streamlit.

- `test_la_tabla_muestra_cada_factor_crudo_y_normalizado`
- `test_las_columnas_normalizadas_estan_entre_0_y_1`
- `test_mas_alto_siempre_es_mejor_en_las_tres_columnas` — La zona con más competencia tiene el menor 'Baja competencia'.
- `test_el_puntaje_es_la_suma_ponderada_de_las_columnas_mostradas` — Lo que dice el pie de la tabla: Puntaje = suma ponderada de las tres columnas (0-1), con 0.5 donde falta el dato.
- `test_una_zona_sin_dato_queda_en_blanco_y_se_nota`
- `test_normalize_weights_conserva_proporciones_y_suma_uno`

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

- `test_el_catalogo_de_tests_esta_al_dia`
- `test_el_catalogo_menciona_cada_funcion_de_test` — Ninguna función `test_*` puede faltar en el catálogo (aunque el resto del texto cambie).
- `test_todo_archivo_de_test_esta_en_la_tabla_del_readme`
- `test_la_tabla_del_readme_no_cita_archivos_que_ya_no_existen`
- `test_parametrize_con_literales_cuenta_los_casos`
- `test_parametrize_apilado_multiplica`
- `test_parametrize_con_valores_no_literales_no_se_puede_contar`
- `test_sin_parametrize_es_un_caso`
- `test_el_generador_encuentra_funciones_y_metodos_de_clases_test`

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

## Archivos de apoyo (no contienen tests)

- `tests/conftest.py` — Configuración común de pytest.
