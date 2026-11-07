# Diseño: machine learning y redes neuronales para el asistente de recomendación de ubicación

**Estado:** borrador para discusión (6-nov-2026). Nada de esto está implementado todavía.
**Decisiones ya tomadas:** el asistente pasa a recomendar por **celdas de ~250 m** (no solo las 7 zonas), y la ampliación de datos con Overpass se hace **primero con una prueba pequeña** (hecha, resultados en la sección 2).

## 1. Qué problema se quiere resolver, y qué NO se puede afirmar

Hoy (`src/location_scoring.py`) el asistente puntúa las 7 zonas con una suma ponderada (MCDA) de demanda, competencia y accesibilidad. Es explicable, pero los pesos (0,40 / 0,35 / 0,25) son una opinión, no se aprenden de nada.

**Límite de fondo:** no existe ningún dato de *resultado de negocio* (ventas, rentabilidad, cierres confirmados). Por tanto **ningún modelo de este diseño puede afirmar que una ubicación será rentable.** Lo que sí se puede aprender con los datos que hay:

| Se puede aprender | No se puede afirmar |
|---|---|
| Dónde hay **menos negocios de una categoría de los que el contexto sugeriría** (brecha de oferta) | Que abrir ahí sea rentable |
| Qué contexto (otras categorías, accesibilidad, densidad) acompaña a cada categoría | Causalidad (ver `causal_analysis`: es asociación) |
| Una señal **débil y ruidosa** de supervivencia (fase 4, exploratoria) | Una tasa de cierre real |

La redacción del TFM debe decir "brecha de oferta" y "señal exploratoria", no "mejor ubicación".

## 2. Auditoría de datos (medida el 6-nov-2026, base real en solo lectura)

| Dato | Hay | Consecuencia |
|---|---|---|
| Etiquetas de éxito | **Ninguna.** Ni ventas ni cierres; `pois_foursquare` solo tiene categoría, nombre y coordenadas (sin calificación, precio ni popularidad) | Ningún modelo supervisado de "éxito" |
| Zonas | 7, con población **estimada** (crecimiento nacional sobre bases de 2014/2019/2021) | Con 7 filas no se entrena nada a nivel de zona |
| POIs Overpass | 3.816 con coordenadas, en **560 celdas** de ~250 m (mediana 3 por celda, máx. 120) | Suficiente para modelos de conteo por celda |
| Celdas con ≥1 POI, por categoría | `business` 461, `food_drink` 246, `school` 104, `hospital` 103, `sport` 52, `leisure` 51, `mall` 19 | **Solo `business` y `food_drink` tienen datos para aprender.** Con ≥3 POIs: `school` 3 celdas, `hospital` 6, `sport` 5, `leisure` 9, `mall` 0 |
| Cercanía a las zonas | 73 % de los POIs a ≤1,5 km de un centro de zona; 12 % a >3 km de todos | La mayor parte del área ya está cubierta por las zonas actuales |
| Demanda fina | **No existe** (población solo por zona) | Señal débil; la población del modelo sería casi una constante por zona |
| Tráfico | 12 rutas entre centros de zona | Accesibilidad solo a nivel de zona, no de celda |

### Prueba de etiquetas de supervivencia (Overpass, histórico del mapa)

Una zona (Msida–Gzira–Sliema, ~4×3 km), solo `food_drink`, 4 consultas, nada guardado en la base:

| Snapshot | Locales | Siguen hoy (mismo id) | Ya no están | Cierres plausibles* | Marcados `disused:`/`was:` hoy |
|---|---|---|---|---|---|
| 1-ene-2022 | 477 | 80 % | 96 (20 %) | **76 (16 %)** | 13 |
| 1-ene-2024 | 533 | 83 % | 92 (17 %) | 74 (14 %) | 15 |
| Hoy | 724 | — | — | — | 16 |

\* Con nombre y sin otro elemento del mismo nombre a ≤60 m hoy (descarta re-mapeos y reetiquetados: 18 casos).

