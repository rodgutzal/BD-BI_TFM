# Diseño: machine learning y redes neuronales para el asistente de recomendación de ubicación

**Estado:** borrador para discusión (6-nov-2026). Nada de esto está implementado todavía.
**Decisiones ya tomadas:**
- El asistente pasa a recomendar por **celdas de ~250 m** (no solo las 7 zonas).
- La ampliación de datos con Overpass se hace **primero con una prueba pequeña** (hecha, resultados en la sección 2).
- El producto es un **panorama de tres lentes por celda** (competencia, mercado consumidor y proveedores), y "lo más positivo para el usuario" significa **lo más útil y accionable**, no un puntaje inflado (confirmado el 6-nov-2026).
- Los **perfiles de negocio son ajustables por el usuario** sobre valores por defecto revisados (sección E, 7-nov-2026).
- Fase 1b autorizada con descarga a **archivos temporales** (sin tocar la base de datos): hecha y evaluada (sección 3.H, 8-nov-2026).
- En la fase 2 la **brecha de oferta se mostrará como indicador exploratorio**, claramente etiquetado como no validado y fuera del puntaje combinado (8-nov-2026).

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

Todo el entrenamiento se hace **fuera del dashboard** (scripts en `tools/`) y, preferentemente, **en otra máquina** (sección 3.I), y el dashboard solo lee una **tabla precalculada de puntajes por celda**. Así el contenedor del dashboard (límite de 1 GiB) no carga modelos pesados ni nuevas dependencias.

### A. Rejilla y variables (`src/ml/` — nuevo)
- Rejilla fija de ~250 m (`src/ml/grid.py`): **45 × 51 = 2.295 celdas, de las que 1.139 están activas** (con algún POI en la celda o en su vecindad inmediata) y **560 contienen POIs**. Todo medido en la fase 0.
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
- **Advertencia sobre proveedores (medida en la fase 0, ver la sección 3.F):** la hipótesis era que la cercanía a proveedores casi no variaría entre celdas por el tamaño de Malta. **Resultó falsa**: varía mucho. El problema real es otro: las tres lentes están muy correlacionadas entre sí porque miden sobre todo cuán urbana es la celda.

### C. Clasificador de texto (tipo de negocio)
- **Hoy:** 140 palabras clave con límites de palabra; si no hay coincidencia, lanza error (no adivina). Es correcto, pero rígido ante sinónimos, errores de ortografía y frases largas.
- **Candidatos:** (1) TF-IDF de n-gramas de caracteres + regresión logística (robusto a erratas, sin dependencias nuevas); (2) un MLP sobre esas mismas variables.
- **Conserva la abstención:** por debajo de un umbral de confianza no elige categoría y lo dice (comportamiento actual, que se quiere mantener).
- **Evaluación:** conjunto reservado de ~200 frases escritas a mano (sinónimos, erratas, frases largas, casos fuera de vocabulario), contra el método de palabras clave. No se entrena con las propias palabras clave para evaluar.
- **Realismo:** con 7 categorías y pocas frases, un método de n-gramas probablemente iguale a una red. Se mide y se decide con la misma regla.

### D. Riesgo de cierre (exploratorio, fase 4)
- Etiquetas por niveles de confianza: **fuerte** (marca `disused:`/`was:`), **probable** (desaparece, con nombre, sin reemplazo y sin rastro en Foursquare), **dudosa** (el resto, no se usa). *(Definición original; la sección 3.M la sustituye: la etiqueta principal ya no usa Foursquare, «fuerte» incluye más marcas de cierre y se fijan las definiciones.)*
- Clasificador (boosting) con validación espacial. Se informa con **sensibilidad al ruido**: solo fuertes vs fuertes+probables.
- **Solo entra en el asistente si su AUC en validación espacial excluye 0,5 con intervalo de confianza**; si no, queda como hallazgo del TFM. *(Regla original; la sección 3.M añade la condición de mejorar a las líneas base triviales y fija dos candidatos con IC del 97,5 %.)*

### E. Perfiles de negocio: qué cuenta como competencia, mercado y proveedor

Una tabla de conocimiento (`src/ml/business_profiles.py`) que, para cada tipo de negocio, dice qué etiquetas de OSM son cada cosa. Sin ella no se puede calcular ninguna lente. Esta información **no se deduce de los datos** (ningún dato dice si un supermercado compite con una panadería): es conocimiento de negocio. Por eso la tabla es un **perfil por defecto** que el usuario puede ajustar (ver más abajo), y no una verdad fija. Ejemplo de los valores por defecto (borrador, **a revisar**):

| Tipo | Competencia directa | Competencia indirecta (sustitutos) | Generadores de mercado | Proveedores típicos |
|---|---|---|---|---|
| Restaurante / café (`food_drink`) | otros `food_drink` | supermercados con comida preparada, panaderías | oficinas, colegios, hoteles, ocio, residentes | mayoristas, carnicerías, pescaderías, verdulerías, panaderías, bebidas |
| Panadería / pastelería | panaderías, pastelerías | supermercados | residentes, oficinas, colegios | mayoristas, alimentación |
| Farmacia (`hospital`) | farmacias | droguerías, supermercados | centros de salud, residentes, oficinas | distribuidores sanitarios (casi sin datos) |
| Gimnasio (`sport`) | gimnasios y centros deportivos | — | oficinas, residentes, colegios | proveedores de equipamiento (casi sin datos) |
| Comercio (`business`, por subcategoría) | misma subcategoría | subcategorías afines | residentes, oficinas, ocio, turismo | mayoristas del sector |

Lo que ya hay **no basta** para todos los tipos: donde los proveedores casi no están cartografiados (mayoristas, distribuidores sanitarios) el lente se marca como "sin datos suficientes" y no se inventa.

#### Perfiles ajustables por el usuario

Los valores por defecto no se imponen: el usuario conoce su negocio mejor que el sistema (una pizzería artesanal no compite igual que un local de comida rápida; sabe si vende a turistas, a oficinistas o al barrio; sabe qué proveedores usaría). Pero **tampoco se deja la definición en blanco**: la mayoría de usuarios no sabe qué es una etiqueta de OSM, y sin valores por defecto razonables un perfil mal definido produciría un panorama engañoso que se atribuiría al modelo.

**Controles, en lenguaje de negocio (no en etiquetas técnicas):**

| Pregunta al usuario | Control | Por defecto |
|---|---|---|
| ¿A quién le vendes? | casillas: residentes, oficinistas, estudiantes, turistas, vida nocturna | las del perfil del tipo de negocio |
| ¿Qué consideras competencia? | lista de tipos de negocio con opción de quitar o añadir | competencia directa e indirecta del perfil |
| ¿Qué proveedores te importan? | casillas con los tipos de proveedor | los habituales del perfil |
| (opcional) modo avanzado | edición de las etiquetas de OSM de cada grupo | — |

**Reglas que se mantienen:**
1. El panorama **indica qué perfil se usó** (por defecto o modificado y cómo), porque los resultados dependen de esas elecciones.
2. Un perfil **no puede dejar una lente sin ningún elemento**: se avisa y se vuelve al valor por defecto de esa lente.
3. **Lo que el usuario cambia solo afecta a las lentes explícitas.** Son conteos sobre una tabla precalculada de celda × subcategoría de OSM, y recalcularlos al momento es barato. En cambio **el modelo de brecha de oferta aprendido (sección B) no se reentrena** con cada cambio: sigue usando las categorías estándar, y la pantalla lo dice. Mezclar ambas cosas sin avisar haría creer que el modelo aprendido entiende la definición personal de competencia.
4. Los **valores por defecto se revisan** una vez (los revisa quien decida el autor: él mismo, su tutor o alguien con experiencia en el sector) y quedan documentados como criterio del autor si no hay revisión externa.
5. La comparabilidad entre recomendaciones se conserva porque siempre existe el perfil por defecto como punto de referencia.

### F. Resultados de la fase 0 (medidos con `tools/measure_lens_variance.py`, base real en solo lectura)

Sobre las 1.139 celdas activas y los perfiles por defecto:

