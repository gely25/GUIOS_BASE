# AGENTS.md — GUIOS PRO

## Alcance
GUIOS PRO es una aplicación Django de apoyo a la decisión de adopción FLOSS mediante la metodología GUIOS. Lee `docs/CONTEXTO_PROYECTO.md` para entender la arquitectura y `docs/PLAN_IMPLEMENTACION.md` para conocer el orden de trabajo. Ambos documentos distinguen hechos comprobados y propuestas pendientes.

## Decisiones obligatorias
- Usar exclusivamente APIs gratuitas con presupuesto de $0 en benchmark y producción. Excluir OpenAI como proveedor. Verificar con documentación oficial vigente cada modelo y que la cuenta o clave utilizada no pueda generar cargos ni excedentes antes de llamar a la API. Si se agota capacidad gratuita, usar fallback hacia otro proveedor gratuito elegible o continuar manualmente.
- Usar PostgreSQL y pgvector en el entorno objetivo. Excluir Ollama, modelos generativos locales, Docker y Redis del desarrollo y despliegue objetivo. Conservar los archivos históricos ajenos a la tarea.
- Eliminar la competencia entre proveedores: no enviar una misma operación a varias APIs simultáneamente, ni usar hedging. Cada tarea lógica tiene como máximo un intento activo desde la aplicación. Un timeout no garantiza que la API remota haya detenido su procesamiento.
- Distribuir tareas independientes entre proveedores/modelos aptos, con concurrencia acotada. Priorizar calidad, velocidad y estabilidad medidas por operación. Usar fallback secuencial ante fallos recuperables o respuestas inválidas y cooldown por unidad de cuota real.
- Conservar HU02, HU09, HU10, HU11, reglas de GUIOS, contratos de respuesta, trazabilidad, validación de referencias y revisión humana. No sustituir PM/FODA ni cálculos metodológicos por IA.
- No asumir que una API key equivale a una cuota independiente; agrupar por unidad de cuota real. No evadir límites de proveedores. No registrar claves, tokens de autenticación ni documentos confidenciales.
- No fijar proveedor ganador, modelo, peso ni cuotas sin benchmark y validación de disponibilidad. Diferenciar Groq de Grok/xAI.
- Trabajar con PostgreSQL y pgvector; reutilizar los workers y mecanismos de persistencia existentes antes de introducir infraestructura nueva.
- Usar la misma configuración de perfiles, unidades de cuota y cupos verificados en todos los procesos. La admisión y la deduplicación se reservan en PostgreSQL; cerrar la transacción antes de llamar al proveedor. Sin una política de cuota verificada, el planificador no admite solicitudes.
- Ante timeout, respuesta de pasarela ambigua o reserva abandonada que pudo enviar una solicitud, mantener la tarea en estado incierto. Reabrirla solo tras confirmar externamente el fin del intento anterior. Mantener el flujo manual disponible.

## Flujo de trabajo
1. Ejecutar `git status --short` y `git log -1 --oneline` y comprobar rama y cambios locales. Preservar el trabajo existente y continuar en la rama acordada `feature/optimizacion-ia`. No hacer push, merge ni cambios remotos sin autorización.
2. Leer solo los archivos relevantes de la fase actual. No repetir auditorías completas del repositorio sin motivo. El código vigente es la fuente de verdad; el README y los documentos históricos pueden estar desactualizados.
3. Antes de editar, indicar objetivo, archivos, riesgos y pruebas. Implementar cambios pequeños y comprobables. No introducir dependencias ni migraciones innecesarias.
4. Ejecutar primero pruebas unitarias relacionadas y después las pruebas de integración necesarias. No afirmar que una prueba pasó si no se ejecutó. Usar mocks para errores de proveedores; llamar a APIs reales solo con autorización y presupuesto definido.
5. Informar archivos cambiados, resultados, limitaciones y siguiente paso. Actualizar el plan si se completa una fase, sin marcar como hecho lo que no se verificó.

## Secretos y entorno
- `.env` es privado; no mostrarlo íntegro, incluirlo en commits, copiarlo a documentación ni pasar sus secretos a servicios externos. Usar `.env.example` con valores vacíos y revisar `.gitignore`.
- Mantener Python/entorno virtual y PostgreSQL de la instalación local. No ejecutar migraciones contra producción o bases ajenas sin autorización.
- Los identificadores de modelos y límites de proveedores deben verificarse en documentación oficial vigente antes de pruebas reales.

## Entrega y operación local

Seguir los comandos del [README](README.md). Revisar las migraciones 0016/0017 con `.\scripts\ia-local.ps1 -Accion Plan` y aplicarlas exclusivamente a la base local comprobada con `-Accion Migrar`. Iniciar Django con `-Accion Django`, HU02 con `-Accion Busquedas` y HU09 con `-Accion Worker` en terminales separadas que usen el mismo `config/ia-local.json`. El perfil admite Gemini y Cloudflare, ambos con 8/8 contratos. Los demás proveedores y modelos siguen fuera del piloto.

El RPD de Gemini sigue sin confirmar. El tope interno inicial de 30 solicitudes por 24 horas limita el piloto y no documenta una cuota oficial. Antes de cambiar concurrencia, topes o reservas, medir los flujos HU02, HU09 y HU10 con datos sintéticos o anonimizados. Mantener P2 con la misma expectativa de calidad y el formato de entrada de HU09.

Conservar la reserva previa y el cargo final por separado. Reconciliar solo intentos nuevos con respuesta válida, término confirmado y uso coherente del proveedor autorizado. Mantener íntegros los cargos históricos y las reservas de intentos inciertos. Consultar el saldo con `scripts/ia-local.ps1 -Accion Cuotas` antes de pruebas reales autorizadas. HU11 requiere la decisión expresa del propietario y la auditoría vigente para alimentar resultados.

El registro admite modelos adicionales por proveedor. Mantener fuera del piloto Gemini 3.1 Flash-Lite y los dos Gemma 4 hasta validar sus resultados. Los modelos reutilizan la credencial, la unidad de proyecto y el cooldown existentes. Solo ampliar operaciones con manifiesto vigente, perfil aprobado y política por modelo. Ante incertidumbre sobre límites independientes, aplicar la menor cuota al contador del proyecto.

El benchmark real de Typhoon terminó con transporte incierto. Mantenerlo deshabilitado y conservar su adaptador de laboratorio limitado a casos sintéticos. Posponer Gemma, Gemini 3.1 y los otros candidatos hasta completar sus validaciones. Antes de entregar, ejecutar la suite completa, `manage.py check`, `manage.py makemigrations --check --dry-run` y `manage.py migrate --plan`.
