# Plan de implementación — IA distribuida

Estado al 26 de noviembre de 2026. El equipo confirmó la línea base real del benchmark. La admisión por cuota, la deduplicación y el cooldown se coordinan en PostgreSQL. HU02, HU09 y HU10 tienen distribución inicial de tareas independientes.

## Restricciones definitivas

- Exclusivamente APIs gratuitas, con presupuesto de **$0** en benchmark y producción. Excluir OpenAI. Descartar configuraciones que puedan generar cargos. Cuando se agote la capacidad gratuita, pasar a otro proveedor gratuito elegible o al flujo manual.
- Usar el entorno local con PostgreSQL 17 y pgvector, sin Ollama, modelos generativos locales ni Docker.
- Eliminar toda carrera entre proveedores. Distribuir tareas independientes con concurrencia acotada y un solo intento activo por tarea desde la aplicación. Aplicar fallback secuencial, gestión de cuotas reales y cooldown.
- Medir velocidad, calidad y estabilidad por operación. Preservar las reglas de GUIOS, los contratos de respuesta, las referencias, la trazabilidad y la revisión humana.

## Fase 0 — Registrar línea base local [revisión estática completada]

- Rama de trabajo `feature/optimizacion-ia`, HEAD `f0be354`. `AGENTS.md` y `docs/` ya estaban sin seguimiento. Preservar el trabajo local y requerir autorización para cambios remotos.
- Entorno virtual, dependencias, PostgreSQL 17, pgvector, migraciones y Django operativo confirmados por el equipo.
- Pendiente antes de implementar el enrutador: registrar `python manage.py check` y las pruebas locales pertinentes. Este diagnóstico no ejecutó Django ni contactó APIs.

## Fase 1 — Benchmark aislado [implementado y probado con los candidatos del piloto]
- Reutilizar los cuatro contratos de `ai_contracts.py`. Preparar herramienta aislada (por ejemplo un comando Django o script en `benchmarks/`), sin persistir valoraciones reales ni modificar el enrutador productivo.
- Verificar con documentación oficial vigente los endpoints, autenticación, capacidad JSON, disponibilidad, condiciones del nivel gratuito, cuotas y política de datos. Excluir OpenAI y cualquier configuración con posibilidad de cobro. Usar credenciales autorizadas del entorno sin imprimirlas ni registrar datos confidenciales.
- Crear dataset anonimizado con casos de HU02, preguntas, suficiencia y valoración. Piloto sugerido: 20–30 subfactores reales o sintéticos representativos, con ejemplos de falta de información, contradicciones, cumplimiento parcial y referencias falsas/instrucciones incrustadas. HU02 requiere casos bibliográficos propios. Separar datos de ajuste y evaluación; revisión humana independiente.
- Validar primero la herramienta con mocks. Con autorización para llamar a APIs y gratuidad verificada, probar un caso por operación y luego ejecutar casos comparables en corridas separadas por proveedor, con repeticiones acotadas y dentro de las cuotas gratuitas. Permitir ejecución por proveedor y operación, exportación CSV/JSON sin datos sensibles y reanudación.
- Métricas: latencia total p50/p95, tiempo por operación, tokens, coste, errores/429, JSON válido, referencias existentes y realmente pertinentes, calidad humana, exactitud y confusión de clases (en especial 1 vs 2), relevancia/no redundancia de preguntas, clasificación bibliográfica. Medir consistencia entre repeticiones y rendimiento concurrente.
- Requisitos de calidad antes de velocidad: excluir modelos que no cumplan contrato, referencias y umbral de calidad acordado. No inventar pesos/umbrales definitivos; elegir con el usuario a partir de resultados.
- Aceptación: informe reproducible por proveedor, modelo y operación, con límites, muestras, fallos y confirmación de coste $0. Selección justificada por calidad, latencia y estabilidad antes de modificar el enrutador productivo.

## Fase 2 — Sustituir carreras por enrutamiento secuencial [implementado y validado con mocks]
- Refactorizar `proveedor_ia.py`, conservando la interfaz `obtener_proveedor(tipo)` y adaptadores donde sea posible. Eliminar `ProveedoresParalelos` y los envíos simultáneos de una misma tarea; actualizar sus pruebas.
- Un trabajo lógico recibe un proveedor elegible. El fallback requiere que el intento anterior haya terminado. Si un timeout, fallo de red o vencimiento deja dudas, la tarea espera confirmación externa o continúa manualmente.
- Limitar intentos y plazo total; respetar permisos, validación y fallback manual. Un timeout no asegura cancelación remota: registrar incertidumbre de consumo y no duplicar persistencia.
- Conservar metadatos por respuesta/intento, evitando estado mutable compartido entre tareas. Revisar usos de `ultimo_identificador` y compatibilidad de llamadas.
- Aceptación: pruebas con mocks demuestran que una tarea exitosa hace una sola consulta; fallo activa respaldo secuencial; no se despachan carreras; todos los proveedores fallidos producen error controlado; no hay propuestas duplicadas.

## Fase 3 — Cuotas, credenciales y planificación [implementada]
- Integrar solo proveedores y modelos gratuitos aprobados por benchmark. Reutilizar el transporte compatible cuando proceda. Separar identidad de credencial, proveedor/modelo y unidad de cuota real (proyecto/equipo/recurso/plan, según documentación). Varias claves de la misma unidad no multiplican cuota.
- Normalizar errores HTTP y metadatos: 400/401/403/429/5xx, timeout, invalidación de contrato. Distinguir error permanente de transitorio; respetar Retry-After y reset si existen; backoff con jitter, cooldown y circuito de salud. No rotar claves para eludir restricciones.
- Política de selección por operación: primero modelos aptos por calidad, después capacidad, cuotas, latencia observada y carga. Usar distribución ponderada o adaptativa, sin asignar tareas a modelos no aprobados. Ajustar concurrencia global y por unidad de cuota, con coordinación entre procesos (evaluar PostgreSQL antes de sumar infraestructura).
- Actualizar `config/settings.py` y `.env.example` para retirar OpenAI y documentar el enrutamiento secuencial, valores vacíos de secretos, límites de concurrencia, salida, intentos y plazos, y parámetros de cuota y cooldown. Mantener el presupuesto fijo en $0.
- Aceptación: simulación de cuota compartida, cooldown, recuperación, asignación a otro proveedor y exclusión de credencial inválida. No filtrar secretos en logs ni pruebas.