| Perfil | Competencia: CV | Mercado: CV | Proveedores: CV | Spearman competencia~mercado | Celdas con mercado alto y competencia baja* |
|---|---|---|---|---|---|
| Restaurante, café o bar | 1,91 | 1,26 | 1,23 | **+0,71** | **9 %** |
| Comercio u oficina | 1,14 | 1,28 | sin datos | +0,74 | 9 % |
| Farmacia, clínica | 1,11 | 1,26 | sin datos | +0,69 | 11 % |
| Gimnasio | 1,37 | 1,26 | 2,15 | +0,56 | 9 % |
| Ocio y cultura | 2,33 | turistas sin datos | sin datos | +0,30 | 0 % |
| Centro comercial | 1,94 | 1,63 | 4,37 | +0,43 | 0 % |

\* Si las lentes fueran independientes saldría ~25 %. CV = coeficiente de variación (desviación / media); por encima de 1 la lente varía mucho entre celdas.

**Lo que dicen los números:**
1. **Las lentes sí varían** (CV > 1 casi siempre): la hipótesis de que los proveedores no discriminarían era falsa.
2. **Pero están muy correlacionadas** (competencia~mercado entre +0,56 y +0,74 en los perfiles con datos). Las tres miden sobre todo *densidad urbana*: donde hay más de todo, hay más competencia, más mercado y más proveedores. Por eso solo un ~9 % de las celdas combina mercado alto con competencia baja, en vez del 25 % esperable.
3. **Consecuencia de diseño:** una suma ponderada de las lentes en bruto (como el MCDA actual) quedaría dominada por la densidad y premiaría o castigaría a las mismas celdas por casi cualquier combinación de pesos. El puntaje debe usar indicadores **relativos a la densidad** (la brecha de oferta de la sección B, que es justamente el residuo tras controlar por contexto, y razones como mercado/competencia), y la sensibilidad a los pesos debe mostrar si el ranking cambia de verdad.
4. **Lo que no se puede medir hoy** (queda marcado como "sin datos" en cada lente, no como cero): residentes (necesita la fase 1b), turistas (hoteles, fase 1b), distribuidores sanitarios y mayoristas (1 solo en la base).

**Dos defectos del propio diseño que la medición destapó y que ya están corregidos:**
- **Doble conteo:** un mismo POI contaba como competencia y a la vez como mercado o proveedor (un museo, competencia directa de un negocio de ocio, contaba también como "generador de turistas"). Con esa definición el cuadrante favorable salía al 0 % en ocio. Regla fijada: **un POI cuenta en una sola lente, con prioridad competencia > mercado > proveedores** (`src/ml/lenses.py`).
- **Perfiles mal definidos:** la competencia directa del comercio genérico era *todo* `business`, lo que incluía las oficinas (que son mercado) y las tiendas proveedoras; y el gimnasio tenía sustitutos con etiquetas que no existen en los datos (100 % ceros). Corregidos en los valores por defecto, que siguen siendo criterio del autor a revisar.

### G. Resultados de la fase 1 (medidos con `tools/validate_location_model.py`, base real en solo lectura)

Validación cruzada espacial: 10 repeticiones, bloques de 4×4 celdas (~1 km), 1.139 celdas activas. Desviación de Poisson media por celda (menos es mejor):

| Modelo | food_drink | business |
|---|---|---|
| **boosting** (Poisson) | **1,513** ± 0,061 | **2,586** ± 0,097 |
| solo densidad urbana (mejor línea base) | 1,695 ± 0,046 | 2,804 ± 0,043 |
| red MLP | 2,441 ± 0,507 | 6,424 ± 2,846 |
| solo distancia al centro | 3,442 | 4,987 |
| solo población | 4,497 | 5,640 |
| media constante | 4,625 | 5,594 |

| Candidato frente a la mejor línea base (densidad) | Diferencia por celda (IC 95 %, bootstrap de bloques) | Veredicto |
|---|---|---|
| boosting, food_drink | −0,182 [−0,566, +0,178] | **indistinguible** |
| boosting, business | −0,218 [−0,514, +0,121] | **indistinguible** |
| MLP, food_drink | +0,747 [+0,119, +1,652] | peor |
| MLP, business | +3,619 [+0,278, +10,137] | peor |

**Decisión según la regla de la sección 4: ningún candidato mejora a la mejor línea base con claridad, así que NO se publica puntaje de ML; se queda el MCDA.** Es un resultado válido y consistente con lo anunciado: las tres lentes y las variables miden sobre todo densidad urbana (sección F), y con ~1.100 celdas (unos 80 bloques independientes) el contexto adicional no se distingue del ruido.

