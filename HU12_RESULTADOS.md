# HU12 · PM y FODA en la pantalla de Resultados

Dónde está el cálculo, cómo verlo funcionando con datos de demostración y qué falta de otras historias.

## Dónde está

El cálculo de la Ponderación Media (PM) y la clasificación FODA se hace y se muestra en **Resultados** (paso 5 del flujo, igual que en el diseño de Figma). La Revisión de evidencia (paso 4) solo sirve para confirmar valoraciones; ya no calcula nada.

| Qué | Archivo |
|---|---|
| Reglas puras (PM, FODA) | `apps/business_rules/pm.py`, `foda.py` |
| Cálculo y guardado | `apps/application/services/pm_foda.py` |
| Datos de la pantalla | `apps/application/services/resultados.py` |
| Vista y plantilla | `apps/presentation/views/informe.py` (`resultados_view`), `templates/presentation/decisor/resultados.html` |
| Formulario de cálculo | `templates/presentation/includes/pm_foda_calculo.html` |

La PM y el FODA se guardan en `EvaluacionFactor.ponderacion_media` y `EvaluacionFactor.clasificacion_foda`. De ahí los leen la recomendación (HU13) y el informe (HU14).

## Cómo verlo

1. Inicie sesión como decisor y abra la evaluación: `http://127.0.0.1:8000/decisor/resultados/?evaluacion=N` (cambie `N` por el número de su evaluación).
2. Si todas las valoraciones están confirmadas, verá la tabla de cálculo. Elija si **Soporte** es interno o externo para su organización y pulse **Calcular y guardar PM y FODA**.
3. Verá la PM por factor, la matriz FODA y el perfil de cumplimiento. Con **Recalcular** puede cambiar la elección de Soporte.

### Con datos de demostración (sin confirmar valoración por valoración)

Comando (cambie `N` por el número de la evaluación):

    python manage.py aprobar_valoraciones_demo --evaluacion N

Confirma todas las valoraciones pendientes de la evaluación N con valores ficticios (solo en la base `_dev`). Después abra la URL del paso 1.

## Qué falta (otras historias)

| Falta | Historia | Responsable |
|---|---|---|
| Recomendación final y su regla versionada (el banner dice «pendiente» y el botón «Siguiente · Informe» está inactivo hasta entonces) | HU13 | Joseph |
| Puntuación global ponderada del diseño, que depende de la regla de recomendación | HU13 | Joseph |
| Explicación redactada por IA | HU14 | Merly |
| Informe PDF | HU14 | Merly |

## Decisiones que conviene confirmar con el equipo

- **Soporte** tiene alcance interno y externo en el catálogo. Aquí lo elige el decisor y la elección queda reflejada en la clasificación (Fortaleza/Debilidad = interno, Oportunidad/Amenaza = externo); no se guarda aparte.
- Un factor con PM ≥ 3 es Fortaleza u Oportunidad; con PM < 3, Debilidad o Amenaza.