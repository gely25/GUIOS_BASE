# Contexto técnico — GUIOS PRO

Actualización: 26 de noviembre de 2026. Repositorio: https://github.com/gely25/GUIOS_BASE.

## Base de referencia y alcance
- ZIP anterior: `GUIOS_BASE-main.zip`, commit `34acf296020b4d47fbd17718d27b026bdf243ec3`.
- ZIP actualizado: `GUIOS_BASE-main(1).zip`, commit `f0be35401d3d6e7a00c4d41fdbcdddd75493edad` (PR #42); 309 archivos. Se usa como referencia estática, no como garantía de que `main` siga en ese commit.
- Revisión local en `feature/optimizacion-ia`, con HEAD `f0be354`. Los hallazgos de IA corresponden a los archivos de esa rama.
- El documento maestro del 25 de noviembre es histórico. Su descripción de Ollama y una sola API corresponde a la versión previa, no al estado actualizado.
- La línea base estática corresponde al ZIP. El piloto posterior comprobó Gemini y Cloudflare mediante benchmark y HU02, HU09 y HU10 con PostgreSQL local. Las mediciones cubren únicamente los casos ejecutados.

## Arquitectura
Monolito modular Django 5.2/Python 3.12/PostgreSQL 17 con pgvector. Las migraciones 0016 y 0017 están aplicadas en la base local del piloto. Instalación y arranque de Django, HU02 y HU09 en el [README](../README.md). Capas en `apps/presentation`, `apps/application`, `apps/business_rules`, `apps/data` y `apps/external_services`. Configuración en `config/settings.py`.

### Flujos
- HU02: búsqueda de bibliografía con OpenAlex, sugerencias de pertinencia IA bajo demanda y aprobación humana.
- HU07/HU08: extracción y fragmentación de PDF/DOCX/XLSX, recuperación de evidencias. `RetrievalService` utiliza vectores deterministas de hashing de 1536 dimensiones, no embeddings neuronales. pgvector almacena y compara vectores.
- HU09: generación de preguntas y análisis de suficiencia; referencias `E:` y `R:`; máximo de tres rondas adaptativas; reutilización mediante huella de contexto; revisión manual cuando corresponde. Worker `python manage.py procesar_hu09`; modelo `LoteHU09` y reclamación de trabajos con bloqueo de base de datos.
- HU10: propuesta preliminar 1–4 (1 no cumple, 2 desconozco/no sé, 3 cumple parcialmente, 4 cumple), justificación y referencias. Ejecuta propuestas independientes en paralelo y valida el contexto antes de persistir.
- HU11: el decisor confirma, modifica o registra valoraciones manualmente. Solo las confirmadas alimentan PM, FODA y recomendación. HU12–HU15 incluyen resultados, recomendaciones, informes e historial. La IA no reemplaza las reglas metodológicas.

## Inventario de archivos importantes
| Ruta | Responsabilidad |
|---|---|
| `apps/external_services/proveedor_ia.py` | Administrador, `obtener_proveedor(tipo)`, fallback secuencial y trazabilidad |
| `apps/external_services/planificador_ia.py` | Admisión, deduplicación, cuotas y recuperación mediante PostgreSQL |
| `apps/external_services/api_ia.py` | `APIJSON`, `APIPreguntas`, `APISuficiencia`, `APIValoracion`, `APIBibliografia`; transporte HTTP y validación |
| `apps/external_services/ai_contracts.py` | Cuatro esquemas e instrucciones (`ESQUEMA_*`, `INSTRUCCION_*`) |
| `apps/external_services/ai_errors.py` | `AnalisisNoDisponible` |
| `apps/external_services/tests/test_proveedor_ia.py` | Pruebas del enrutador vigente |
| `apps/application/services/actualizacion_bibliografica/sugerencias_ia.py` | HU02, lotes de publicaciones |
| `apps/application/services/suficiencia.py` | HU09, análisis vigente y referencias |
| `apps/application/services/lotes_hu09.py` | Orquestación de lotes HU09 |
| `apps/data/management/commands/procesar_hu09.py` | Worker HU09 |
| `apps/application/services/ai.py` | HU10, propuestas y persistencia |
| `apps/application/services/preparacion_hu10.py` | Preparación de contexto |
| `apps/application/services/retrieval.py` | Recuperación documental |
| `config/settings.py`, `.env.example` | Configuración del entorno |
| `diag_ia.py` | Lista modelos y operaciones admitidos localmente sin enviar solicitudes |
| `benchmarks/ia.py` | Benchmark aislado de los cuatro contratos con mocks o ejecución real autorizada |

## IA anterior a la fase 2 (histórico del ZIP)
Gemini, OpenAI y Groq mediante cliente Chat Completions compatible; una clave y modelo por proveedor. `ProveedoresParalelos` usa un `ThreadPoolExecutor` de 12 hilos por proceso y envía la misma entrada a todos los proveedores configurados; acepta la primera respuesta válida e intenta cancelar las demás. Las solicitudes ya iniciadas pueden continuar y consumir cuota. `GUIOS_AI_TIMEOUT` por defecto: 15 segundos. Las claves actuales siguen la forma `GUIOS_AI_<PROVEEDOR>_API_KEY` y los modelos `GUIOS_AI_<PROVEEDOR>_MODEL`. Cliente con `LIMITE_ENTRADA=16000`, `LIMITE_RESPUESTA=65536`, generación JSON y temperatura 0. No confundir esos límites con tokens.

Ollama fue retirado en el PR #42. En el ZIP todavía faltaban cuotas, cooldown y selección por aptitud. La identificación del último proveedor era mutable.

## Administrador distribuido

Gemini tiene prioridad provisional. Cohere requiere habilitación por operación, autorización de gratuidad y aprobación para tratar los datos de esa operación. Groq, Cloudflare y OpenRouter están registrados y sus operaciones quedan vacías por defecto. El registro excluye a OpenAI.

El planificador usa PostgreSQL para las reservas, cooldown, credenciales bloqueadas, cuotas por unidad real e intentos en curso. Identifica el trabajo con una huella HMAC de la operación, el ámbito de negocio, la versión y la entrada. Una restricción parcial admite como máximo una reserva abierta por tarea. Las tablas de coordinación guardan estado y métricas sin claves ni entradas. Solo se conserva temporalmente la salida validada para reutilizarla al persistir o reintentar una operación de negocio.

Se ejecutan en paralelo únicamente lotes bibliográficos HU02, subfactores independientes de un lote HU09 y propuestas independientes de HU10. Se conserva el orden de los resúmenes, las comprobaciones de vigencia antes de escribir y la revisión humana. La admisión permite varias solicitudes de tareas distintas en la misma unidad si hay capacidad. Cada tarea mantiene su fallback secuencial y cada transacción de admisión termina antes del HTTP.

El bloqueo 401/403 persiste entre procesos y reinicios. Ante 429 y fallos transitorios, se respeta el mayor plazo entre el cooldown configurado y `Retry-After`. Timeout, fallo de red ambiguo, 408, 502, 504 y abandono de una reserva enviada dejan la tarea incierta y sin fallback. La reserva de capacidad puede vencer para otras tareas, pero el mismo trabajo sigue bloqueado hasta confirmar externamente el término.

## Piloto local Gemini y Cloudflare

El operador confirmó 8/8 contratos válidos para Cloudflare Workers Free tras recuperar el acceso con el alias `GUIOS_AI_CLOUDFLARE_API_TOKEN`. Gemini también obtuvo 8/8. El perfil local compartido inicia con 3 reservas en Gemini y 2 en Cloudflare, 12 y 30 RPM internos, respectivamente. Gemini tiene un tope de prueba de 30 peticiones en 24 horas móviles mientras se desconoce el RPD oficial. Cohere tiene contratos válidos y queda fuera por condiciones de uso pendientes. Groq sigue fuera por 403 text/plain de la API y OpenRouter por 429 pese a que el contador mostraba 50 solicitudes disponibles.

El piloto reserva según los bytes UTF-8 de los mensajes decodificados, margen de plantilla y tope de generación. La medición usa los mismos mensajes por modelo y operación que construye el transporte. Los bytes del sobre HTTP se reportan por separado. Los intentos nuevos con contrato válido y uso coherente pueden sustituir la reserva por un cargo final. Cloudflare requiere desglose exacto y redondea hacia arriba entrada y salida por separado con sus coeficientes de Neurons. Cuando el uso es desconocido, el cargo mantiene una cota conservadora. El historial anterior a 0017 conserva sus cargos.

En dos tandas reales de HU02 se registraron 14 intentos, diez de Gemini y cuatro de Cloudflare. PostgreSQL registró 35.914 tokens observados de 204.284 reservados, más 3.010 Neurons contabilizados bajo la política previa. La tanda de 50 publicaciones registró un pico de cinco reservas y completó todos los intentos sin fallbacks. El worker bibliográfico se inicia con `scripts/ia-local.ps1 -Accion Busquedas`; recupera las publicaciones en cola. El análisis IA sigue siendo una acción del administrador.

### Registro multimodelo

El proveedor puede registrar varios IDs con una sola clave y una sola unidad real de cuota. Cada modelo adicional necesita su propia política, operaciones explícitas, perfil validado y autorización operativa. Todos los intentos de esa unidad siguen contando para el proyecto y se comprueba también el límite local del modelo. Si la independencia de los límites es incierta, la unidad usa el menor límite configurado en cada dimensión. Un bloqueo de credencial o cooldown del proyecto afecta a todos sus modelos. El identificador de deduplicación de la tarea permanece independiente del modelo.

Gemma 4 26B, Gemma 4 31B y Gemini 3.1 Flash-Lite se incorporaron al benchmark como candidatos. Permanecen fuera del perfil operativo, que sigue usando Gemini 3.5 Flash-Lite y Cloudflare. El benchmark usa una constancia separada, solicitudes sintéticas secuenciales y el transporte HTTPS de Google. Gemma produce texto JSON guiado por el prompt; Gemini 3.1 solicita JSON nativo. Ambos pasan por el contrato local estricto.

Typhoon `typhoon-v2.5-30b-a3b-instruct` tuvo una sonda preliminar HTTP 200 en 1,705 s y falló después en el benchmark real con transporte incierto. Se mantiene deshabilitado para operación. Su adaptador de laboratorio queda limitado a casos sintéticos autorizados. Z.AI `glm-4.7-flash` sigue fuera tras HTTP 429.

El piloto HU09/HU10 usa dos subfactores aislados y declaraciones ficticias visibles como fuentes `R:`. La evaluación sintética 1 completó HU09 y HU10. PostgreSQL confirmó suficiencia vigente para ODF y LDAPv3, con propuestas de 4/4 y 1/4, respectivamente. Ambas siguen pendientes de confirmación humana. Las citas `R:1` y `R:2` identifican declaraciones del decisor simulado.

Cuando finaliza un lote HU09, el sondeo actualiza contadores, disponibilidad y acciones HU10 sin sustituir borradores. El servidor conserva las comprobaciones de vigencia y la deduplicación por tarea. HU10 solo prepara todo el contexto para seleccionar pendientes. Cada comprobación individual posterior se limita al subfactor correspondiente.

### Auditoría de entrega

El registro público asigna el rol Decisor en el servidor. Las altas administrativas requieren acceso al módulo de gestión autenticado. HU12 y HU13 exigen valor confirmado o modificado por el propietario, auditoría de la decisión y fuentes vigentes. Los dos valores del piloto permanecen pendientes.

El cierre de IA requiere una reserva abierta de la misma tarea, unidad y modelo. Una lectura HTTP truncada bloquea el reenvío automático de la tarea como transporte incierto. Cloudflare solo se admite con cupo diario de Neurons y reserva el redondeo de entrada y salida. La vigencia del manifiesto y el perfil limitan los modelos operativos. La gratuidad de la cuenta y el cupo consumido por aplicaciones externas se verifican en los paneles del proveedor.

### Textos de interfaz para la entrega

Las pantallas presentan los pasos como Preguntas y suficiencia, Valoración preliminar con IA, Validación humana, Resultados e Informe. Los códigos HU y los estados de la cola se conservan para el enrutamiento, las pruebas y la trazabilidad interna. El sondeo usa las mismas etiquetas visibles que la página inicial. Los avisos para el usuario describen la acción disponible o remiten a soporte. Los comandos de operación siguen en la documentación técnica.

## Diagnóstico inicial de reutilización
| Archivo | Reutilizar | Modificar en fases posteriores |
|---|---|---|
| `proveedor_ia.py` | Interfaz `obtener_proveedor(tipo)`, registro de adaptadores y validación de configuración | Retirar OpenAI, `ProveedoresParalelos` y su ejecutor. Seleccionar por operación, aplicar fallback secuencial y atribuir cada resultado a su intento sin depender de estado mutable compartido. |
| `api_ia.py` | Transporte HTTPS para APIs compatibles con Chat Completions, validación JSON y adaptadores por operación, incluidos cupos, IDs permitidos y coherencia de suficiencia | Conservar el estado HTTP, distinguir fallos de entrada, autenticación, cuota, transporte y contrato, y extraer solo metadatos permitidos como `Retry-After`. |
| `ai_contracts.py` | Los cuatro esquemas e instrucciones como línea base del benchmark | Mantener los contratos durante el cambio de enrutamiento. |
| `ai_errors.py` | `AnalisisNoDisponible` como error compatible con los servicios y su modo manual | Añadir clasificación interna para decidir fallback y cooldown sin interpretar mensajes de texto. |
| `config/settings.py` y `.env.example` | Lectura desde el entorno y plantilla sin claves reales | Retirar variables de OpenAI y actualizar los comentarios de la carrera. Documentar los parámetros de plazo, intentos, concurrencia, cuotas y cooldown cuando se definan. |
| `diag_ia.py` | Idea de una prueba mínima de conectividad y latencia | Sustituir el sondeo de Gemini con modelos fijos y llamadas al importar por una entrada explícita de benchmark aislado que cubra los cuatro contratos. |

Gemini y Groq ya tienen integración de transporte y quedan como candidatos sujetos a verificación oficial de gratuidad, disponibilidad, cuotas y tratamiento de datos. Los modelos del ejemplo y de `diag_ia.py` son referencias de configuración sin validación vigente. OpenAI queda excluido como proveedor. Las rutas de compatibilidad de Gemini y Groq que contienen `openai` identifican el protocolo y usan los servicios de Google y Groq.

## Objetivo acordado
Usar exclusivamente APIs gratuitas con presupuesto de **$0**, tanto en el benchmark como en producción. Excluir OpenAI como proveedor y trabajar sin Ollama, modelos generativos locales ni Docker. Si se agota la capacidad gratuita, recurrir a otro proveedor gratuito elegible mediante fallback secuencial o al flujo manual.

Distribuir operaciones independientes entre proveedores aptos con concurrencia acotada. Cada tarea lógica admite un intento activo desde la aplicación. Ante fallos recuperables o respuestas inválidas, aplicar fallback secuencial y cooldown por unidad de cuota real. Un timeout local puede dejar procesamiento remoto activo. Usar calidad, velocidad y estabilidad medidas por operación para decidir la asignación. En el benchmark, comparar casos equivalentes en ejecuciones separadas. Preservar la trazabilidad, la validación de referencias, la revisión humana y las reglas de GUIOS, incluidas las valoraciones confirmadas que alimentan PM y FODA.