**Matices que hay que contar en el TFM:**
- El boosting es **mejor en estimación puntual** (~11 % menos de desviación que la densidad en `food_drink`, ~8 % en `business`; mejor Spearman y precisión@50: 0,58 frente a 0,50 en `food_drink`) pero el intervalo toca el 0. No se puede descartar una mejora pequeña; tampoco afirmarla. Con las variables de la fase 1b (edificios, hoteles, paradas) podría cambiar: es la siguiente palanca.
- **La red MLP rinde peor y es muy inestable** (desviación estándar entre repeticiones de 0,5 y 2,8). Parte es una limitación conocida: scikit-learn no ofrece pérdida de Poisson en la red y se entrena sobre log(1 + conteo), lo que infraestima los conteos grandes. En Spearman y precisión@50 se acerca al boosting (0,50 y 0,56 frente a 0,55 y 0,58), o sea, ordena razonablemente pero está mal calibrada en escala de conteo. Una red con pérdida de Poisson (requiere `torch`, decisión 2) es la prueba justa que falta.
- **Contraste independiente con Foursquare** (AUC de la oferta esperada fuera de muestra para las celdas con locales en Foursquare): `food_drink` boosting 0,883, MLP 0,860, densidad 0,851, distancia 0,838, población 0,575; `business` 0,809, 0,793, 0,772, 0,768, 0,403. Mismo orden que la desviación, con ventajas pequeñas. Entre las 50 celdas de mayor brecha, el 12 % (`food_drink`) y el 0 % (`business`) tiene más locales en Foursquare que en OSM, frente a un 10 % y un 1 % de referencia: **no hay señal de que la brecha sea un artefacto de falta de mapeo**.
- **La brecha absoluta favorece a los centros saturados.** La mayor de `food_drink` es la celda `r36c17` (St Julian's): 18 locales observados frente a ~62 esperados, +44, en la zona más densa de restauración. Por eso se calcula también la **brecha relativa** (en desviaciones típicas), y en la fase 2 el panorama debe usar la relativa. Las celdas de mayor brecha están más cerca de los centros (mediana 559 m frente a 1.974 m en el conjunto), como era de esperar.
- Sin edificios ni población por celda no se puede comprobar que las celdas de mayor brecha tengan gente (fase 1b).

**Corrección de mi propio procedimiento durante la fase 1:** la primera versión de `decide()` promediaba las predicciones de todas las repeticiones y después calculaba la desviación. Con eso el boosting de `business` salía como «mejora» ([−0,655, −0,098]), pero el veredicto cambiaba con el número de repeticiones: promediar convierte a cada candidato en un conjunto de modelos y favorece a los de alta varianza frente a las líneas base. Ahora la desviación se calcula **en cada repetición por separado** y luego se promedia (un modelo honesto cada vez); el veredicto es el mismo con 4, 10 y 20 repeticiones. Hay un test de regresión.

**Dos errores de robustez que los datos reales o los tests destaparon:** una variable toda en NaN (por ejemplo, la accesibilidad si la base no tiene datos de rutas) rompía el boosting al discretizarla; ahora se descartan esas columnas.

### H. Resultados de la fase 1b (contexto de OpenStreetMap, 8-nov-2026)

**Qué se descargó** (7 consultas a Overpass con pausas de 12 s, ~3 MB, a archivos fuera de la base; la base no cambió):

| Tema | Elementos | Observaciones |
|---|---|---|
| Edificios | 15.608 | **78 % son `building=yes`** (genéricos); solo el 11 % está marcado como residencial; el 16 % tiene número de plantas. Hay edificios en 1.419 celdas (los POIs activaban 1.139) |
| Alojamiento | 198 | 129 hoteles, 29 casas de huéspedes, 21 apartamentos, 18 hostales; solo 7 con habitaciones o camas, así que solo se pueden **contar** |
| Transporte | 1.156 | 1.134 paradas de autobús, 18 de ferry, 3 estaciones y 1 andén (las 427 `stop_position` se descartan: duplican las paradas) |
| Industria / mayoristas | 149 | 145 áreas industriales y **un único mayorista** (el mismo de antes) |

**Límites que hay que declarar:** al ser casi todo `building=yes`, no se distingue vivienda de comercio; «residentes» se aproxima con los edificios que no son claramente no residenciales (excluye industriales, escuelas, iglesias, garajes, cobertizos...), y el número de edificios mide superficie construida, no población. **La lente de proveedores no mejora**: sigue sin mayoristas.

**Efecto en las lentes.** «Residentes» y «turistas» (alojamiento) pasan de «sin datos» a tener valores en todas las celdas activas. Correlación de Spearman entre la competencia directa de `food_drink` y cada segmento de mercado: residentes **+0,52**, oficinistas +0,59, estudiantes +0,51, turistas +0,69, vida nocturna +0,20. El cuadrante «residentes altos y competencia baja» contiene el **17 %** de las celdas (frente a ~25 % si fueran independientes), así que los residentes se parecen menos a la competencia que el resto de segmentos, pero **el hallazgo de la fase 0 se mantiene**: el índice de mercado combinado sigue correlacionado con la competencia (+0,73) y solo ~10 % de las celdas combinan mercado alto y competencia baja.

**Corrección durante la fase:** `mercado_total` sumaba conteos en bruto y, con ~90 edificios por celda frente a ~1 colegio, era casi solo «cuántos edificios hay» (aparentaba un cuadrante favorable del 16 %, que era un artefacto de escala). Ahora es un **índice 0-1**: la media de los segmentos con datos, cada uno escalado por su máximo en la rejilla.

**Efecto en los modelos** (misma validación espacial, mismas 1.139 celdas; desviación de Poisson por celda, menos es mejor):

| Modelo | food_drink | business |
|---|---|---|
| boosting **con** contexto | **1,486** | **2,458** |
| boosting solo con POIs (fase 1) | 1,513 | 2,586 |
| solo densidad de POIs (mejor línea base) | 1,695 | 2,804 |
| red MLP con contexto | 2,027 (±0,31) | 5,141 (±2,06) |
| solo edificios (línea base nueva) | 3,816 | 4,535 |

| Comparación | food_drink | business |
|---|---|---|
| boosting con contexto − mejor línea base | −0,209 [−0,568, +0,104] **indistinguible** | −0,346 [−0,664, +0,015] **indistinguible** |
| **¿aporta el contexto?** (boosting con − sin contexto) | −0,027 [−0,188, +0,112] **indistinguible** | −0,128 [−0,269, +0,027] **indistinguible** |
| MLP con contexto − mejor línea base | +0,332 [−0,171, +0,985] indistinguible | +2,337 [−0,261, +7,323] indistinguible |

**Decisión según la regla de la sección 4: sigue sin publicarse puntaje de ML** (en ninguno de los dos objetivos). El contexto mejora la estimación puntual (~2 % en `food_drink`, ~5 % en `business`) pero ningún intervalo queda por debajo de 0; en `business`, la comparación con la línea base queda en el límite (+0,015). Contraste con Foursquare (AUC): `food_drink` boosting con contexto 0,890 (sin contexto 0,883; densidad 0,851); `business` 0,816 (0,809; 0,772). Entre las 50 celdas de mayor brecha no hay señal de falta de mapeo (10 % frente a 10 % de referencia en `food_drink`; 0 % frente a 1 % en `business`).

**Lectura para el TFM:** con ~1.100 celdas (unos 80 bloques independientes) y estas variables, la información del contexto urbano más allá de la densidad de POIs **no se puede separar del ruido**. La densidad de comercios ya recoge casi todo lo que los edificios, el alojamiento y el transporte aportan. Es un resultado negativo bien medido, no una limitación del código.

### I. Entrenar en otra máquina (fase 1c, 9-nov-2026)

El entrenamiento no corre donde está el stack. Hasta la fase 1b las herramientas abrían `data/mobility.db` (~412 MB, casi todo mediciones de rutas con su polilínea) y leían el contexto de OSM de un directorio temporal. Ninguna de las dos cosas viaja bien, así que la fase 1c define las entradas y salidas del entrenamiento:

- **Paquete de entrada** (`tools/export_ml_inputs.py` → `data/ml_inputs.sqlite`, `src/ml/inputs_bundle.py`). Un archivo SQLite sin dependencias nuevas, con las **mismas tablas y columnas que ya lee `data_access`**, así que `--db paquete.sqlite` funciona en `validate_location_model.py` y `measure_lens_variance.py` sin más cambios. Lleva los POIs de Overpass y de Foursquare, la población por zona, el tiempo de viaje medio por par de zonas (ya agregado) y el contexto de OSM normalizado. Medido con la base real: **0,3 MB sin contexto y 1,0 MB con él, frente a 412 MB**.
- **Manifiesto y verificación.** Cada paquete guarda fecha, commit, versiones de Python, pandas, numpy, scikit-learn y scipy, y filas y sha256 por tabla. `python tools/export_ml_inputs.py --verify paquete.sqlite` lo comprueba en la máquina de entrenamiento, sin la base; `validate_location_model.py` lo comprueba solo antes de entrenar y se detiene si no coincide.
- **Mismos resultados.** Con la base real, `measure_lens_variance.py` da una salida idéntica desde la base y desde el paquete, y `validate_location_model.py` también (mismas métricas con el contexto desde el directorio y desde el paquete). La base no se modifica.
- **Entorno** (`requirements-ml.txt`). Versiones exactas de pandas, numpy, scikit-learn y scipy. `requirements.txt` fija scikit-learn en la misma versión (1.9.0) y scipy en 1.17.1 (la última con wheels para Python 3.11 de Docker y CI; la máquina de entrenamiento usa 1.18.0 con Python 3.13).
- **Salida: tablas, no modelos serializados.** Lo que vuelve de la máquina de entrenamiento es una tabla precalculada (la de panoramas, en la fase 2) con su procedencia (`inputs_bundle.provenance`: hash del paquete, commit y versiones). No se mueven `.pkl`, que dependerían de la versión de scikit-learn del dashboard.

**Flujo:** `export_ml_inputs.py` (aquí) → copiar el archivo → `--verify` y entrenar (allí) → traer la tabla de resultados → versionarla (aquí).

**Fuera de alcance de esta fase:** `--jobs` en la validación (hoy tarda 1-2 minutos y es secuencial); y dónde lee el dashboard el contexto de OSM, que se decide con la tabla de panoramas en la fase 2.

### J. Panorama por celda (fase 2a, 9-nov-2026)

`tools/build_panorama.py` (en la máquina de entrenamiento, con el paquete de la sección I) calcula el panorama de las 1.139 celdas activas para los siete perfiles por defecto y escribe en `data/ml/`:

| Archivo | Contenido |
|---|---|
| `panorama.csv` | 7.973 filas (perfil × celda): ubicación, zona más cercana, las tres lentes con sus indicadores, percentiles, confianza y, solo para `food_drink` y `business`, la brecha exploratoria |
| `cell_counts.csv` | 1.447 celdas × (categoría\|subcategoría): la base para recalcular las lentes con el perfil que ajuste el usuario, sin la base de datos |
| `panorama_manifest.json` | procedencia (hash de la entrada, commit, versiones), parámetros, decisión de la validación y sha256 de los dos CSV |

`src/ml/panorama.py` solo usa numpy, pandas y scipy (la rejilla ya lo usaba): **no importa scikit-learn**, así que el dashboard puede importarlo. Con `--sin-brecha` solo se calculan las lentes, en segundos; con la brecha, ~1 minuto por objetivo.

**Qué dice cada columna y qué no:**
- **Lentes y percentiles.** Indicadores explícitos (conteos); el percentil ordena las celdas de 0 a 1 y deja `NaN` donde no hay datos (sin datos no es una posición baja). No hay puntaje combinado.
- **Confianza** (`confianza` 0-1 y `confianza_nivel` alta/media/baja): media de las tres lentes de min(apoyo / 5, 1), con 0 para una lente sin datos. En las siete categorías, ~74 % de las celdas salen con confianza alta, ~26 % media y ninguna baja. **No es una probabilidad.** La competencia se apoya en los POIs de cualquier categoría de la vecindad (`pois_vecindad`) y no en el número de competidores: «cero competidores» es una observación creíble donde hay mucho mapeado, y con el número de competidores las celdas sin competencia saldrían siempre con confianza baja, justo las que interesan.
- **Brecha exploratoria** (`esperado`, `brecha_relativa`, `brecha_p10`, `brecha_p90`, `modelo_brecha`, `brecha_validada`). Es la brecha relativa de la sección G, fuera de muestra y con el boosting. **`brecha_validada` es False** porque ningún candidato superó con claridad a la densidad de POIs (diferencias −0,209 y −0,346, ambas indistinguibles de 0, idénticas a las de la fase 1b). El manifiesto lo declara. Viaja en columnas propias y no entra en ninguna otra. Con el boosting, ~3 % de las celdas de `food_drink` y ~7 % de las de `business` tienen brecha relativa mayor que 1. **Los percentiles 10-90 no son un intervalo de confianza:** miden solo cuánto cambia la brecha según cómo se reparten los bloques entre entrenamiento y prueba (anchura mediana 0,08 y 0,22), y subestiman la incertidumbre real del modelo.

**Error encontrado y corregido durante la fase:** `cell_counts.csv` incluía solo las celdas activas, pero estas se definen con POIs de Overpass y el contexto de OSM (edificios, alojamiento) de celdas inactivas vecinas también suma en las lentes de las activas. Recalcular desde esa tabla daba otros números (2,4 % de las celdas con distinto `mercado_residentes`). Ahora incluye toda celda con algún conteo (1.447 en lugar de 1.139) y un test comprueba que las lentes recalculadas son idénticas a las del panorama.

**Reproducibilidad:** con la misma entrada y semilla, `panorama.csv` sale con el mismo hash (comprobado dos veces, incluida la brecha).

### K. Interfaz del panorama (fase 2b, 9-nov-2026)

El panorama aparece en **Recomendación**, debajo del resultado por zona (`streamlit_app/dashboards/panorama_section.py`; la lógica sin Streamlit está en `src/ml/panorama_view.py` y no importa scikit-learn). Lee `data/ml/` y se niega a mostrarlo si algún CSV no coincide con el hash del manifiesto.

- **Tres lentes por separado, sin puntaje combinado.** El mapa colorea una capa a la vez (competencia directa, mercado, proveedores, diversidad de proveedores); la ficha de la celda elegida muestra las tres con sus indicadores, la confianza y su significado.
- **Controles de perfil** (sección E): a quién vendes, competencia directa, competencia indirecta y proveedores, partiendo del perfil por defecto. Cada cambio recalcula las lentes desde `cell_counts.csv`, sin la base. La pantalla **siempre indica el perfil usado** y avisa cuando se aparta del por defecto: lente que no puede quedar vacía, más de la mitad de la competencia por defecto quitada («el panorama será más optimista de lo que los datos respaldan») y elementos elegidos como directa e indirecta a la vez (cuentan solo como directa). Se puede **añadir** competencia con cualquier categoría y subcategoría de OSM, salvo las del contexto (edificios, transporte...).
- **La brecha es una capa aparte, etiquetada «EXPLORATORIA, no validada».** Aparece solo en `food_drink` y `business`, con la advertencia de que la validación no mostró que supere a la densidad de comercios y de que su intervalo no es de confianza. **No se recalcula con el perfil** (decisión de la sección E): la pantalla lo dice cuando el perfil es personalizado.
- **Lista de celdas ★:** mercado en el 25 % superior, competencia directa en el 25 % inferior y confianza no baja. Es un **filtro**, no un puntaje; se muestra cuántas celdas lo cumplen y se advierte de que, como las lentes se parecen, son pocas.
- **Los resultados sobreviven a tocar un control.** Antes, cualquier cambio volvía a ejecutar la página con el botón «Buscar» en falso y los resultados desaparecían (también pasaba con los pesos). Ahora se recuerda el texto buscado hasta que se pulsa el botón otra vez; el texto vacío borra la búsqueda anterior. Los controles del panorama tienen una clave por categoría, para que los ajustes de un negocio no pasen al siguiente.

**Límites que la pantalla no resuelve:** el perfil por defecto es un borrador del autor y los pesos de «qué es competencia» siguen siendo conocimiento de negocio, no un resultado de los datos; los residentes se aproximan con edificios no claramente no residenciales (~78 % de los edificios de Malta son `building=yes`); y la brecha, aun etiquetada, puede leerse como una recomendación. Las otras cinco categorías no tienen brecha y siguen con el panorama explícito.

### L. Clasificador de texto (fase 3, 9-nov-2026)

**Resultado de la primera evaluación: el clasificador entrenado NO se adopta; se queda el método de palabras clave** (la repetición con otro conjunto, en la sección 3.L2, sí lo adopta). Es un resultado negativo según la regla fijada antes de ver los datos, y con una causa concreta que se explica abajo.

**Qué se construyó** (`src/ml/text_classifier.py`, `src/ml/text_training.py`, `tools/evaluate_text_classifier.py`, datos en `data/text/`):
- TF-IDF de n-gramas de caracteres (2 a 5, por palabra) + regresión logística, con una clase `ninguna` (frases que no describen un negocio) y un umbral de confianza: si gana `ninguna` o no se llega al umbral, no se elige categoría, como hace el método actual.
- **Inferencia de solo numpy**, sin scikit-learn: el modelo se exporta a JSON (vocabulario, idf, coeficientes) en lugar de un `.pkl`, para no depender de la versión de scikit-learn del dashboard. Un test comprueba que las probabilidades coinciden con las de scikit-learn (error < 1e-9) en todas las frases del proyecto.
- Segundo candidato: una red MLP de scikit-learn sobre los mismos TF-IDF (3 semillas).
- **Datos escritos a mano por el autor:** 347 frases de entrenamiento y un conjunto de evaluación reservado de **200** (39 directas, 53 sinónimos, 34 erratas, 34 frases largas y 40 fuera de alcance). Ninguna frase de evaluación se usa para entrenar ni para elegir el umbral (sale de una validación cruzada sobre el entrenamiento; un test lo comprueba barajando las etiquetas de evaluación).

**Regla de decisión (fijada de antemano):** el híbrido —palabras clave primero y, solo si se abstienen, el clasificador— se adopta si (a) su exactitud supera a la de las palabras clave con el intervalo por bootstrap pareado por encima de 0 y (b) su tasa de respuestas equivocadas no pasa de la de las palabras clave más 2 puntos.

| Sistema | Exactitud | Respuestas equivocadas | Sin respuesta |
|---|---|---|---|
| palabras clave | 45,0 % | **3,0 %** | 52,0 % |
| logística | 69,0 % | 11,5 % | 19,5 % |
| red MLP | 72,5 % | 14,0 % | 13,5 % |
| **híbrido (palabras + logística)** | **73,0 %** | 10,0 % | 17,0 % |

| Tipo (n) | palabras clave | logística | híbrido |
|---|---|---|---|
| directa (39) | 92 % / 8 % | 85 % / 13 % | 92 % / 8 % |
| errata (34) | 21 % / 0 % | 79 % / 6 % | 82 % / 3 % |
| larga (34) | 24 % / 6 % | 26 % / 21 % | 41 % / 18 % |
| sinónimo (53) | 0 % / 0 % | 57 % / 15 % | 57 % / 15 % |
| fuera de alcance (40) | 98 % / 2 % | 98 % / 2 % | 95 % / 5 % |

(exactitud / respuestas equivocadas.) La exactitud del híbrido mejora en **+28,0 puntos** [IC 95 %: +22,0, +34,5] → cumple (a). Pero sus respuestas equivocadas son el 10,0 % frente al 3,0 % de las palabras clave (tolerancia +2 puntos) → **no cumple (b)**. La red no se distingue de la logística (−3,5 [−8,0, +1,0]), y es peor en respuestas equivocadas.

**Lectura honesta:**
- El clasificador gana donde las palabras clave no llegan —erratas (21 % → 82 %) y sinónimos (0 % → 57 %)—, pero **contesta mal más a menudo cuando contesta**: confunde cines con museos, carnicerías con restaurantes, o responde a «reservar una mesa para el sábado». Las palabras clave, cuando responden, casi siempre aciertan, y por eso cuestan menos en respuestas equivocadas.
- **La causa del fallo de (b) es un defecto de mi protocolo, no solo de los datos:** el umbral se eligió maximizando la exactitud fuera de muestra, lo que trata igual una respuesta equivocada que una pregunta sin respuesta. Salió el mínimo de la rejilla (0,30), el más atrevido. La regla (b), en cambio, penaliza justo las respuestas equivocadas. Los dos criterios no son coherentes.
- **Sensibilidad al umbral (solo descriptiva):** con un umbral de 0,50 o más, el mismo híbrido sí cumpliría la regla (4,0 % de respuestas equivocadas con 0,50). Pero elegir ahora el umbral mirando esa tabla sería ajustar a la evaluación. **No cambia la decisión:** cualquier cambio de protocolo exige una evaluación nueva.

**Límites que condicionan todo el resultado:**
1. **Las frases las escribió el mismo autor** (entrenamiento y evaluación), no son consultas reales de usuarios. La exactitud es optimista.
2. **La composición del conjunto la fijó el autor:** 121 de 200 frases son sinónimos, erratas o frases largas, pensadas para que las palabras clave fallen. Por eso la exactitud global de las palabras clave (45 %) no dice cómo irá con consultas reales; lo comparable es el desglose por tipo.
3. **Etiquetas discutibles:** una carnicería o un «mall con cine» admiten más de una lectura. No hay una verdad única.
4. 200 frases dan intervalos anchos, y las erratas y sinónimos de entrenamiento y evaluación comparten estilo.

**Qué haría falta para adoptarlo:** (i) un criterio de umbral coherente con la regla, fijado antes —p. ej. el umbral más bajo cuyas respuestas equivocadas fuera de muestra no superen las de las palabras clave más la tolerancia—; (ii) un conjunto de evaluación nuevo, idealmente con consultas reales o escritas por otras personas. Con eso, la herramienta ya está lista: `python tools/evaluate_text_classifier.py` (`--exportar data/ml` guarda el modelo y su manifiesto; `--sin-mlp` omite la red).

### L2. Repetición de la fase 3: protocolo fijado antes de generar los datos (12-nov-2026)

Este apartado se escribe y se sube al repositorio **antes** de generar el segundo conjunto de evaluación; el historial de git lo prueba. Corrige los dos defectos que dejó la sección L.

**Qué cambia respecto a la primera evaluación**
1. **El umbral de confianza se elige con un criterio coherente con la regla (b):** el más bajo cuyo híbrido no comete, fuera de muestra sobre el entrenamiento, más respuestas equivocadas que las palabras clave más 2 puntos (`elegir_umbral`). Antes se elegía el de mayor exactitud, que trata igual una respuesta equivocada que una pregunta sin respuesta.
2. **Conjunto de evaluación nuevo, escrito por otro autor.** Las frases de evaluación de la sección L (200) quedan **consumidas** y no vuelven a usarse para decidir. El conjunto nuevo lo escribe **Codex** (un modelo de OpenAI), sin ver las 347 frases de entrenamiento ni las 200 de la primera evaluación: solo recibe las siete categorías con su definición, los cinco tipos de frase y las cuotas de abajo. No se le envía ningún dato del proyecto.

**Lo que NO cambia:** las 347 frases de entrenamiento, el vectorizador, la regresión logística, la red MLP, las palabras clave, la rejilla de umbrales y la regla de decisión: (a) la exactitud del híbrido supera a la de las palabras clave con el IC por bootstrap pareado por encima de 0 y (b) sus respuestas equivocadas no pasan de las de las palabras clave más 2 puntos. **Después de ver los resultados no se cambia nada de lo anterior**; si se encuentra un error, se documenta y se repite la evaluación completa declarando que hubo una repetición.

**Composición fijada de antemano (200 frases):**

| Tipo | Frases | Qué es |
|---|---|---|
| directa | 40 | nombra el negocio, sin rodeos |
| sinónimo | 40 | lo describe con otras palabras o con un término poco habitual |
| errata | 30 | con faltas de ortografía o letras cambiadas |
| larga | 50 | una frase con contexto, como la escribiría una persona al explicar su idea |
| fuera de alcance | 40 | no describe un negocio (otro tema, ruido, algo vago o sin sentido) |

Las 160 frases que sí describen un negocio se reparten así por categoría: `food_drink` 30, `business` 30, `hospital` 20, `school` 20, `sport` 20, `leisure` 20, `mall` 20 (las 40 fuera de alcance son la clase `ninguna`). Se pide además variedad de redacción (varios registros, español de distintos países, localidades de Malta cuando encaje) y que las frases parezcan consultas reales, no ejemplos escolares.

**Etiquetado doble y ciego.** Una segunda sesión de Codex recibe solo las frases, **barajadas y sin etiqueta ni tipo**, más las definiciones de categoría (las mismas que el generador, salvo una cláusula añadida a `ninguna`: «o que solo menciona un negocio sin pedir abrirlo»; ver el límite 7), y las etiqueta. Las frases en las que su etiqueta **no coincide** con la del autor se consideran ambiguas: se **excluyen de la evaluación principal** y se evalúan aparte, informando cuántas son y cómo salen los sistemas en ellas. Esto ataca el límite 3 de la sección L (etiquetas discutibles) a costa de favorecer las frases claras, y se declara así. La regla de decisión se aplica al conjunto principal; el resultado sobre las 200 completas se informa también.

**Control de calidad de los datos (mecánico, definido ya):** se descartan las frases vacías, las repetidas y las que coinciden (sin distinguir mayúsculas) con una de entrenamiento; se informa cuántas se descartaron. Si tras descartar quedan menos de las cuotas, se piden las que faltan a Codex con las mismas instrucciones, sin ver los resultados de ningún sistema.

**Límites que siguen valiendo:** las frases las escribe un modelo de lenguaje, no usuarios reales (otro tipo de sesgo: puede ser más correcto y más variado que un usuario real, y su estilo no es el del entrenamiento escrito a mano); la composición la fijamos nosotros; 200 frases dan intervalos anchos; y el etiquetador ciego es también un modelo, así que su acuerdo con el autor mide consistencia, no verdad.

**Resultado (12-nov-2026): con la regla fijada de antemano, el híbrido SE ADOPTA.** Se ejecutó una sola vez por configuración preregistrada (principal y completa), sin cambiar nada después de verlas. El etiquetado ciego coincidió con el del autor en **192 de 200 frases (96 %)**; esas 192 son el conjunto principal y las otras 8 se evalúan aparte.

| Sistema (192 frases) | Exactitud | Respuestas equivocadas | Sin respuesta |
|---|---|---|---|
| palabras clave | 66,7 % | 5,7 % | 27,6 % |
| logística | 58,3 % | 2,6 % | 39,1 % |
| red MLP | 61,5 % | 1,0 % | 37,5 % |
| **híbrido (palabras + logística)** | **76,0 %** | 6,2 % | 17,7 % |

- **(a) Exactitud:** el híbrido mejora a las palabras clave en **+9,4 puntos [IC 95 %: +5,2, +13,5]**: el intervalo queda por encima de 0 → cumple.
- **(b) Respuestas equivocadas:** 6,2 % frente a 5,7 % (+0,5 puntos; tolerancia +2) → cumple.
- **Umbral elegido solo con el entrenamiento:** 0,50 para la logística (0,75 para la red). Con el criterio antiguo habría salido 0,30; ya no.
- **Conjunto completo (200 frases):** +9,0 [+5,0, +13,0] y 7,0 % frente a 6,5 %; misma decisión.
- La red no se distingue de la logística (−3,1 [−8,3, +2,1]); se queda la logística, que es la exportable a JSON.

| Tipo (n) | palabras clave | logística | híbrido |
|---|---|---|---|
| directa (36) | 81 % / 3 % | 72 % / 0 % | 92 % / 3 % |
| errata (29) | 69 % / 0 % | 55 % / 0 % | 79 % / 0 % |
| larga (48) | 69 % / 2 % | 42 % / 4 % | 81 % / 4 % |
| sinónimo (39) | 36 % / 3 % | 33 % / 0 % | 49 % / 3 % |
| fuera de alcance (40) | 80 % / 20 % | 92 % / 8 % | 80 % / 20 % |

(exactitud / respuestas equivocadas.)

**Lectura honesta**
- **Dónde ayuda:** gana entre 10 y 13 puntos en los cuatro tipos que sí describen un negocio. Sin embargo, **los sinónimos siguen en solo el 49 %**: la mitad de las frases con otras palabras se queda sin respuesta o se responde mal.
- **Dónde no ayuda:** en las frases fuera de alcance el híbrido se equivoca el **20 %**, igual que las palabras clave, porque hereda su fallo: de las 8 que contesta mal, 5 solo *mencionan* un negocio («mi tía trabaja en una farmacia», «El gimnasio de mi barrio cierra demasiado temprano», «mi primo va a una escuela de inglés», «ayer cené en un restaurante», «Mi hermano tiene una cita en el dentista mañana») y 3 contienen una palabra suelta de negocio sin pedir abrir nada («¿Qué barrios de Malta son más seguros para vivir?» → `business`, «¿Cómo preparo un buen café con leche en casa?» → `food_drink`, «la dirección de la oficina de correos» → `business`). La logística sola solo se equivoca el 8 % ahí. Es un defecto real del híbrido tal como está definido (las palabras clave van primero) y **no se ha corregido**, porque cambiarlo exigiría una evaluación nueva.
- **Las 8 ambiguas:** varias parecen errores del etiquetador más que ambigüedad real (y una causa plausible de al menos cuatro es una asimetría del protocolo, ver el límite 7) («Cine en St Julian's», «Farmacia de guardia en Sliema», «Veterinaria en Marsaskala» y «Busco una panadería artesanal» etiquetadas como `ninguna`). La regla las excluye igualmente, y excluirlas apenas cambia el resultado (completo: +9,0 frente a +9,4). En esas 8 las palabras clave y el híbrido dan la misma respuesta (siete responden y una se abstiene): coincide con la etiqueta del autor en 5 y con la del etiquetador en 2.
- **Sensibilidad al umbral (solo descriptiva):** el híbrido cumple la regla en todos los umbrales mostrados de 0,40 a 0,80 (la tabla avanza de 0,10 en 0,10); falla a 0,30 (13 % de respuestas equivocadas) y a 0,90 (ya no mejora a las palabras clave con claridad). El 0,50 elegido no está en el borde.
- **Las cifras absolutas no son comparables con la sección L:** otro conjunto, otra composición y otras frases. Las palabras clave suben del 45 % al 66,7 % sobre todo porque aciertan mucho más dentro de cada tipo (sinónimos 0 % → 36 %, erratas 21 % → 69 %, frases largas 24 % → 69 %): las frases de este conjunto usan más a menudo palabras que el método ya conoce. No se debe leer como una mejora de las palabras clave.

**Límites que condicionan la conclusión**
1. **Las frases las escribió un modelo de lenguaje, no usuarios reales.** Su español es más correcto y variado que el de un usuario, y sus erratas son plausibles pero artificiales.
2. **El etiquetador ciego es el mismo modelo en otra sesión:** comparte puntos ciegos con el generador. El 96 % de acuerdo mide consistencia, no verdad.
3. **El entrenamiento sigue siendo del autor** (347 frases escritas a mano), con un estilo distinto al de las de evaluación, lo que es sano, pero no equivale a consultas reales.
4. **La composición la fijamos nosotros** (cuotas por tipo y categoría) y el desglose por tipo es lo comparable; 200 frases dan intervalos anchos.
5. **No se registró el nombre del modelo de Codex** (`codex-cli 0.167.2`, modelo por defecto, sin configuración propia): la procedencia exacta de las frases no es reproducible, aunque los prompts y las etiquetas están en `data/text/evaluacion_v2/`.
6. **Este segundo conjunto también queda consumido:** una mejora futura del clasificador exigiría un tercero.
7. **Asimetría de las definiciones:** el etiquetador ciego recibió, para `ninguna`, una cláusula que los prompts de generación de los tipos directa, sinónimo, errata y larga no llevaban («o que solo menciona un negocio sin pedir abrirlo»). Es plausible que explique cuatro de los ocho desacuerdos («Busco una panadería artesanal», «Cine en St Julian's», «Farmacia de guardia» y «Veterinaria en Marsaskala», etiquetadas `ninguna`). No cambia la decisión (con las 200 frases se cumple igual) pero se declara: el 96 % de acuerdo está algo deprimido por esa diferencia.
8. **Integración en la app (PR #72):** `src/ml/text_hibrido.py` aplica el híbrido evaluado (un test comprueba que da la misma respuesta que la evaluación para cada frase del conjunto principal), carga `data/ml/text_classifier.json` verificado con su manifiesto (adoptado y hash) y, si falta o no cuadra, la pantalla vuelve a las palabras clave. Cuando decide el modelo, la pantalla lo indica, muestra su confianza y abre el selector para **corregir la categoría**; cuando responden las palabras clave se presenta como antes (con el selector plegado). **El motivo no es que se sepa que el modelo falle más:** en las 192 frases las palabras clave responden 107 y se equivocan 11 (10,3 %; 8 de ellas son frases fuera de alcance que solo mencionan un negocio), mientras el modelo responde solo 19 y se equivoca 1 (5,3 %), una muestra demasiado pequeña para comparar. Se señala porque es una lectura que el usuario no puede anticipar por una palabra visible y casi no está medida. No hay medición con usuarios reales: las cifras de este apartado son las del conjunto escrito por Codex.

### M. Fase 4: riesgo de cierre exploratorio — protocolo fijado antes de descargar el estado completo del área (12-nov-2026, revisado v2)

**Historia de este protocolo (transparencia).** La v1 (commit `31f7d68`) se subió antes de descargar nada. Una revisión independiente encontró fallos de diseño y huecos que habrían permitido decidir después de ver los datos. **Aún no se ha descargado ningún dato del área** (el primer intento falló por indisponibilidad de Overpass), así que esta v2 corrige el protocolo **antes** de ver ninguna etiqueta o resultado del área completa; la v1 queda en el historial de git. Cambios respecto a la v1: el AUC se promedia por repetición (no las predicciones); el método de validación es el real de la fase 1 (no `GroupKFold`); **Foursquare sale de la etiqueta principal**; el contexto estático actual sale de las variables principales; se definen identificador, superviviente, fuerte, normalización de nombres y distancia; se fijan modelos e hiperparámetros; la regla de decisión se rehace (dos candidatos, líneas base triviales, nivel corregido); y la puerta se aclara. **Lo que sí se vio antes:** la sonda de la sección 2 etiquetó ya una parte de esta población (`food_drink` de Msida–Gzira–Sliema, foto de 2022); de ella salen el umbral de 60 m y la idea de contrastar con Foursquare. Esos valores **no se ajustan** con los datos nuevos y esa zona no se presenta como evidencia independiente.

Autorizada por el autor la descarga del estado histórico de toda el área para **las siete categorías** (12-nov-2026).

**Pregunta.** Con datos solo de OpenStreetMap, ¿el entorno de un local en 2022 (competencia y densidad de locales) predice si ya no figura hoy? **Es una señal de entorno, no una probabilidad de cierre ni de rentabilidad** (no hay datos de resultados de negocio).

**Datos (a archivos fuera del repositorio y de la base).** Overpass con consultas de fecha (`[date:...]`), el área de la rejilla (35,84–35,94 N, 14,44–14,58 E, ~11 × 13 km), las siete categorías de `CATEGORY_TAGS` (nodos y ways), en **1-ene-2022**, **1-ene-2024** y **hoy**, más los elementos con marca de ciclo de vida de hoy. `tools/download_osm_history.py`: pausa, reintentos por rondas, rechazo de espejos que ignoren la fecha o devuelvan un error de Overpass con HTTP 200.

**Identificador y representante.** Un local es el par **(tipo, id)** de OpenStreetMap (nodo 123 y way 123 son elementos distintos). Su posición es el nodo, o el centro (`out center`) si es un way; un local que pasa de nodo a way **no** se empareja por identificador (ver «dudoso»). Las distancias son en metros entre esos puntos representativos; con polígonos grandes el centro puede quedar lejos del borde (límite declarado).

**Población de estudio.** Elementos de la foto de 2022 con nombre, en las siete categorías, dentro de la rejilla **y a más de 500 m de su borde** (la descarga se limita a la rejilla: sus vecinos de fuera no cuentan y los recuentos de los locales del borde quedarían truncados), y que **no** sean `shop=vacant` ni lleven `disused=yes`, `abandoned=yes` o `vacant=yes` (no son un negocio abierto). Unidad: el local. **Nombre normalizado:** minúsculas, sin tildes ni signos de puntuación, espacios colapsados; dos nombres son «el mismo» si son **iguales** tras normalizar (sin coincidencia aproximada).

**Etiquetas de cierre (definidas ya; todas se miran contra la foto de «hoy»).** «Categoría» significa **cualquiera de las siete** salvo que se diga «la misma categoría». Se evalúan **en este orden y decide la primera que se cumple** (así no hay solapes):
1. **fuerte:** el (tipo, id) figura hoy con una marca de ciclo de vida (`disused:`, `was:`, `abandoned:`, `demolished:`, `razed:` sobre la clave de categoría) **y no figura hoy con su etiqueta de categoría activa**; **o** figura hoy con `shop=vacant`, `disused=yes`, `abandoned=yes` o `vacant=yes`, **aunque haya cambiado de nombre o de categoría** (un local vacío es un cierre explícito; por eso «fuerte» prevalece sobre «dudoso»). (Amplía la sección D, que solo citaba `disused:`/`was:`.)
2. **superviviente:** el (tipo, id) figura hoy con **la misma categoría** que en 2022, **el mismo nombre normalizado** y ninguna marca de cierre.
3. **dudoso (no entra ni como positivo ni como negativo):** el (tipo, id) sigue pero cambió de nombre o de categoría (negocio distinto en el mismo punto); el (tipo, id) no figura pero hay hoy un elemento de las siete categorías con el mismo nombre normalizado a ≤ 60 m (re-mapeo, paso de nodo a way); o figura hoy con una categoría activa **y** una marca de ciclo de vida de las prefijadas (sin `shop=vacant` ni `disused=yes`, que ya serían «fuerte»).
4. **probable:** todo el resto, es decir, el (tipo, id) **no figura hoy** ni con categoría ni con marca de ciclo de vida **y** no hay hoy un elemento de las siete categorías con el mismo nombre normalizado a ≤ 60 m. **No se usa Foursquare.**

«No figura hoy» significa «no aparece hoy en ninguna de las siete categorías ni con marca de cierre»: **incluye** los borrados y los **reetiquetados fuera de las siete categorías**, que no se pueden distinguir con lo que se descarga (límite declarado).

**Por qué Foursquare no está en la etiqueta principal.** Foursquare solo se consultó alrededor de los siete centros de zona y de puntos de sus corredores (`build_search_points`, radio 1.500 m, máximo 50 resultados por punto): su cobertura depende de la distancia a esos puntos, que se correlaciona con la densidad de locales, y el filtro habría metido en la etiqueta justo lo que el modelo debe predecir. **Sensibilidad B (solo descriptiva):** repetir con «probable» exigiendo además que no haya en Foursquare un local del mismo nombre normalizado a ≤ 150 m, y **solo para locales dentro de 1.500 m de algún punto de búsqueda de Foursquare**; se excluyen las fichas «(sin nombre)».

**Cierre principal** = fuerte ∪ probable contra superviviente. **Sensibilidad A (descriptiva):** solo fuertes contra superviviente.

**Variables principales (todas de la foto de 2022; ninguna del estado actual).** Categoría (7, una columna por categoría); número de locales de la **misma categoría** y **totales** de la foto de 2022 a **250 m y 500 m** (sin contar el propio local) sobre **todos los elementos de las siete categorías de la foto de 2022**, con o sin nombre, **excluidos** los `shop=vacant` y los marcados `disused=yes`, `abandoned=yes` o `vacant=yes`; distancia al más cercano de la misma categoría (m, máximo 1.000); y si el nombre normalizado se repite **≥ 3 veces** en la foto de 2022 (cadena). **No se usan** el contexto estático del estado actual (edificios, alojamiento, paradas, industria: es posterior al resultado, y un local dibujado como edificio, o un edificio derribado, entra o sale del recuento según sobreviva), ni el tiempo de viaje (TomTom), ni la población por zona (Data Commons). **Sensibilidad C (descriptiva):** añadir edificios, alojamiento y paradas a 250/500 m **solo si** se descarga ese contexto con `[date:"2022-01-01"]` (exigiría ampliar la herramienta).

**Modelos y líneas base (fijados, sin ajuste de hiperparámetros).**
- Candidato 1, **regresión logística**: variables numéricas estandarizadas, categoría codificada una-columna-por-categoría, regularización L2 (la de por defecto: **no** se pasa `penalty`, deprecado desde scikit-learn 1.8 y eliminado en 1.10), `C=1,0`, `max_iter=2000`. Versión fijada en `requirements.txt` (scikit-learn 1.9.0).
- Candidato 2, **boosting** (`sklearn.ensemble.GradientBoostingClassifier`): `n_estimators=150`, `max_depth=2`, `learning_rate=0,05`, `subsample=0,8`, `min_samples_leaf=10`, `random_state` = la semilla de la repetición. Sin ajuste interno ni parada temprana.
- Líneas base **triviales**: **constante** (AUC 0,5); **solo categoría** (tasa de cierre por categoría calculada con los datos de entrenamiento de cada pliegue); **solo densidad** (logística con solo los cuatro recuentos a 250/500 m, con `log(1 + n)`).

**Validación (la de la fase 1, `src/ml/validation.py`).** En cada una de **10 repeticiones**, la cuadrícula de bloques de 1 km (`BLOCK_CELLS = 4` celdas de 250 m) se **desplaza al azar** y los bloques se reparten al azar en **5 pliegues** (`block_labels`, `assign_folds`; no `GroupKFold`). Cada local obtiene así una probabilidad fuera de muestra **por repetición**. **El AUC se calcula en cada repetición** (todas las probabilidades fuera de muestra de esa repetición, juntas) **y después se promedia** entre repeticiones: **no se promedian las predicciones** entre repeticiones (convertiría a cada candidato en un conjunto de modelos y favorecería al de más varianza; `decide()` ya lo prohíbe y tiene un test). **Intervalo:** remuestreo de **bloques** (cuadrícula **sin desplazar**), 2 000 réplicas; en cada réplica se **recalcula el AUC** de cada repetición con los locales de los bloques remuestreados y se promedia. Hace falta código nuevo (`block_bootstrap_mean` solo sirve para medias por elemento). La **mejor línea base trivial** (la de mayor AUC medio entre «solo categoría» y «solo densidad») se **elige una sola vez**, con todos los datos y antes del remuestreo, y no se reelige en cada réplica; la diferencia con ella se mide con el mismo remuestreo, pareado. **Semillas:** base 0; la repetición `r` usa la semilla `0 + r` (como la fase 1), también para el `random_state` del boosting.

**Puerta de tamaño muestral (fijada ya, solo para el análisis principal).** Se entrena y se evalúa **solo si** hay **al menos 60 cierres principales** y **al menos 30 bloques de 1 km (cuadrícula sin desplazar) con algún cierre**. Si no, el resultado es **«no concluyente: no se entrena»**, se publica el recuento y no se hace nada más. Las sensibilidades A, B y C y el control de 2024 son **descriptivos**: se ejecutan solo si tienen al menos 30 positivos (si no, se informa del recuento) y **no influyen en la decisión**.

**Regla de decisión (fijada ya).** Hay dos candidatos, así que cada intervalo es del **97,5 %** (corrección de Bonferroni). Una señal de riesgo de cierre se considera **utilizable** si **al menos un candidato** cumple, en el cierre principal, **(a)** límite inferior del IC del AUC **> 0,5** y **(b)** límite inferior de la diferencia con la **mejor línea base trivial** (categoría o densidad) **> 0**. (El diseño original (D) exigía solo (a); se añade (b) para que «mejor que el azar» no baste si algo trivial ya lo explica, como pasó en la fase 1. La logística es candidato, no línea base, para que una señal captada por un modelo simple no se descarte por no ganar a un boosting.) Si se cumple, **no entra directamente a la pantalla**: pasaría a un PR aparte con su propia revisión y con el aviso de que es una señal de entorno. Si no, **queda como hallazgo del TFM** y no se expone nada al usuario.

**Controles descriptivos.** Repetir con la foto de 2024 como instante de partida (cierres entre 2024 y hoy); desglose por categoría; tasa de cierre por categoría.

**No se cambia nada después de ver los resultados.** Si se encuentra un error, se documenta y se repite entera declarando que hubo una repetición.

**Sesgos y límites declarados de antemano:** el mapa creció un 52 % de 2022 a hoy por mejor cartografía, no por negocios nuevos (los locales de 2022 son los más visibles: sesgo de supervivencia); «ya no figura» no es «cerró» (un reetiquetado fuera de las siete categorías o un borrado de mapeo cuentan igual); el reuso de un nodo por otro negocio solo se detecta si cambia el nombre o la categoría; el centro de un polígono grande puede quedar a más de 60 m; la mezcla de nodos y ways; el 26 % de los «plausibles» de la sonda parecía seguir abierto en Foursquare (por eso hay una sensibilidad con ese filtro); y con pocos cierres los intervalos serán anchos.

**Qué se publica y qué no.** Se versionan solo agregados (recuentos por instante, categoría y nivel de etiqueta; la tabla de resultados; el manifiesto con hashes y fecha de descarga). **No** se versionan etiquetas por local. Datos de OpenStreetMap bajo ODbL, con atribución.
### Confianza de datos por celda
Cada panorama lleva una **confianza** visible: cuántas de las tres lentes tienen datos reales, qué categoría de OSM es poco fiable en esa zona (por ejemplo, `food_drink` se ve en torno al 61 % frente a Foursquare) y cuántos POIs sustentan cada indicador. Una celda con poca información no se presenta con la misma seguridad que una bien cubierta.

## 4. Protocolo de validación (fijado antes de entrenar)

1. **Validación cruzada espacial por bloques** (bloques de ~1 km con la cuadrícula desplazada al azar en cada repetición y bloques repartidos al azar en pliegues, repetida): evita que celdas vecinas, que se parecen, inflen la métrica. La validación al azar daría números falsamente buenos.
2. **Métricas:** desviación de Poisson, correlación de Spearman entre conteo predicho y observado en bloques reservados, y acierto en las k celdas mejor clasificadas.
3. **Líneas base** que el ML debe superar: media constante; solo distancia al centro; solo población; y el MCDA actual convertido en predictor de la misma etiqueta.
4. **Criterio de éxito:** el ML mejora a la mejor línea base en la desviación de Poisson, con el intervalo de las repeticiones separado del de la línea base. **Si no, no se publica el puntaje de ML y se queda el MCDA** (resultado válido para el TFM).
5. **Contraste independiente:** el modelo se entrena **solo con OSM** y se evalúa contra los locales de **Foursquare** (411 restaurantes): ¿caen en celdas con más oferta esperada que otras? Foursquare cubre solo el 15 % de lo que ve OSM, así que es un contraste parcial.
6. **Revisión de cordura:** las mayores brechas no deben caer en celdas sin edificios ni población (mar, zonas industriales). Es el motivo de la fase 1b.

## 5. Fases (un PR por fase, como hasta ahora)

| Fase | Entregable | Depende de |
|---|---|---|
| 0 | **Hecha (PR #38).** Rejilla y variables (`src/ml/`), con tests y control de fuga; **perfiles de negocio por defecto** (sección E) y los indicadores de las tres lentes con los datos que ya hay; **tabla precalculada celda × subcategoría de OSM** (base del recálculo al ajustar el perfil); medición de cuánto varía cada lente entre celdas | — |
| 1 | **Hecha (PR #39).** Modelos de oferta (boosting y MLP) + `tools/validate_location_model.py` (validación espacial reproducible, como `validate_forecast.py`); resultado en la sección 3.G: **ningún candidato supera a la densidad con claridad, no se publica puntaje de ML** | 0 |
| 1b | **Hecha (PR #40).** Edificios, alojamiento turístico, paradas de transporte e industria/mayoristas descargados de Overpass (`tools/download_osm_context.py`, a archivos fuera de la base) y cargados desde `src/ml/osm_context.py`. Resultado en la sección 3.H: residentes y turistas ya tienen datos; **el contexto no cambia la decisión de la fase 1**; los mayoristas siguen sin datos (solo hay uno) | descarga autorizada |
| 1c | **Hecha (PR #41).** Entrenamiento en otra máquina (sección 3.I): paquete de entrada de ~1 MB con manifiesto y verificación (`tools/export_ml_inputs.py`), `--db` acepta el paquete, `requirements-ml.txt` con versiones exactas y convención de salida (tablas con procedencia, sin `.pkl`) | 1b |
| 2a | **Hecha (PR #42).** Tabla precalculada de panoramas por celda (tres lentes, percentiles, confianza y brecha exploratoria etiquetada), conteos para recalcular con otro perfil y manifiesto: `src/ml/panorama.py` y `tools/build_panorama.py` (sección 3.J). Sin interfaz | 1c |
| 2b | **Hecha (PR #43).** Interfaz (sección 3.K): mapa de calor y ficha por celda en Recomendación, **con los controles de perfil ajustable** (a quién vendes, qué es competencia, qué proveedores) y la indicación del perfil usado; el MCDA se conserva como respaldo y para las otras 5 categorías. Tests de pantalla del recálculo al cambiar el perfil y del aviso de que el modelo aprendido no cambia | 2a |
| 3 | **Hecha (PR #44) y repetida (PR #71).** Clasificador de texto comparado con las palabras clave: la primera evaluación (sección 3.L) **no lo adopta**; la repetición con un conjunto escrito por Codex y etiquetado a ciegas (3.L2) **sí adopta el híbrido** (+9,4 puntos de exactitud, 6,2 % frente a 5,7 % de respuestas equivocadas), **conectado a Recomendación en el PR #72** (palabras clave primero, el modelo solo si se abstienen, lectura del modelo indicada con su confianza y categoría corregible por el usuario). La primera evaluación no lo adoptó por tener más respuestas equivocadas que las palabras clave. | — |
| 4 | **En curso (PR #73):** riesgo de cierre exploratorio (sección 3.M). Descarga autorizada por el autor el 12-nov-2026 para las siete categorías. Protocolo **v2** (revisado tras una revisión independiente, antes de descargar el área completa) y herramienta de descarga listos; **la descarga está pendiente**: los servidores públicos de Overpass no respondían. Sin resultados | 0, descarga autorizada |

## 6. Riesgos y sesgos que hay que declarar en el TFM

- **Presencia ≠ éxito:** el modelo aprende dónde *hay* negocios, no dónde *prosperan*. La "brecha" supone un equilibrio de mercado que no se ha comprobado.
- **Cobertura de OSM desigual:** `food_drink` está medido en ~61 % frente a Foursquare, y el mapa creció un 52 % desde 2022. Zonas peor cartografiadas parecerán "con brecha".
- **Demanda débil:** población estimada y solo por zona hasta que haya señal de edificios (fase 1b).
- **Muestra pequeña:** 560 celdas y dos categorías con datos suficientes. Los intervalos serán anchos; hay que mostrarlos.
- **Etiquetas de cierre ruidosas:** 26 % de los "cierres plausibles" parece seguir abierto en la prueba.
- **Perfiles personalizados:** si el usuario redefine la competencia o los proveedores, el panorama cambia pero el modelo aprendido no; y un perfil muy sesgado (por ejemplo, quitar casi toda la competencia) produce un panorama más optimista sin que los datos lo respalden. Por eso el perfil usado se muestra siempre en el panorama y se avisa cuando se aparta mucho del valor por defecto.

## 7. Decisiones pendientes

1. **Resuelta para la fase 1b** (edificios, alojamiento, transporte e industria, a archivos temporales). **Resuelta también para la fase 4:** el autor autorizó el 12-nov-2026 el **estado histórico de toda el área** para las siete categorías (riesgo de cierre; la sonda inicial cubrió solo una zona). La descarga aún no se ha podido hacer por indisponibilidad de los servidores públicos de Overpass.
2. ¿Se añade **`torch`** (solo para entrenar, no en el dashboard)? El MLP de scikit-learn rindió peor y de forma inestable, en parte por no tener pérdida de Poisson (sección 3.G); una red con esa pérdida es la comparación justa que falta, pero es una dependencia pesada para un resultado que probablemente siga sin superar a la densidad.
3. **Aplicado:** el criterio de éxito de la sección 4 se aplicó tal como estaba fijado y dio un resultado negativo (no se publica puntaje de ML). Queda por decidir qué hacer con la brecha de oferta en la fase 2: (a) no mostrarla, (b) mostrarla etiquetada como **exploratoria** junto a las lentes explícitas, o (c) esperar a la fase 1b.
4. **Resuelta (sección 3.L2):** las 200 frases de evaluación las escribió Codex con etiquetado ciego. Antes: ¿quién escribe las **~200 frases de evaluación** del clasificador de texto? Idealmente alguien que conozca el lenguaje real de los usuarios; yo puedo proponer un borrador.
5. ¿Quién **revisa los valores por defecto de los perfiles de negocio** (sección E)? Ya no es crítico, porque el usuario puede corregirlos; basta con que alguien con criterio de negocio los repase una vez: el propio autor, su tutor o una persona con experiencia en el sector. Yo preparo el borrador completo. Si no hay revisión externa, el TFM debe decir que son criterio del autor.
6. ¿Qué **umbral** de desviación del perfil por defecto activa el aviso al usuario (por ejemplo, quitar más de la mitad de los elementos de competencia)? Propongo empezar en la mitad y ajustarlo con las primeras pruebas.