**Lo que dice la prueba:**
- El histórico **sí es consultable** y da candidatos a cierre reconocibles (por ejemplo, locales de cadena que ya no figuran).
- **Es ruidoso:** de los 76 cierres plausibles, **20 (26 %) aparecen hoy en Foursquare** con el mismo nombre a ≤150 m, es decir, probablemente siguen abiertos (aunque Foursquare también arrastra fichas obsoletas, y solo cubre el 15 % de los locales de OSM, así que el contraste es parcial). Quedan **56 probables** y **12 con marca explícita de cierre**.
- **El mapa creció un 52 % desde 2022** (477 → 724): casi todo es mejor cartografía, no negocios nuevos. Por eso **no se pueden interpretar los "nuevos" como aperturas**, y los negocios de 2022 son los más visibles (sesgo de supervivencia en la propia muestra).
- Extrapolando a toda el área: del orden de **100-200 eventos de cierre** (de los cuales muy pocos con marca explícita). Es poco y ruidoso: sirve para una señal **exploratoria**, no para el núcleo del asistente.

## 3. Arquitectura propuesta

```
texto libre ──► [C] clasificador de texto ──► categoría ─┐
                                                          ▼
 POIs, zonas, tráfico ──► [A] rejilla 250 m + features ──► [B] modelo de oferta esperada ──► brecha por celda ─┐
                                                                                                              ├─► puntaje explicable ──► mapa de calor
                                              [D] riesgo de cierre (exploratorio, opcional) ───────────────────┘
```

Todo el entrenamiento se hace **fuera del dashboard** (scripts en `tools/`), y el dashboard solo lee una **tabla precalculada de puntajes por celda**. Así el contenedor del dashboard (límite de 1 GiB) no carga modelos pesados ni nuevas dependencias.

### A. Rejilla y variables (`src/ml/` — nuevo)
- Rejilla de ~250 m sobre el área de los POIs (unas 1.700 celdas en total, **estimado** como 38×45 sobre la extensión de los POIs; **560 con POIs, medido**).
- Variables por celda: conteos por categoría en la celda y en la vecindad (anillos de 1 y 2 celdas), distancia al centro de zona más cercano, población de zona suavizada con un núcleo (kernel), accesibilidad de la zona más cercana.
- **Control de fuga:** al modelar la categoría X, **X no entra en las variables** (ni en la celda ni en la vecindad). Si no, el modelo solo copiaría la etiqueta.
- *Fase 1b (requiere autorización aparte, la actual cubre solo la sonda):* edificios residenciales y paradas de transporte de OSM como señal de demanda fina. Sin esto, las "brechas" pueden caer en celdas sin gente (mar, industria).

### B. Modelo de oferta esperada (núcleo)
- **Objetivo:** número de locales de la categoría en la celda (solo `food_drink` y `business`).
- **Modelos:** (1) `HistGradientBoostingRegressor(loss="poisson")`; (2) **red neuronal MLP** (`MLPRegressor`, sobre log(1+conteo)).
- **Salida:** `brecha = esperado − observado` por celda, con incertidumbre (conjunto de modelos con semillas/bootstrap). Las otras cinco categorías **siguen con el MCDA actual**: no hay datos para aprender.
- **Puntaje final** (se mantiene explicable): suma ponderada de `brecha`, demanda y accesibilidad, con el desglose siempre visible, como ahora. Los pesos pasan a ser ajustables y a mostrarse con sensibilidad (cuánto cambia el ranking al moverlos).
- **Honestidad sobre la red neuronal:** con ~560 celdas, lo esperable es que el boosting iguale o supere al MLP. El valor para el TFM es la **comparación medida**, no una promesa de que la red gane. Regla fijada de antemano: **se publica el modelo que gane en validación; si el MLP no gana, se usa el boosting** y se documenta.
- **Dependencia:** `scikit-learn` ya está en `requirements.txt` (versión 1.9 local; incluye MLP). **No hay `torch` ni `tensorflow`** instalados; no se añaden salvo que se demuestre que la pérdida de Poisson en una red propia mejora de forma clara (decisión pendiente).

### C. Clasificador de texto (tipo de negocio)
- **Hoy:** 140 palabras clave con límites de palabra; si no hay coincidencia, lanza error (no adivina). Es correcto, pero rígido ante sinónimos, errores de ortografía y frases largas.
- **Candidatos:** (1) TF-IDF de n-gramas de caracteres + regresión logística (robusto a erratas, sin dependencias nuevas); (2) un MLP sobre esas mismas variables.
- **Conserva la abstención:** por debajo de un umbral de confianza no elige categoría y lo dice (comportamiento actual, que se quiere mantener).
- **Evaluación:** conjunto reservado de ~200 frases escritas a mano (sinónimos, erratas, frases largas, casos fuera de vocabulario), contra el método de palabras clave. No se entrena con las propias palabras clave para evaluar.
- **Realismo:** con 7 categorías y pocas frases, un método de n-gramas probablemente iguale a una red. Se mide y se decide con la misma regla.