## Fase 4 — Distribuir tareas independientes [integración inicial implementada]
- Revisar primero `lotes_hu09.py`, `ai.py`, `preparacion_hu10.py` y `sugerencias_ia.py`. Reutilizar workers existentes y limitar concurrencia a la capacidad medida. No enviar una tarea a varios proveedores a la vez.
- HU09: paralelizar únicamente subfactores independientes dentro de una misma ronda; respetar dependencias con respuestas del decisor. HU10: evitar reconstrucción redundante de contexto y mantener llamadas HTTP fuera de transacciones. HU02: evaluar lotes y manejo de fallos sin perder integridad de la revisión humana.
- Asegurar vigencia de contexto, idempotencia, resultados parciales, recuperación de trabajos abandonados y persistencia atómica. No compartir objetos ORM/conexiones sin revisar seguridad de hilos.
- Aceptación: reducción medible del tiempo total respecto a línea base con calidad comparable, sin saturar cuotas, duplicar resultados ni alterar reglas de negocio.

## Fase 5 — Observabilidad, recuperación documental y despliegue [pendiente]
- Métricas por operación, proveedor/modelo, intento, versión de prompt, latencia, tokens, coste estimado, error y estado final. No almacenar prompts/evidencias completos en logs por defecto.
- Evaluar embeddings remotos, búsqueda híbrida y reranking solo después del benchmark generativo; comparar recuperación contra hashing existente. Cualquier cambio de dimensión/modelo necesita estrategia de reindexación y compatibilidad.
- Despliegue sin Docker ni Ollama: servidor WSGI/ASGI, procesos worker, PostgreSQL+pgvector, almacenamiento persistente y protegido, HTTPS, secretos, respaldo y recuperación. Revisar registro público con rol administrador, autorización de documentos y límites de subida, configuración DEBUG/hosts/CSRF.
- Aceptación: pruebas HU02/HU09/HU10/HU11 y flujo completo de resultados/PDF; revisión de seguridad y medición de rendimiento. No publicar sin aprobación del equipo.

## Uso eficiente de Codex
Abrir la raíz del repositorio en VS Code y leer `AGENTS.md`. Solicitar una fase concreta por sesión, sin pedir análisis completo repetido. Usar ChatGPT para diseño y revisión de diffs; Codex para cambios pequeños y pruebas locales. Al terminar, anotar commit, archivos, pruebas y bloqueos. Si el cupo se agota, continuar manualmente con Git y ChatGPT; los consumos de APIs de GUIOS son independientes.

## Línea base del benchmark (histórico)

Benchmark real confirmado por el equipo. Gemini obtuvo 8/8 contratos, calidad 7/8 y latencia media de 960 ms. Cohere obtuvo 8/8 contratos, calidad 6/8 y latencia media de 2870 ms. Groq devolvió 403, OpenRouter 429 y Cloudflare se omitió por configuración o autorización inválida.

Para habilitar una cuenta gratuita verificada, configurar `GUIOS_AI_AUTORIZACION_GRATUITA` con la ruta de un manifiesto vigente del mismo formato que el benchmark. El manifiesto debe reflejar las cuentas y los IDs exactos de modelo configurados para la aplicación. Configurar explícitamente `GUIOS_AI_COHERE_OPERACIONES` solo para los usos de datos aprobados. `GUIOS_AI_<PROVEEDOR>_UNIDAD_CUOTA` permite identificar cupos que realmente se comparten. El administrador bloquea la salida cuando falta la constancia local; la comprobación del plan en la cuenta corresponde al operador.

El piloto posterior recuperó Cloudflare y ejecutó HU02, HU09 y HU10. El procedimiento de instalación y arranque está en el [README](../README.md).

## Configuración y operación del planificador

- `GUIOS_AI_POLITICAS_CUOTA` es un objeto JSON por unidad real. La unidad puede declararse con `GUIOS_AI_<PROVEEDOR>_UNIDAD_CUOTA`; si falta, se usa el nombre del proveedor. Modelos o credenciales que compartan cuota deben usar la misma unidad. Mantener configuración y clave de Django coherentes entre procesos para conservar la identidad de trabajos y credenciales.
- Cada política declara `rpm`, `tpm` y `rpd`. Solo usar `null` donde se verificó que ese límite no aplica. Se admite `tpd` y `unidades_diarias` con `unidades_por_intento` para unidades de consumo específicas, por ejemplo Neurons. Se requiere al menos un límite numérico verificado. `concurrencia` tiene valor conservador de 1 si se omite. Una política ausente, inválida o incompleta bloquea solicitudes. Los límites usan ventanas móviles de 60 segundos o 24 horas, incluidas las reservas que podrían contar en la ventana.
- `tokens_por_intento` reserva un máximo conservador por solicitud y `max_tokens_salida` se transmite al proveedor. Verificar ambos valores para el modelo, incluido el razonamiento y la sobrecarga de su plantilla. La admisión rechaza entradas cuyo payload UTF-8 más la salida máxima supera la reserva. La contabilidad usa el mayor valor entre reserva y uso reportado. La comprobación de bytes es una cota operativa conservadora que requiere validación con cada tokenizador; no equivale a un conteo exacto. Para ventanas de unidades específicas, configurar un máximo conservador por intento según el proveedor.
- `GUIOS_AI_PERFILES_OPERACION` es un objeto JSON por clave `proveedor/modelo` y operación. Cada operación habilitada requiere `"validado": true`. Incluir `calidad` (0 a 1) y `latencia_ms` cuando existan mediciones por operación. El planificador considera primero calidad y luego latencia ajustada por solicitudes activas entre candidatos con capacidad. Sin mediciones por operación, conserva la prioridad provisional de Gemini. Los resultados agregados del benchmark no se copian como métricas por operación.
- `GUIOS_AI_TRABAJADORES_LOTE` limita los hilos por lote. `GUIOS_AI_ESPERA_SEGUNDOS` acota la espera por una reserva; `GUIOS_AI_RESERVA_SEGUNDOS` determina cuándo se considera abandonada (se respeta como mínimo el timeout y la espera más un margen). Ante incertidumbre se bloquea la tarea y se aplica cooldown a la unidad; el vencimiento por sí solo no permite reenviar esa tarea.
- `GUIOS_AI_REUSO_SEGUNDOS` limita la vigencia del resultado validado en PostgreSQL. El resultado puede contener referencias y justificaciones internas. Aplicar los mismos controles de acceso y protección que al resto de la base. Programar `python manage.py mantener_planificacion_ia` para recuperar reservas vencidas y borrar salidas expiradas. `python manage.py mantener_planificacion_ia --confirmar-termino ID_TAREA` reabre una tarea incierta tras confirmar con el proveedor que terminó. La recuperación del lote HU09 interrumpido sigue dependiendo de su worker y del flujo operativo existente.
- `IntentoIA` conserva operación, proveedor, modelo, espera, latencia, tokens reservados y reportados, fallback y motivo de fallo. No registra prompts, documentos, claves ni cuerpos de errores. Definir la retención de estas métricas y dimensionar las conexiones PostgreSQL según el número de workers y lotes simultáneos.

## Puesta en marcha local con presupuesto $0

### Pruebas integrales reales y transición de HU09 a HU10

