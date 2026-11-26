# GUIOS PRO: revisión de evidencia y proveedor de IA configurable

## Entrega

Estos cambios parten del ZIP de `origin/main` entregado el 23 de noviembre de 2026.
No incluyen `.env`, secretos, base de datos ni historial Git. Se mantiene el mecanismo de
validación humana y las reglas de cálculo originales.

## Paso 4: interfaz HU11

- Navegación por dimensiones, factores y subfactores; búsqueda y filtro de estados.
- Panel con la propuesta preliminar de IA (si existe), su justificación, la evidencia
  documental vinculada y las declaraciones del decisor, diferenciadas.
- Área de información faltante y acceso a HU09 para responder preguntas o analizar suficiencia.
- Diálogo para confirmar propuesta, modificarla o registrar una valoración manual.
- Guardado de borradores, comprobación de versiones, reapertura justificada, revisión
  de borradores por lote, historial y navegación anterior/siguiente conservados.
- Progreso real del lote HU09 cuando está en curso (por subfactores, sin simular un
  porcentaje de documentos); diseño adaptable a pantallas pequeñas.
- Se mantiene la comprobación de propiedad, roles, exclusión de IR 1, CSRF y la
  regla: solo un valor confirmado contribuye a resultados.

## IA con proveedores externos

HU02, HU09 y HU10 pueden usar Gemini, OpenAI y Groq. Configure para cada proveedor
una clave y un modelo mediante `GUIOS_AI_GEMINI_API_KEY` /
`GUIOS_AI_GEMINI_MODEL`, `GUIOS_AI_OPENAI_API_KEY` / `GUIOS_AI_OPENAI_MODEL` y
`GUIOS_AI_GROQ_API_KEY` / `GUIOS_AI_GROQ_MODEL`. Se consultan en paralelo y se usa
la primera respuesta válida según el contrato de la aplicación. `GUIOS_AI_TIMEOUT`
limita cada solicitud; las llamadas que ya empezaron pueden continuar hasta ese límite.
Los endpoints HTTPS están fijados por proveedor. Consulte `.env.example` para los
nombres de variables y modelos de ejemplo.

Al usar HU09/HU10, los fragmentos de evidencia y las respuestas vinculadas se envían
a cada proveedor configurado; HU02 envía títulos y resúmenes bibliográficos. Revise las
condiciones de privacidad, límites y facturación de cada proveedor. No se incluyen
claves en el repositorio. La disponibilidad y los costes dependen de las cuentas
configuradas.

La recuperación documental principal sigue usando `RetrievalService` y pgvector.
El filtro opcional local de similitud semántica de preguntas se retiró; el filtrado
conservador de preguntas similares sigue siendo textual. Si las APIs fallan, se
muestra un error controlado y la revisión manual sigue disponible.

## Prueba en tu equipo

Trabaja en una **copia independiente**. Copia tu archivo `.env` local de pruebas
(sin compartirlo) y activa tu entorno virtual existente.

```powershell
python manage.py check
python manage.py test apps.presentation.tests.test_revision_humana_interfaz apps.application.tests.test_hu10_valoracion apps.external_services.tests.test_api_ia
```

La prueba manual debe cubrir: un subfactor con propuesta IA, otro sin propuesta,
confirmación, modificación, borrador, reapertura y bloqueo de factores IR=1. Para
probar el proveedor remoto utiliza primero un documento de prueba que no contenga
datos personales y una clave de API válida. Para ejecutar el análisis masivo:

```powershell
python manage.py procesar_hu09 --once
```

Este trabajador necesita ejecutarse también en el despliegue si se usa la cola HU09.

## Verificaciones realizadas al preparar esta entrega

- `python -m compileall` sobre `apps` y `config`: correcto.
- `node --check` sobre el JavaScript de HU11: correcto.
- `python -m unittest apps.external_services.tests.test_api_ia`: **6 pruebas correctas**
  utilizando respuestas HTTP simuladas, sin contacto con servidores externos.
- Equilibrio de bloques de la plantilla Django: correcto (verificación estática).

**No se pudo ejecutar `manage.py check` ni la suite completa de Django aquí:** el
entorno de preparación no dispone de Django y no tiene acceso a paquetes para
instalarlo. Tampoco se ha probado la API con una clave real ni se ha comprobado
visualmente la pantalla con un servidor Django activo. Es una implementación
lista para probar e integrar tras la validación local, no un despliegue validado.

## Integración recomendada

No sobrescribas tus ramas anteriores ni apliques un ZIP a `main` directamente.
Crea una rama de integración a partir de la versión de `main` que te facilitó
este ZIP y prueba allí. La alternativa es extraer el ZIP completo corregido
en una carpeta nueva y copiar de manera privada el `.env` de prueba.
