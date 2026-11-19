# HU11 — contrato de revisión humana y cálculo

HU11 consume las propuestas en `ValoracionSubfactor.valor_ia` y `justificacion_ia` y las fuentes de HU09. HU10 debe validar el contexto mediante `PreparacionHU10Service.validar_vigencia()` al persistir su propuesta, en una transacción que bloquee primero la evaluación y después la valoración. HU11 no genera propuestas automáticas. Las propuestas de los comandos demo son ficticias.

## Contrato HU12

`RevisionHumanaService.para_calculo(actor, evaluacion_id)` devuelve `version_contrato: 2`, `evaluacion_id`, `huella` y `factores`. Cada factor tiene `evaluacion_factor_id`, `factor_id`, `factor`, `alcance`, `ir` y `valoraciones`; cada valoración tiene `valoracion_id`, `subfactor_id`, `valor` (confirmado), `justificacion`, `revision_id` y `fecha_validacion`.

Se excluyen factores irrelevantes e IR=1. Se bloquean factores relevantes sin IR, subfactores faltantes, valores sin auditoría vigente, cambios de fuentes y lotes HU09 activos. La vista previa usa `calcular_pm` y `clasificar_foda` de las reglas existentes. El alcance `ambos` requiere una elección válida del módulo responsable antes de clasificar FODA; HU11 no inventa esa elección. La vista previa no persiste resultados.

Ejemplo de coordinación (dentro del módulo responsable de HU12):

```python
from django.db import transaction
from apps.application.services.revision_humana import RevisionHumanaService

with transaction.atomic():
    entrada = RevisionHumanaService.para_calculo(actor, evaluacion_id)
    # Calcular usando únicamente entrada['factores'][...]['valoraciones'].
    # Resolver el alcance ambiguo y validar las demás reglas de HU12.
    RevisionHumanaService.validar_calculo(actor, evaluacion_id, entrada['huella'])
    # Persistir resultados oficiales dentro de esta misma transacción.
```

Si el cálculo se realiza fuera de esa transacción, validar la huella dentro de una nueva transacción antes de persistir. Todos los productores de resultados y de propuestas deben respetar el orden de bloqueo compartido. La integración efectiva debe probarse con los módulos de los responsables de HU10 y HU12; este contrato no sustituye su implementación.

## Reapertura

Solo el decisor propietario, en una evaluación abierta sin lote HU09 activo, puede reabrir una decisión registrada. Requiere motivo y confirmación explícita en la interfaz. Se conserva la propuesta IA y las decisiones históricas, pero se anulan la puntuación confirmada, el autor y la fecha vigentes. Los PM, FODA y el resultado final previamente persistidos se archivan en el evento de reapertura y se retiran de las tablas de resultados vigentes, de forma atómica. Las demás decisiones permanecen intactas. La nueva decisión debe confirmar o modificar de nuevo la propuesta (o valorar manualmente si no existe). La huella cambia aun si se vuelve a confirmar el mismo valor. Los resultados exportados fuera de la base no pueden invalidarse desde este servicio.

La reapertura requiere coordinar con los demás integrantes la conservación de resultados históricos y las migraciones concurrentes. No se incluye una política de retención de auditoría ni la publicación oficial de un informe.

## Verificación final y operación local

Ejecutar las migraciones y las pruebas desde el entorno virtual del proyecto:

```text
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test apps.application.tests.test_revision_humana apps.presentation.tests.test_revision_humana_interfaz --verbosity 2
python manage.py test --verbosity 2
```

Los borradores con contexto desactualizado se conservan, pero no se ofrecen en la selección masiva. El decisor debe consultar de nuevo las fuentes y guardar el borrador actualizado. La comprobación se repite en el servidor al registrar el lote; la lista de pantalla no constituye una autorización. La vista privada se sirve con directivas que impiden su almacenamiento en caché. Para probar con datos ficticios se puede emplear `python manage.py cargar_demo_hu11 --variante borradores`; este comando no reinicia decisiones existentes.

El cálculo comprueba la completitud antes de recuperar fuentes y auditorías, y agrupa los datos por factor. La prueba de 61 subfactores comprueba el número de consultas SQL de este contrato, no el rendimiento end-to-end ni la latencia de PostgreSQL en producción. La huella y los bloqueos requieren que HU10, HU12 y otros productores respeten las transacciones y las reglas de escritura documentadas. No acreditan por sí solos la actualidad semántica de una propuesta de IA ni la inmutabilidad de registros frente a administradores de la base de datos.