| Flujo | Solicitudes | Concurrencia máxima | Ventana efectiva de IA | Suma de latencias | Tokens reservados / contabilizados |
|---|---:|---:|---:|---:|---|
| HU02, 50 publicaciones | 7 | 5 | 10.470 ms | — | 102.142 / 102.142 con la contabilidad histórica |
| HU09, evaluación 1 | 2 a Gemini | 2 | 1.322 ms | 2.468 ms | 9.893 / 1.418 |
| HU10, evaluación 1 | 2 a Gemini | 2 | 1.451 ms | 2.547 ms | 10.089 / 1.627 |

Las tres corridas finalizaron con cero errores, fallbacks e intentos abiertos. La ventana de IA mide el intervalo entre la primera reserva y el último cierre. En HU02, la observación total fue de 81.618 ms e incluyó interacción humana. La suma de latencias de HU09 y HU10 permite observar el solapamiento. Comparar con la ejecución secuencial requeriría otra medición con las mismas entradas y condiciones.

La consulta de solo lectura a PostgreSQL confirmó que el lote HU09 terminó con dos resultados de suficiencia vigentes, una ronda por subfactor y cero preguntas nuevas. ODF/ODT obtuvo 4/4 con `R:1`, la declaración que acredita exportación nativa a ODF 1.3. LDAPv3 obtuvo 1/4 con `R:2`, la declaración que indica que se limita a cuentas locales y carece de LDAPv3. Las menciones al manual y a las pruebas proceden de esa declaración sintética. Las dos propuestas conservan estado `PENDIENTE`, sin valor confirmado, decisor de validación ni fecha de confirmación.

El sondeo original solo actualizaba el progreso de HU09. El botón de HU10 seguía deshabilitado con el estado del HTML inicial. Al terminar HU09, la consulta devuelve ahora el resumen vigente de HU10 y actualiza sus acciones y etiquetas, sin reemplazar formularios editados. Las fichas de evidencia e historial se muestran completas en la siguiente navegación. Durante el sondeo activo se lee el estado del lote sin reconstruir evidencia. Los autoguardados prevalecen sobre respuestas atrasadas del sondeo. La interfaz bloquea envíos dobles y el servidor evita reenviar o sobrescribir propuestas ya completadas por otro lote.

En HU09 se eliminó la lectura duplicada del contexto por subfactor y el registro vacío de preguntas. En HU10 el lote prepara una vez el conjunto completo para seleccionar pendientes. Luego se reconstruye y valida únicamente cada subfactor objetivo antes de la solicitud y dentro de la transacción de escritura. Si cambian evidencia o suficiencia, se descarta la respuesta para ese contexto. La prueba con dos subfactores comprueba cuatro lecturas acotadas en HU09 y una lectura global más cuatro acotadas en HU10. Queda medir impacto de estas reducciones en lotes mayores y separar el coste de ORM del tiempo HTTP.

### Typhoon, benchmark sintético

El benchmark real se detuvo por transporte incierto. Mantener Typhoon deshabilitado y posponer las pruebas restantes de candidatos para después de la entrega.