### D. Riesgo de cierre (exploratorio, fase 4)
- Etiquetas por niveles de confianza: **fuerte** (marca `disused:`/`was:`), **probable** (desaparece, con nombre, sin reemplazo y sin rastro en Foursquare), **dudosa** (el resto, no se usa).
- Clasificador (boosting) con validación espacial. Se informa con **sensibilidad al ruido**: solo fuertes vs fuertes+probables.
- **Solo entra en el asistente si su AUC en validación espacial excluye 0,5 con intervalo de confianza**; si no, queda como hallazgo del TFM.

## 4. Protocolo de validación (fijado antes de entrenar)

1. **Validación cruzada espacial por bloques** (bloques de ~1 km, `GroupKFold`, repetida): evita que celdas vecinas, que se parecen, inflen la métrica. La validación al azar daría números falsamente buenos.
2. **Métricas:** desviación de Poisson, correlación de Spearman entre conteo predicho y observado en bloques reservados, y acierto en las k celdas mejor clasificadas.
3. **Líneas base** que el ML debe superar: media constante; solo distancia al centro; solo población; y el MCDA actual convertido en predictor de la misma etiqueta.
4. **Criterio de éxito:** el ML mejora a la mejor línea base en la desviación de Poisson, con el intervalo de las repeticiones separado del de la línea base. **Si no, no se publica el puntaje de ML y se queda el MCDA** (resultado válido para el TFM).
5. **Contraste independiente:** el modelo se entrena **solo con OSM** y se evalúa contra los locales de **Foursquare** (411 restaurantes): ¿caen en celdas con más oferta esperada que otras? Foursquare cubre solo el 15 % de lo que ve OSM, así que es un contraste parcial.
6. **Revisión de cordura:** las mayores brechas no deben caer en celdas sin edificios ni población (mar, zonas industriales). Es el motivo de la fase 1b.

## 5. Fases (un PR por fase, como hasta ahora)

| Fase | Entregable | Depende de |
|---|---|---|
| 0 | Rejilla y variables (`src/ml/`), con tests y control de fuga | — |
| 1 | Modelos de oferta (boosting y MLP) + `tools/validate_location_model.py` (validación espacial reproducible, como `validate_forecast.py`) y resultados en el README | 0 |
| 1b | Edificios residenciales y paradas de transporte | **autorización de descarga a Overpass** |
| 2 | Tabla precalculada de puntajes por celda + mapa de calor en Recomendación; el MCDA se conserva como respaldo y para las otras 5 categorías | 1 |
| 3 | Clasificador de texto, comparado con las palabras clave | — |
| 4 | Riesgo de cierre exploratorio (etiquetas de Overpass histórico de toda el área) | 0, **autorización de descarga** |

## 6. Riesgos y sesgos que hay que declarar en el TFM

- **Presencia ≠ éxito:** el modelo aprende dónde *hay* negocios, no dónde *prosperan*. La "brecha" supone un equilibrio de mercado que no se ha comprobado.
- **Cobertura de OSM desigual:** `food_drink` está medido en ~61 % frente a Foursquare, y el mapa creció un 52 % desde 2022. Zonas peor cartografiadas parecerán "con brecha".
- **Demanda débil:** población estimada y solo por zona hasta que haya señal de edificios (fase 1b).
- **Muestra pequeña:** 560 celdas y dos categorías con datos suficientes. Los intervalos serán anchos; hay que mostrarlos.
- **Etiquetas de cierre ruidosas:** 26 % de los "cierres plausibles" parece seguir abierto en la prueba.

## 7. Decisiones pendientes

1. ¿Se autoriza la **descarga completa** de edificios, paradas y estado histórico de toda el área (fases 1b y 4)? La autorización actual cubrió solo la sonda.
2. ¿Se añade **`torch`** (solo para entrenar, no en el dashboard) si el MLP de scikit-learn se queda corto, o se limita el trabajo a scikit-learn?
3. ¿Se acepta el **criterio de éxito** de la sección 4 (publicar el ML solo si gana en validación espacial)?
4. ¿Quién escribe las **~200 frases de evaluación** del clasificador de texto? Idealmente alguien que conozca el lenguaje real de los usuarios; yo puedo proponer un borrador.
