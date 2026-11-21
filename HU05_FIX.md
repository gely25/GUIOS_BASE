# HU05 — Correcciones de integridad y navegación

Esta rama parte de `feature/hu05-registro-evaluacion` y concentra correcciones para preparar la integración.

## Cambios

1. **Historial de organizaciones:** al crear una evaluación se bloquea el registro del decisor. Si su organización ya está asociada a evaluaciones anteriores o compartida con otros usuarios, se crea una ficha nueva para la evaluación actual. Solo se actualiza la ficha existente cuando todavía no tiene historial ni otros usuarios asociados.
2. **Catálogo vigente:** `CatalogService` exige exactamente una versión `ACTIVO`. La base de datos incorpora una restricción parcial para impedir más de una versión activa.
3. **Normalización de datos existentes:** la migración `0012_integridad_hu05` conserva `GUIOS-V1` como catálogo activo y pasa a `INACTIVO` las demás versiones que estuvieran activas. Las evaluaciones históricas mantienen sus claves foráneas.
4. **Catálogo demo:** `cargar_datos_demo` registra `GUIOS-DEMO-V1` con estado `DEMO`; no desplaza `GUIOS-V1`.
5. **Reversión segura:** la migración `0011_catalogo_guios_vigente` ya no elimina `GUIOS-V1` al revertirse.
6. **Fecha de actualización:** `Evaluacion.fecha_actualizacion` utiliza `auto_now=True` y la migración `0012` actualiza el estado del modelo.
7. **Navegación:** tras registrar una ficha, se continúa al paso 2 (`decisor-importancia-factores`) con `evaluacion_id` en la URL. La pantalla de módulo pendiente muestra el mensaje de confirmación.
8. **Codificación:** se amplía la prueba de codificación para verificar UTF-8 válido, además de la ausencia de BOM. El código fuente de la rama de origen se verificó como UTF-8 válido y sin BOM; la secuencia de caracteres extraños del diff previo procedía de su visualización/exportación, no de estos archivos fuente.

## Pruebas añadidas o ajustadas

- Dos evaluaciones del mismo decisor no modifican la organización de la evaluación anterior.
- Una organización compartida con otro usuario no se modifica al iniciar una evaluación.
- Una organización exclusiva sin historial se puede actualizar.
- El catálogo `DEMO` no se selecciona como vigente.
- La fecha de actualización cambia al guardar una evaluación modificada.
- La base de datos impide dos catálogos activos.
- El comando demo conserva `GUIOS-V1` como única versión activa.
- La interfaz redirige al siguiente paso y presenta el mensaje de registro.

## Verificación local

Desde la raíz del proyecto y con el entorno virtual activado:

```powershell
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test apps.application.tests.test_evaluacion_hu05 apps.presentation.tests.test_evaluacion_hu05 apps.data.tests.test_modelos apps.data.tests.test_datos_demo --verbosity 2
python manage.py test apps.application.tests.test_preguntas apps.application.tests.test_revision_humana apps.presentation.tests.test_lotes_hu09 apps.presentation.tests.test_preguntas_interfaz apps.presentation.tests.test_revision_humana_interfaz --verbosity 2
python manage.py test --verbosity 2
```

La integración no se considera terminada hasta ejecutar la suite completa en la rama de correcciones y revisar el resultado contra `main`.
