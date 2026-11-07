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

### Qué entrega el asistente: un panorama por celda, no un veredicto

Requisito añadido (6-nov-2026): el modelo no debe mirar solo la competencia directa, sino también el **mercado consumidor** y los **posibles proveedores** de cada celda, para pintar el panorama más útil al usuario final. Como no se puede dar una tasa de certeza, el producto es un **panorama de tres lentes por celda** (competencia, mercado, proveedores), con una **confianza de datos** visible.

**"Lo más positivo para el usuario" se interpreta como "lo más útil y accionable", no como "lo más optimista":**
- Se **empieza por lo favorable** (qué tiene a favor la celda) y se acompaña cada riesgo de una forma de mitigarlo (por ejemplo, "competencia alta pero mercado fuerte: conviene diferenciarse").
- **Nunca se altera un puntaje ni se oculta un riesgo para que la imagen sea mejor.** Un panorama inflado deja al usuario peor informado, y con datos de cobertura desigual sería fácil engañar sin querer. Los riesgos y la confianza de los datos se muestran siempre.

## 2. Auditoría de datos (medida el 6-nov-2026, base real en solo lectura)

| Dato | Hay | Consecuencia |
|---|---|---|
| Etiquetas de éxito | **Ninguna.** Ni ventas ni cierres; `pois_foursquare` solo tiene categoría, nombre y coordenadas (sin calificación, precio ni popularidad) | Ningún modelo supervisado de "éxito" |
| Zonas | 7, con población **estimada** (crecimiento nacional sobre bases de 2014/2019/2021) | Con 7 filas no se entrena nada a nivel de zona |
| POIs Overpass | 3.816 con coordenadas, en **560 celdas** de ~250 m (mediana 3 por celda, máx. 120) | Suficiente para modelos de conteo por celda |
| Celdas con ≥1 POI, por categoría | `business` 461, `food_drink` 246, `school` 104, `hospital` 103, `sport` 52, `leisure` 51, `mall` 19 | **Solo `business` y `food_drink` tienen datos para aprender.** Con ≥3 POIs: `school` 3 celdas, `hospital` 6, `sport` 5, `leisure` 9, `mall` 0 |
| Cercanía a las zonas | 73 % de los POIs a ≤1,5 km de un centro de zona; 12 % a >3 km de todos | La mayor parte del área ya está cubierta por las zonas actuales |
| Demanda fina | **No existe** (población solo por zona) | Señal débil; la población del modelo sería casi una constante por zona |
| Generadores de consumidores ya en `pois` | 266 oficinas (empresas, gobierno, profesionales), 127 colegios, 130 centros de salud (95 farmacias), 83 de ocio, 65 deportivos, 23 centros comerciales | Buena señal de **flujo de gente** para el lente de mercado |
| Lo que **falta** para el mercado | Hoteles y alojamiento turístico, edificios residenciales, paradas de transporte | Sin turismo ni residentes por celda el lente de mercado queda incompleto (Sliema y St Julian's son zonas turísticas) |
| Proveedores ya en `pois` (subcategorías `business`) | 82 supermercados, 41 carnicerías, 31 panaderías, 25 verdulerías, 9 pescaderías, 39 ferreterías, 33 papelerías, 5 droguerías | Sirven como **proveedores minoristas** |
| Proveedores que **faltan** | **1 solo mayorista**; sin charcutería, granjas ni distribuidores; sin zonas industriales o logísticas | El proveedor real de un restaurante o café casi no está cartografiado: el lente de proveedores medirá cercanía a comercio minorista, **no** contratos ni costes logísticos |
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
- **Las tres lentes** (ver la tabla de perfiles de negocio, sección E): cada celda recibe indicadores de **competencia** (directa e indirecta), de **mercado consumidor** (residentes, trabajadores, estudiantes, visitantes y turistas, medidos por los generadores de consumidores cercanos) y de **proveedores** (cercanía y diversidad de los proveedores típicos del tipo de negocio).
- **Control de fuga:** al modelar la categoría X, **X no entra en las variables** (ni en la celda ni en la vecindad). Si no, el modelo solo copiaría la etiqueta.
- *Fase 1b (requiere autorización aparte, la actual cubre solo la sonda):* edificios residenciales y paradas de transporte de OSM como señal de demanda fina. Sin esto, las "brechas" pueden caer en celdas sin gente (mar, industria).

### B. Modelo de oferta esperada (núcleo)
- **Objetivo:** número de locales de la categoría en la celda (solo `food_drink` y `business`).
- **Modelos:** (1) `HistGradientBoostingRegressor(loss="poisson")`; (2) **red neuronal MLP** (`MLPRegressor`, sobre log(1+conteo)).
- **Salida:** `brecha = esperado − observado` por celda, con incertidumbre (conjunto de modelos con semillas/bootstrap). Las otras cinco categorías **siguen con el MCDA actual**: no hay datos para aprender.
- **Puntaje final** (se mantiene explicable): suma ponderada de `brecha`, demanda y accesibilidad, con el desglose siempre visible, como ahora. Los pesos pasan a ser ajustables y a mostrarse con sensibilidad (cuánto cambia el ranking al moverlos).
- **Honestidad sobre la red neuronal:** con ~560 celdas, lo esperable es que el boosting iguale o supere al MLP. El valor para el TFM es la **comparación medida**, no una promesa de que la red gane. Regla fijada de antemano: **se publica el modelo que gane en validación; si el MLP no gana, se usa el boosting** y se documenta.
- **Dependencia:** `scikit-learn` ya está en `requirements.txt` (versión 1.9 local; incluye MLP). **No hay `torch` ni `tensorflow`** instalados; no se añaden salvo que se demuestre que la pérdida de Poisson en una red propia mejora de forma clara (decisión pendiente).

#### Cómo entran el mercado y los proveedores en el modelo (aprendido frente a regla)

- **Aprendido:** el modelo de oferta esperada recibe como variables los generadores de consumidores y los proveedores cercanos. Su **importancia aprendida** dice cuánto acompañan al negocio existente (por ejemplo, cuánto se agrupan los restaurantes cerca de oficinas): es un peso estimado de los datos, no una opinión.
- **Explícito:** además, los tres lentes se muestran **por separado** en el panorama, con sus indicadores crudos. Sin etiquetas de éxito, el modelo **no puede aprender cuánto vale** un buen mercado o un proveedor cercano para el negocio; por eso el puntaje combinado usa pesos visibles y ajustables, con la sensibilidad del ranking a cada peso.
- **Advertencia sobre proveedores:** Malta es pequeña (distancias de pocos kilómetros), así que **es posible que la cercanía a proveedores casi no varíe entre celdas** y el lente discrimine poco. Se mide en la fase 0 (varianza entre celdas); si no discrimina, se muestra como información y se le quita peso, en vez de fingir que ayuda a decidir.

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

### E. Perfiles de negocio: qué cuenta como competencia, mercado y proveedor

Una tabla de conocimiento (`src/ml/business_profiles.py`, revisable por una persona) que, para cada tipo de negocio, dice qué etiquetas de OSM son cada cosa. Sin ella no se puede calcular ninguna lente. Ejemplo (borrador, **a validar**):

| Tipo | Competencia directa | Competencia indirecta (sustitutos) | Generadores de mercado | Proveedores típicos |
|---|---|---|---|---|
| Restaurante / café (`food_drink`) | otros `food_drink` | supermercados con comida preparada, panaderías | oficinas, colegios, hoteles, ocio, residentes | mayoristas, carnicerías, pescaderías, verdulerías, panaderías, bebidas |
| Panadería / pastelería | panaderías, pastelerías | supermercados | residentes, oficinas, colegios | mayoristas, alimentación |
| Farmacia (`hospital`) | farmacias | droguerías, supermercados | centros de salud, residentes, oficinas | distribuidores sanitarios (casi sin datos) |
| Gimnasio (`sport`) | gimnasios y centros deportivos | — | oficinas, residentes, colegios | proveedores de equipamiento (casi sin datos) |
| Comercio (`business`, por subcategoría) | misma subcategoría | subcategorías afines | residentes, oficinas, ocio, turismo | mayoristas del sector |

Lo que ya hay **no basta** para todos los tipos: donde los proveedores casi no están cartografiados (mayoristas, distribuidores sanitarios) el lente se marca como "sin datos suficientes" y no se inventa.

### Confianza de datos por celda
Cada panorama lleva una **confianza** visible: cuántas de las tres lentes tienen datos reales, qué categoría de OSM es poco fiable en esa zona (por ejemplo, `food_drink` se ve en torno al 61 % frente a Foursquare) y cuántos POIs sustentan cada indicador. Una celda con poca información no se presenta con la misma seguridad que una bien cubierta.

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
| 0 | Rejilla y variables (`src/ml/`), con tests y control de fuga; **perfiles de negocio** (sección E) y los indicadores de las tres lentes con los datos que ya hay; medición de cuánto varía cada lente entre celdas | — |
| 1 | Modelos de oferta (boosting y MLP) + `tools/validate_location_model.py` (validación espacial reproducible, como `validate_forecast.py`) y resultados en el README | 0 |
| 1b | Edificios residenciales, paradas de transporte, **hoteles y alojamiento turístico**, mayoristas y zonas industriales/logísticas (mercado y proveedores finos) | **autorización de descarga a Overpass** |
| 2 | Tabla precalculada de **panoramas por celda** (tres lentes + confianza) + mapa de calor y ficha por celda en Recomendación; el MCDA se conserva como respaldo y para las otras 5 categorías | 1 |
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
5. ¿Quién **valida la tabla de perfiles de negocio** (sección E): qué es competencia, mercado y proveedor para cada tipo? Es conocimiento del dominio, no se deduce de los datos; yo propongo un borrador y alguien con criterio de negocio lo corrige.
6. ¿Se acepta la interpretación de **"lo más positivo"** como "lo más útil y accionable" (empezar por lo favorable y mostrar siempre los riesgos), y no como un puntaje inflado?