Typhoon documenta la API experimental gratuita y publica 200 RPM y 5 solicitudes por segundo para `typhoon-v2.5-30b-a3b-instruct`. El benchmark solo acepta ese ID con una constancia exclusiva y los casos sintéticos del repositorio. Reutiliza el transporte del endpoint Chat Completions, conserva el prompt y la validación JSON local y adopta una solicitud por segundo como tope interno. Se detiene ante 401, 403, 429 o transporte incierto. La configuración operativa no admite Typhoon. El proveedor documenta recopilación de datos, por lo que las pruebas de producción quedan pendientes de revisar las condiciones de uso. [API](https://docs.opentyphoon.ai/en/api-reference/) · [Límites](https://docs.opentyphoon.ai/en/rate-limits/) · [Términos](https://opentyphoon.ai/tac)

Confirmar que la clave ya configurada pertenece a la API experimental gratuita antes de generar la constancia. El comando ejecuta los ocho casos, incluido P2 corregido, y conserva CSV y JSON con tokens, referencias, calidad, latencia y contrato.

```powershell
$marca = Get-Date -Format yyyyMMdd-HHmmss
$aut = ".\autorizacion-typhoon-$marca.json"
.\venv\Scripts\python.exe -m benchmarks.autorizar_typhoon --confirmo-nivel-gratuito --salida $aut
.\venv\Scripts\python.exe -m benchmarks.ia --modo real --proveedores typhoon --autorizacion $aut --salida ".\benchmark-typhoon-$marca"
```

### Piloto preparado de HU09 y HU10

`cargar_piloto_hu09_hu10` requiere el destino local comprobado y el decisor demo existente. Si la evaluación ya existe, devuelve sus IDs y su elegibilidad actual sin reiniciarla ni duplicarla. Usa un catálogo histórico aislado y fuentes de declaración sintéticas, sin editar el catálogo activo ni la cuenta.

En `guios_pro_ai_dev` quedó preparada la evaluación **1**, decisor **2** (`decisor.demo@guios.local`), con las valoraciones **2 y 1** elegibles. La verificación previa estimó 9.893 tokens reservados si un proveedor atiende ambos casos, o 994 Neurons si ambos van a Cloudflare. No quedó encolado ningún lote.

```powershell
.\venv\Scripts\python.exe manage.py cargar_piloto_hu09_hu10
.\scripts\ia-local.ps1 -Accion Configurar
.\scripts\ia-local.ps1 -Accion Cuotas
.\venv\Scripts\python.exe -m benchmarks.local_ia preparar-hu09 --evaluacion 1 --decisor 2
```

Arrancar Django y el worker HU09 en terminales separadas. Iniciar sesión con el decisor demo, usando su acceso existente, y abrir la ruta que imprime la preparación. Con el observador de HU09 esperando, pulsar **Analizar subfactores disponibles** una sola vez en **Análisis masivo de suficiencia**. Esperar `FINALIZADO` y verificar que aparecen dos resultados. La declaración de ODF acredita una función y la de LDAPv3 acredita su ausencia. Ambas pueden ser suficientes aunque conduzcan a propuestas distintas.

Cerrar el observador HU09 y abrir el de HU10. Si las dos filas muestran suficiencia vigente y están habilitadas, pulsar **Generar propuestas HU10 pendientes**. Verificar las dos propuestas y sus citas `R:`. Conservar su confirmación para HU11. Si algún modelo pide información indispensable, resolverla mediante el flujo habitual antes de intentar HU10.

### Benchmark multimodelo de Google

El perfil habitual conserva Gemini 3.5 Flash-Lite y Cloudflare. Los siguientes candidatos tienen las cuotas observadas en el panel del operador. Google confirma los IDs, acceso vía `generateContent` y entrada y salida gratuitas en Free Tier. Los resultados de cuota no se presentan como capacidades independientes. [Gemma en la API de Gemini](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api) · [Gemini 3.1 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite) · [Precios](https://ai.google.dev/gemini-api/docs/pricing) · [Límites por proyecto](https://ai.google.dev/gemini-api/docs/rate-limits)

| Modelo exacto | RPM | TPM | RPD | Validación JSON |
|---|---:|---:|---:|---|
| `gemma-4-26b-a4b-it` | 30 | 16.000 | 14.400 | Prompt y validación local |
| `gemma-4-31b-it` | 30 | 16.000 | 14.400 | Prompt y validación local |
| `gemini-3.1-flash-lite` | 15 | 250.000 | 500 | MIME JSON y validación local |

La guía de salidas estructuradas no lista Gemma. Por eso los dos Gemma reciben `systemInstruction` y el contrato como texto, sin exigir opciones de salida estructurada que la guía no documenta para esos modelos. El cliente descarta las partes de razonamiento y rechaza respuestas incompletas o fuera del contrato. Gemini 3.1 solicita `application/json` por `generateContent`. Gemini 3.5 y Cloudflare conservan sus rutas. [API de generación](https://ai.google.dev/api/generate-content) · [Salidas estructuradas](https://ai.google.dev/gemini-api/docs/structured-output)

`config/ia-politicas-modelos-candidatos.json` es un borrador para después del benchmark. Gemma parte de una reserva máxima interna de 8.192 tokens por intento, una sola solicitud simultánea por modelo, margen 256 y hasta 2.048 tokens de salida. El cálculo parte del tamaño real de los mensajes. Los contextos que excedan el techo de Gemma se descartan para ese candidato antes del HTTP y pueden dirigirse a otro modelo elegible. Si se habilita Gemma sobre la unidad actual, su TPM observado de 16.000 reduce también el techo conservador del proyecto. Las ventanas históricas, el contador de la unidad y el cooldown se conservan.

Para habilitación futura, `GUIOS_AI_MODELOS_ADICIONALES` define `proveedor → modelo exacto → operaciones`, por ejemplo `{"gemini":{"gemma-4-26b-a4b-it":"preguntas"}}`. `GUIOS_AI_POLITICAS_MODELO` usa `proveedor/modelo` como clave y la misma forma de política que el proyecto. `GUIOS_AI_PERFILES_OPERACION` sigue asociando calidad, latencia y validación por operación al ID exacto del modelo. La constancia de benchmark, marcada con `uso: benchmark`, no habilita el planificador. El script del piloto mantiene vacías las opciones multimodelo.

#### Autorizar y ejecutar desde PowerShell

Usar la clave existente de AI Studio únicamente si pertenece al proyecto Free Tier sin facturación habilitada. Usar solo los ocho casos sintéticos. El generador crea una constancia separada válida para el día de ejecución y no edita `.env` ni el manifiesto de la aplicación.

```powershell
$marca = Get-Date -Format yyyyMMdd-HHmmss
$aut = ".\autorizacion-google-benchmark-$marca.json"
.\venv\Scripts\python.exe -m benchmarks.autorizar_google --confirmo-nivel-gratuito --salida $aut
.\scripts\ia-local.ps1 -Accion Cuotas
```

Para ejecutar los 24 casos en una sola corrida, confirmar que queden **al menos 24 solicitudes** dentro del presupuesto interno de 30 para las últimas 24 horas, descontando los intentos previos del piloto y otros benchmarks. Ejecutar en una ventana aislada del tráfico Google de la aplicación, sin intentos en curso ni cooldown vigente, y dejar transcurrir un minuto desde el último intento de Google. El benchmark no escribe en PostgreSQL. Llevar su consumo aparte al calcular el saldo del proyecto. Si quedan menos de 24, ejecutar solo los modelos que quepan, en tandas de ocho por modelo, sin aumentar el presupuesto. Reservar capacidad para HU09/HU10 antes de iniciar.

```powershell
.\venv\Scripts\python.exe -m benchmarks.ia --modo real --modelo gemini=gemma-4-26b-a4b-it --modelo gemini=gemma-4-31b-it --modelo gemini=gemini-3.1-flash-lite --presupuesto-google 24 --autorizacion $aut --salida ".\benchmark-google-$marca"
```

Para una tanda de un modelo cuando haya ocho solicitudes disponibles:

```powershell
.\venv\Scripts\python.exe -m benchmarks.ia --modo real --modelo gemini=gemma-4-26b-a4b-it --presupuesto-google 8 --autorizacion $aut --salida ".\benchmark-gemma26-$marca"
```

El benchmark limita el conjunto de Google a 12 RPM y 16.000 TPM reservados en común. Conserva las reservas de tokens durante 60 segundos tras cada respuesta y separa la espera de la latencia del proveedor. Ejecuta los ocho casos por modelo, incluido P2 corregido, con los mismos criterios. Ante 401, 403, 429 o transporte incierto, corta los casos restantes de Google sin reintentar. CSV y JSON guardan calidad, referencias, contrato, latencia y tokens disponibles por caso.

### Resultados HU02 y conciliación de cuotas

Consulta de solo lectura de PostgreSQL al 26 de noviembre de 2026, 21:23 de Bogotá. Los saldos son internos, incluyen todas las operaciones de la unidad dentro de su ventana y pueden cambiar.

| Tanda HU02 | Intentos Gemini / Cloudflare | Tokens observados | Tokens reservados | Neurons contabilizados |
|---|---:|---:|---:|---:|
| Primera | 5 / 2 | 18.045 | 102.142 | 1.463 |
| Segunda, 50 publicaciones | 5 / 2 | 17.869 | 102.142 | 1.547 |
| Total | 10 / 4 | 35.914 | 204.284 | 3.010 |

La segunda tanda usó el 17,49 % de su reserva inicial. El acumulado observó un 17,58 %. En el corte quedaban 20 de las 30 solicitudes internas de Gemini y 6.990 de los 10.000 Neurons de Cloudflare. Ambas unidades estaban sin intentos activos. La consulta no cambió datos ni reinició ventanas.

La reserva inicial cubre el tamaño real de los mensajes del modelo y la operación, el margen de plantilla y el tope de salida. El sistema deja fuera los escapes y campos del sobre de transporte porque el proveedor recibe mensajes decodificados. Conserva el margen de 256 unidades, los 2.048 tokens máximos de salida y los topes de cuota del piloto. En PostgreSQL, `0017_reconciliacion_ia` agrega dos campos de cargo que preservan la reserva inicial. La conciliación se habilita explícitamente para Gemini y Cloudflare. Una respuesta nueva, confirmada y válida con uso coherente libera excedente. Los intentos inciertos y datos incompletos conservan al menos la reserva. Los intentos históricos conservan su cargo anterior y los contadores RPM/RPD siguen contando cada intento.

Para Cloudflare se aplica a cada lado el coeficiente vigente de ese modelo y se redondean hacia arriba entrada y salida por separado. Si falta un desglose exacto, se mantiene la estimación conservadora. El cargo es una contabilidad local que debe cotejarse con Workers AI. [Precios y Neurons de Cloudflare](https://developers.cloudflare.com/workers-ai/platform/pricing/) · [Límites de Gemini](https://ai.google.dev/gemini-api/docs/rate-limits)

```powershell
.\scripts\ia-local.ps1 -Accion Cuotas
.\scripts\ia-local.ps1 -Accion Plan
# Aplicar solo en guios_pro_ai_dev una vez revisado el plan.
.\scripts\ia-local.ps1 -Accion Migrar
```

`Cuotas` funciona antes y después de 0017. La migración agrega columnas nulas sin recalcular las filas existentes. Se aplicó en `guios_pro_ai_dev` y se verificó que las sumas de ambos proveedores y los saldos internos seguían iguales. Reiniciar Django y los workers con el perfil actualizado para usar la conciliación.

### Prueba controlada de HU09 y HU10

Preparar una evaluación sintética nueva con exactamente dos subfactores elegibles. Vincular evidencia breve y explícita a cada uno para permitir una sola ronda de suficiencia. Mantener ambos sin preguntas pendientes. Usar la evaluación del decisor de prueba y verificarla antes de encolar.

```powershell
.\scripts\ia-local.ps1 -Accion Configurar
.\scripts\ia-local.ps1 -Accion Cuotas
$evaluacion = [int](Read-Host 'ID de la evaluacion sintetica')
$decisor = [int](Read-Host 'ID del decisor de prueba')
.\venv\Scripts\python.exe -m benchmarks.local_ia preparar-hu09 --evaluacion $evaluacion --decisor $decisor
.\venv\Scripts\python.exe -m benchmarks.local_ia medir --hu HU09 --salida ".\hu09-$(Get-Date -Format yyyyMMdd-HHmmss).json"
```

`preparar-hu09` comprueba propiedad y estado, exige dos objetivos y calcula su reserva si un solo proveedor atiende ambos. La herramienta solo lee la base. Antes de encolar en Django, dejar margen para dos propuestas HU10 además de las dos solicitudes HU09. Encolar una vez y esperar a que el worker termine. Si algún objetivo requiere intervención, resolverlo por revisión manual antes de decidir si repetir. Consultar las cuotas otra vez y medir HU10 únicamente cuando haya propuestas habilitadas; la confirmación permanece en HU11.

### Perfil compartido del piloto

`config/ia-local.json` contiene las políticas, los perfiles por operación y los parámetros de ejecución de ambas terminales. `scripts/ia-local.ps1` prepara solo variables operativas de proceso. Django y HU09 leen la misma configuración y las credenciales del `.env` raíz. El script muestra la huella del perfil sin imprimir credenciales. Si se cambia el perfil, reiniciar Django y el worker y verificar que coincidan sus huellas.

| Unidad del piloto | Modelo | Concurrencia | RPM interno | Otros topes |
|---|---|---:|---:|---|
| `gemini-proyecto-dev` | `gemini-3.5-flash-lite` | 3 | 12 | 250.000 TPM confirmados. **30 peticiones por 24 h móviles como presupuesto interno de prueba**. RPD oficial pendiente. |
| `cloudflare-cuenta-dev` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | 2 | 30 | 10.000 Neurons por 24 h móviles en Workers Free. El perfil solo configura los límites publicados aplicables. |

Para ajustar `rpm`, `concurrencia` y `trabajadores_lote`, editar el JSON y medir otra vez en el mismo entorno. El perfil inicia con cinco hilos por lote y mantiene Cohere, Groq y OpenRouter deshabilitados.

Con `margen_tokens_entrada`, la reserva se calcula por petición a partir de los mensajes UTF-8, más 256 unidades de margen y un tope de 2.048 tokens de salida. El techo de 65.536 valida la estimación y no se cobra íntegro. `-Accion Tamanos` muestra ambos tamaños y la reserva por modelo. La estimación por bytes admite sobrecarga y no sustituye al tokenizador. Revisar el tope de salida con datos sintéticos antes de reducirlo.

### Arranque y primeras mediciones desde PowerShell

Desde la raíz. Si PowerShell bloquea los scripts locales, usar `Set-ExecutionPolicy -Scope Process RemoteSigned` en esa terminal cuando la política del equipo lo permita. Esta opción se limita a la sesión. Verificar que el manifiesto gratuito esté vigente al iniciar.

```powershell
.\scripts\ia-local.ps1 -Accion Configurar
.\scripts\ia-local.ps1 -Accion Tamanos
.\scripts\ia-local.ps1 -Accion Plan
.\scripts\ia-local.ps1 -Accion Migrar
.\scripts\ia-local.ps1 -Accion Django
```

`Plan` y `Migrar` exigen PostgreSQL de loopback, nombre efectivo `guios_pro_ai_dev` y, en Windows, un backend identificado como proceso PostgreSQL local. Solo permiten aplicar 0016 y 0017 hacia delante. Ejecutar `Migrar` solo después de revisar `Plan`. Django escucha en `127.0.0.1:8000`.

En una segunda terminal, desde la raíz:

```powershell
.\scripts\ia-local.ps1 -Accion Worker
```

Para HU02, iniciar también `procesar_busquedas` en otra terminal desde la raíz:

```powershell
.\scripts\ia-local.ps1 -Accion Busquedas
```

Este worker reclama las búsquedas pendientes y recupera publicaciones de OpenAlex. El administrador sigue iniciando el análisis IA y revisando los vínculos sugeridos.

En una tercera terminal, abrir una medición por vez. Con ella abierta, ejecutar el flujo en Django usando un contexto nuevo y sintético o anonimizado. Para HU02 usar una búsqueda completada sin sugerencias y con más de ocho publicaciones para observar varios lotes. Para HU09 encolar una evaluación con varios subfactores independientes y esperar a que el lote finalice. Para HU10 generar en lote las propuestas habilitadas por suficiencia vigente y dejar la confirmación a HU11. Pulsar Intro en el observador cuando termine cada flujo.

```powershell
.\venv\Scripts\python.exe -m benchmarks.local_ia medir --hu HU02 --salida ".\hu02-$(Get-Date -Format yyyyMMdd-HHmmss).json"
.\venv\Scripts\python.exe -m benchmarks.local_ia medir --hu HU09 --salida ".\hu09-$(Get-Date -Format yyyyMMdd-HHmmss).json"
.\venv\Scripts\python.exe -m benchmarks.local_ia medir --hu HU10 --salida ".\hu10-$(Get-Date -Format yyyyMMdd-HHmmss).json"
```

El observador no llama a modelos. Reporta el tiempo observado total, la ventana entre el primer intento y el último cierre, el tiempo con al menos una reserva abierta y el tiempo fuera de la ventana de IA. Este último incluye interacción humana, cola previa y trabajo local antes y después del HTTP. En la segunda tanda histórica, la ventana de IA duró unos 10,47 s dentro de 81,62 s observados. También exporta intentos, reservas y cargos, concurrencia, distribución y errores. Evitar otro tráfico de la misma operación durante la ventana. El pico mide solapamiento local.

### Caso P2

Los tres reportes históricos conservaron conformidad de contrato y fallo de calidad, pero no la pregunta emitida. El benchmark de preguntas enviaba `fuentes` y `descartadas`, mientras que HU09 envía `evidencias` y `preguntas_descartadas`. Se corrigió esa diferencia en P1 y P2. Para P2, la evidencia dice explícitamente que existe autenticación LDAP, así que sigue siendo correcto exigir una lista vacía. No se cambió el criterio ni la instrucción productiva. La causa atribuible al modelo o a la instrucción queda pendiente de una nueva ejecución con el formato corregido.

```powershell
.\venv\Scripts\python.exe -m benchmarks.ia --modo real --proveedores gemini cloudflare --casos P2 --autorizacion .\autorizacion-gratuita.json --salida ".\benchmark-p2-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

### Recuperación y referencias de límites

La revisión local encontró las claves y los modelos de Gemini, Cohere, Groq y OpenRouter bajo sus nombres canónicos. Cloudflare tenía modelo e ID de cuenta válido por formato, pero su token estaba en `GUIOS_AI_CLOUDFLARE_API_TOKEN`. El código anterior buscaba `GUIOS_AI_CLOUDFLARE_API_KEY`, así que omitía Cloudflare antes del HTTP. Ambos nombres funcionan ahora, con prioridad para `_API_KEY`. Verificar que el token esté activo, limitado a la cuenta del ID y tenga Workers AI Read y Edit según la guía REST. El formato local no verifica permisos ni acceso al modelo. [Cloudflare Workers AI REST](https://developers.cloudflare.com/workers-ai/get-started/rest-api/)

| Proveedor y modelo | Referencia pública de gratuidad | Dato que debe comprobar el operador |
|---|---|---|
| Gemini `gemini-3.5-flash-lite` | Entrada y salida gratuitas en Free Tier. Google aplica RPM, TPM de entrada y RPD por proyecto. [Precios](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite) · [Límites](https://ai.google.dev/gemini-api/docs/rate-limits) | En AI Studio, confirmar proyecto Free Tier con facturación desactivada y copiar RPM, TPM y RPD activos del modelo exacto. |
| Cohere `command-a-plus-05-2026` | Command A+ Trial publica 20 RPM y Cohere documenta 1.000 llamadas mensuales para claves de evaluación. [Modelo](https://docs.cohere.com/v1/docs/command-a-plus) · [Límites](https://docs.cohere.com/v2/docs/rate-limits) | Confirmar tipo de clave, titular del cupo mensual, consumo restante y límites adicionales aplicables. Usar `rp31d` para limitar el número de solicitudes en 31 días móviles. Autorizar por separado el tratamiento de datos de cada operación. |
| Groq `openai/gpt-oss-120b` | Tabla Free Plan consultada: 30 RPM, 8.000 TPM, 1.000 RPD y 200.000 TPD. [Límites](https://console.groq.com/docs/rate-limits) | Confirmar Free Plan, permisos del modelo en organización y proyecto, condiciones del modelo y límites efectivos en **Limits**. Si hay topes separados de entrada y salida, reservar conservadoramente con el menor hasta disponer de contadores separados. |
| Cloudflare `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Workers Free incluye 10.000 Neurons/día. Cloudflare publica 300 RPM como límite general de generación de texto. [Precios](https://developers.cloudflare.com/workers-ai/platform/pricing/) · [Límites](https://developers.cloudflare.com/workers-ai/platform/limits/) | Confirmar que el token corresponde a la cuenta Workers Free, que hay cupo disponible y que el modelo está habilitado. Usar `unidades_diarias` y un máximo conservador por llamada. Con los coeficientes publicados, calcular `unidades_por_intento` redondeando hacia arriba `(26668 × máximo de tokens de entrada + 204805 × máximo de tokens de salida) / 1000000`, incluyendo plantilla y margen verificados. |
| OpenRouter `google/gemma-4-26b-a4b-it:free` | Referencia del nivel gratuito base: 20 RPM y 50 RPD. Los metadatos públicos listan `google-ai-studio` con precio cero para entrada y salida. [Modelos gratuitos](https://openrouter.ai/collections/free-models) · [Metadatos del endpoint](https://openrouter.ai/api/v1/models/google/gemma-4-26b-a4b-it:free/endpoints) | Confirmar el contador diario mediante `--cuota` y el RPM aplicable. Mantener el modelo exacto, el endpoint fijado y sin recarga automática. Un saldo de $0 no indica cuántas llamadas gratuitas quedan. |

Las cifras públicas de esta tabla son referencias. Configurar los límites efectivos del cupo de cada cuenta y descontar capacidad usada por otras aplicaciones que compartan ese cupo. Usar `null` solo si se confirmó que el límite no aplica. Una unidad sin política completa queda deshabilitada. Cloudflare ya forma parte del perfil local. Groq y OpenRouter siguen fuera hasta recuperar el acceso y validar sus contratos.

### Sondas y recuperación manual

```powershell
# Cloudflare: verifica nombre de variable, formato de cuenta y manifiesto sin red.
.\venv\Scripts\python.exe -m benchmarks.sonda_ia cloudflare --autorizacion .\autorizacion-gratuita.json
# Groq: un POST mínimo. Los códigos conocidos se traducen sin imprimir el cuerpo.
.\venv\Scripts\python.exe -m benchmarks.sonda_ia groq --autorizacion .\autorizacion-gratuita.json --ejecutar
# OpenRouter: metadato autenticado de cuota, sin inferencia.
.\venv\Scripts\python.exe -m benchmarks.sonda_ia openrouter --autorizacion .\autorizacion-gratuita.json --cuota
# OpenRouter: un POST si queda cupo y el endpoint autorizado publica precio cero.
.\venv\Scripts\python.exe -m benchmarks.sonda_ia openrouter --autorizacion .\autorizacion-gratuita.json --ejecutar
# Cloudflare: un POST solo después de verificar el alcance del token y Workers Free.
.\venv\Scripts\python.exe -m benchmarks.sonda_ia cloudflare --autorizacion .\autorizacion-gratuita.json --ejecutar
```

Groq usa `POST https://api.groq.com/openai/v1/chat/completions`, autenticación Bearer, JSON y `max_completion_tokens`. GPT-OSS 120B admite el modo JSON Object. El 403 guardado carece de un código reconocido. La sonda distingue los bloqueos documentados de organización o proyecto y reconoce condiciones del modelo pendientes. Si falta un código reconocido, comprobar la cuenta y las restricciones regionales o del proxy, incluido el entorno donde se hizo la solicitud. [API de Groq](https://console.groq.com/docs/api-reference) · [Permisos de modelo](https://console.groq.com/docs/model-permissions)

En OpenRouter, un contador diario de cero evita el POST. Un 429 con `provider_code` apunta al proveedor ascendente; un 429 con los encabezados de límite de OpenRouter apunta a la plataforma. Sin esos indicios el origen queda indeterminado. La sonda valida los precios públicos antes del POST; el adaptador fija `only`, `allow_fallbacks: false` y precio máximo cero para entrada, salida y solicitud. [Límites y 429](https://openrouter.ai/docs/api/reference/limits)

Una vez comprobado el acceso y usando la misma terminal:

```powershell
.\venv\Scripts\python.exe -m benchmarks.ia --modo real --proveedores groq cloudflare openrouter --autorizacion .\autorizacion-gratuita.json --salida ".\benchmark-recuperacion-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

Ejecutar el mantenimiento contra la misma base local verificada. Tras un timeout, las tareas quedan inciertas sin fallback. Consultar identificadores y metadatos de intento para correlacionar la ejecución con el proveedor. Si no se puede comprobar que el intento terminó, conservar el bloqueo y continuar por el flujo manual. El comando de reapertura no sustituye esa comprobación y el cooldown de la unidad puede seguir vigente.

```powershell
.\venv\Scripts\python.exe manage.py mantener_planificacion_ia
.\venv\Scripts\python.exe manage.py shell -c "from apps.data.models import IntentoIA; print(list(IntentoIA.objects.filter(tarea__estado='INCIERTA').order_by('-pk').values('tarea_id','proveedor','modelo','operacion','inicio','error')[:30]))"
# Solo después de verificar el término del intento:
.\venv\Scripts\python.exe manage.py mantener_planificacion_ia --confirmar-termino ID_TAREA
```

La huella de deduplicación conserva el ámbito de búsqueda o evaluación, operación y contexto completo. El caché también comprueba el actor que solicitó la respuesta. Otra cuenta no puede recuperar esa respuesta ni provocar un segundo envío del mismo trabajo mientras esté reservado o reutilizable. Las salidas guardadas antes de añadir esta comprobación carecen del marcador de actor y se omiten hasta vencer.

## Ejecutar el benchmark aislado

Desde la raíz del repositorio, con el entorno Python del proyecto activo:

```powershell
python -m unittest benchmarks.test_ia apps.external_services.tests.test_api_ia -v
python -m benchmarks.ia --modo mock --salida benchmark-mock
python -m benchmarks.ia --modo mock --proveedores cohere cloudflare --salida benchmark-subconjunto
```

Cada proveedor usa el modelo y la clave de `GUIOS_AI_<PROVEEDOR>_MODEL` y `GUIOS_AI_<PROVEEDOR>_API_KEY` en modo real. Los identificadores son `GEMINI`, `GROQ`, `COHERE`, `CLOUDFLARE` y `OPENROUTER`. Cloudflare también requiere `GUIOS_AI_CLOUDFLARE_ACCOUNT_ID`. En modo mock se usan modelos ficticios y se omite la lectura de `.env`.

La ejecución real requiere revisar, para cada modelo, su ficha oficial vigente, compatibilidad JSON, plan y cuenta o clave configurada. Verificar que el acceso se corte al agotar el nivel gratuito y que no exista cobro de excedentes. El programa exige una constancia local de esa revisión antes de enviar solicitudes y valida coincidencia exacta de modelo, plan, dominio oficial y vigencia. La constancia la llena el operador y carece de secretos. La herramienta no puede consultar ni certificar el estado de facturación de la cuenta. Los planes admitidos son `gemini-free-tier`, `groq-free`, `cohere-trial`, `workers-free` y `openrouter-free`. Para OpenRouter usar un modelo concreto con sufijo `:free` y fijar un solo endpoint gratuito mediante `endpoint_openrouter`. Para los demás proveedores omitir ese campo.

Ejemplo de estructura para `autorizacion-gratuita.json`, con valores ficticios que deben sustituirse después de verificar:

```json
[
  {
    "proveedor": "gemini",
    "modelo": "modelo-exacto-verificado",
    "plan": "gemini-free-tier",
    "fuente_oficial": "https://ai.google.dev/gemini-api/docs/pricing",
    "verificado": "2026-11-26",
    "vence": "2026-11-26",
    "sin_cargos_ni_excedentes": true
  }
]
```

```powershell
python -m benchmarks.ia --modo real --proveedores gemini --autorizacion autorizacion-gratuita.json --salida benchmark-real-gemini
```

La CLI exporta `resultados.json` y `resultados.csv` por caso. Mide latencia, tokens disponibles, JSON, contrato, IDs válidos y coincidencia con la respuesta esperada. La calidad automática usa IDs, clase o estado y temas de preguntas. La pertinencia de las justificaciones requiere evaluación humana. La ejecución es serial y, tras un 429, omite los casos restantes de ese proveedor durante la corrida. Una nueva corrida requiere otro directorio de salida.

## Auditoría y entrega

- El registro público crea exclusivamente cuentas de Decisor. Revisar las cuentas administrativas preexistentes antes de exponer una instalación antigua.
- Los cambios de vínculos de evidencia y de nombres de documentos toman el mismo bloqueo de evaluación que la validación final de HU09/HU10/HU11. La prueba de duplicación de DOCX usa los mismos bytes para evitar variaciones de metadatos ZIP.
- El diagnóstico de admisión funciona sin red. El benchmark real de OpenRouter comprueba el endpoint exacto y sus precios públicos antes de inferencia. Conserva el tope de precio cero y el fallback remoto deshabilitado. OpenRouter sigue fuera del perfil operativo.
- El cierre exige que la reserva siga abierta y corresponda al mismo modelo, tarea y unidad. Ante una lectura HTTP incompleta se mantiene el cargo conservador y la tarea queda incierta. Cloudflare requiere cupo diario de Neurons. Se aplica el redondeo por categoría tanto a las nuevas reservas como a la conciliación.
- La preparación de cuotas calcula el tamaño de los mensajes una vez por tarea y evita serializar el sobre HTTP para reservas basadas en contexto. El cliente vuelve a comprobar la reserva antes de enviar. La reducción de trabajo local se verificó en el código. Su impacto en milisegundos queda sin medir.
- La cadena existente pasa de 0012 a 0014 por dependencia explícita. 0016 agrega las cuatro tablas de coordinación y 0017 agrega dos campos de cargo anulables. Los intentos anteriores conservan la contabilidad de reserva. Revisar el plan y respaldar la base local antes de aplicar cambios.
- Mantener la verificación de los niveles gratuitos del proyecto y de la cuenta en cada panel. El RPD oficial de Gemini sigue pendiente. El presupuesto interno de 30 solicitudes por 24 horas aplica al piloto y PostgreSQL solo contabiliza el tráfico de esta instalación.
- La suite completa pasó 738 pruebas con Python 3.12.10 y una base PostgreSQL de pruebas exclusiva terminada en `_dev`. Se usó el hash rápido de Django solo durante la ejecución de pruebas. `manage.py check` quedó limpio, `makemigrations --check --dry-run` no detectó cambios y `migrate --plan` quedó vacío en `guios_pro_ai_dev`. HU12 rechazó la evaluación sintética 1 porque sus dos propuestas siguen pendientes de confirmación.

### Limpieza de textos visibles

- Se sustituyeron los códigos HU en enlaces, botones, encabezados, avisos y errores por nombres funcionales. Los textos siguen distinguiendo entre propuestas de IA y valoraciones confirmadas por el decisor.
- Se retiraron comandos y variables de configuración de los avisos de bibliografía, indicadores y revisión. El sondeo de suficiencia muestra «En cola», «En curso» y «Finalizado» sin alterar los estados que controlan el flujo.
- El PDF conserva su contenido metodológico. La regresión comprueba el texto extraído del PDF generado.
- La suite completa pasó 740 pruebas en PostgreSQL temporal, con IA simulada y hash rápido limitado a las pruebas. Se verificaron mensajes dinámicos en cola, al habilitar propuestas, al finalizar y ante un error del servicio.

#### Archivos modificados en la limpieza

```text
apps/application/services/actualizacion_bibliografica/busquedas.py
apps/application/services/actualizacion_bibliografica/versiones.py
apps/application/services/ai.py
apps/application/services/lotes_hu09.py
apps/application/services/preparacion_hu10.py
apps/application/services/revision_humana.py
apps/application/tests/test_actualizacion_bibliografica.py
apps/application/tests/test_hu10_valoracion.py
apps/application/tests/test_informe_documento.py
apps/external_services/api_ia.py
apps/presentation/static/presentation/js/preguntas.js
apps/presentation/static/presentation/js/revision_rapida.js
apps/presentation/templates/presentation/administracion/bibliografia_panel.html
apps/presentation/templates/presentation/administracion/bibliografia_version.html
apps/presentation/templates/presentation/comun/modulo_pendiente.html
apps/presentation/templates/presentation/decisor/preguntas.html
apps/presentation/templates/presentation/decisor/revision_humana.html
apps/presentation/templates/presentation/includes/indicadores_bibliograficos.html
apps/presentation/tests/test_preguntas_interfaz.py
apps/presentation/tests/test_revision_faltantes.py
apps/presentation/tests/test_revision_humana_interfaz.py
apps/presentation/tests/test_vista_indicadores_literatura.py
apps/presentation/views/documentos.py
apps/presentation/views/preguntas.py
apps/presentation/views/revision_humana.py
docs/CONTEXTO_PROYECTO.md
docs/PLAN_IMPLEMENTACION.md
```

### Archivos a incluir en el commit

La lista cubre los cambios de la rama sobre `f0be354`. Los manifiestos, las credenciales y los resultados locales quedan fuera del commit.

```text
.env.example
.gitignore
AGENTS.md
apps/application/services/actualizacion_bibliografica/busquedas.py
apps/application/services/actualizacion_bibliografica/sugerencias_ia.py
apps/application/services/actualizacion_bibliografica/versiones.py
apps/application/services/ai.py
apps/application/services/analisis_preguntas.py
apps/application/services/lotes_hu09.py
apps/application/services/preguntas.py
apps/application/services/preparacion_hu10.py
apps/application/services/revision_humana.py
apps/application/services/suficiencia.py
apps/application/services/tareas_ia.py
apps/application/tests/test_actualizacion_bibliografica.py
apps/application/tests/test_document_service.py
apps/application/tests/test_hu10_valoracion.py
apps/application/tests/test_informe_documento.py
apps/application/tests/test_piloto_hu09_hu10.py
apps/application/tests/test_revision_humana.py
apps/data/management/commands/cargar_piloto_hu09_hu10.py
apps/data/management/commands/mantener_planificacion_ia.py
apps/data/migrations/0016_planificacion_ia.py
apps/data/migrations/0017_reconciliacion_ia.py
apps/data/models/__init__.py
apps/data/models/planificacion_ia.py
apps/external_services/ai_errors.py
apps/external_services/api_ia.py
apps/external_services/clientes_ia.py
apps/external_services/planificador_ia.py
apps/external_services/proveedor_ia.py
apps/external_services/tests/fixtures_ia.py
apps/external_services/tests/test_proveedor_ia.py
apps/presentation/forms.py
apps/presentation/static/presentation/js/preguntas.js
apps/presentation/static/presentation/js/revision_rapida.js
apps/presentation/templates/presentation/acceso/registro.html
apps/presentation/templates/presentation/administracion/bibliografia_busqueda.html
apps/presentation/templates/presentation/administracion/bibliografia_panel.html
apps/presentation/templates/presentation/administracion/bibliografia_version.html
apps/presentation/templates/presentation/comun/modulo_pendiente.html
apps/presentation/templates/presentation/decisor/preguntas.html
apps/presentation/templates/presentation/decisor/revision_humana.html
apps/presentation/templates/presentation/includes/indicadores_bibliograficos.html
apps/presentation/tests/test_lotes_hu09.py
apps/presentation/tests/test_preguntas_interfaz.py
apps/presentation/tests/test_registro.py
apps/presentation/tests/test_revision_faltantes.py
apps/presentation/tests/test_revision_humana_interfaz.py
apps/presentation/tests/test_vista_indicadores_literatura.py
apps/presentation/views/access.py
apps/presentation/views/documentos.py
apps/presentation/views/evidencia_carga.py
apps/presentation/views/preguntas.py
apps/presentation/views/revision_humana.py
benchmarks/__init__.py
benchmarks/autorizar_google.py
benchmarks/autorizar_typhoon.py
benchmarks/casos_ia.py
benchmarks/clientes_ia.py
benchmarks/cuotas_google.py
benchmarks/ia.py
benchmarks/local_ia.py
benchmarks/sonda_ia.py
benchmarks/test_google_multimodelo.py
benchmarks/test_ia.py
benchmarks/test_local_ia.py
benchmarks/test_sonda_ia.py
benchmarks/test_typhoon.py
config/ia-local.json
config/ia-politicas-modelos-candidatos.json
config/settings.py
diag_ia.py
docs/CONTEXTO_PROYECTO.md
docs/PLAN_IMPLEMENTACION.md
README.md
scripts/ia-local.ps1
```
