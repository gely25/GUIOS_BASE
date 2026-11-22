# Integración HU12 → HU13 / HU14: qué entrega el cálculo de PM y FODA

Para quien desarrolla la recomendación final (HU13) y el informe (HU14). Explica qué datos deja listos HU12, dónde leerlos, dónde guardar la recomendación y cómo probarlo sin esperar a nadie.

## 1. Qué entrega HU12

Por cada factor relevante de una evaluación, HU12 guarda dos valores en `EvaluacionFactor` (`apps/data/models/evaluaciones.py`):

| Campo | Tipo | Contenido |
|---|---|---|
| `ponderacion_media` | Decimal(5,2) | PM del factor, de 1,00 a 4,00. Es la media de sus valoraciones confirmadas, redondeada a 2 decimales (mitad hacia arriba). |
| `clasificacion_foda` | texto | `Fortaleza`, `Oportunidad`, `Debilidad` o `Amenaza`. |
| `importancia_relativa` | entero | IR del factor (HU06). Los factores con IR = 1 no participan. |
| `relevante` | booleano | Solo los factores con `relevante = True` y PM calculada forman parte del resultado. |

Reglas:

- PM mayor o igual que 3: Fortaleza (interno) u Oportunidad (externo). PM menor que 3: Debilidad (interno) o Amenaza (externo).
- La etiqueta FODA es la fuente de verdad. No la recalcule a partir de la PM guardada (ya redondeada): use `clasificacion_foda` tal como está.
- Mientras la PM y el FODA no se hayan calculado, ambos campos están en `NULL`. Eso significa que el decisor aún no pasó por la pantalla de Resultados.
- **Soporte** puede ser interno o externo según la organización. El decisor lo elige al calcular y la elección queda reflejada en la etiqueta (Fortaleza o Debilidad = interno; Oportunidad o Amenaza = externo). No se guarda en otro campo.

## 2. Cómo leerlo

La forma más simple es el servicio de lectura, que ya filtra por usuario y entrega todo ordenado:

    from apps.application.services.resultados import ResultadosService

    resultados = ResultadosService.cargar(usuario, evaluacion_id)

`resultados` (clase `ResultadosEvaluacion`, en `apps/application/services/resultados.py`) trae:

- `factores`: lista de `FactorResultado` con `dimension`, `factor`, `ir`, `pm` (Decimal), `foda` y `valores` (las valoraciones confirmadas).
- `cuadrantes`: los factores agrupados por Fortaleza, Oportunidad, Debilidad y Amenaza.
- `confirmadas` y `total`: valoraciones confirmadas y esperadas; `completa` indica si están todas.
- `software_completo`, `organizacion`, `codigo` (por ejemplo `EV-006`), `fecha_corte`.
- `recomendacion`, `explicacion` y `version_regla`, si ya existen (ver sección 3).

Si la evaluación no existe, no es del usuario o aún no tiene PM calculada, lanza `InformeNoDisponible`.

Si prefiere el ORM directo:

    EvaluacionFactor.objects.filter(
        evaluacion_id=evaluacion_id, relevante=True, ponderacion_media__isnull=False,
    ).select_related('factor')

## 3. Dónde guardar la recomendación (HU13)

Se guarda en `ResultadoEvaluacion` (`apps/data/models/resultados.py`), una fila por evaluación:

| Campo | Uso |
|---|---|
| `evaluacion` | Relación uno a uno con la evaluación. |
| `recomendacion` | Texto de la recomendación final. |
| `explicacion` | Explicación redactada (opcional). |
| `version_regla` | Versión de la regla que la produjo, por ejemplo `v1.0`. |
| `fecha_generacion` | Se llena sola. |

No hay que tocar ninguna pantalla: en cuanto exista la fila, la pantalla de Resultados muestra la recomendación en el banner oscuro del diseño, muestra la explicación y habilita el botón «Siguiente · Informe». Sin fila, el banner dice «Recomendación final · pendiente» y el botón queda inactivo. El informe y el PDF (HU14) leen la misma fila.

## 4. Cuándo deja de ser válida

- Si el decisor **reabre una valoración** en la revisión de evidencia, el sistema borra la PM y el FODA de todos los factores y **elimina el `ResultadoEvaluacion`**, después de guardar una copia histórica en `ReaperturaRevisionHumana.resultados_anteriores`. La recomendación debe generarse de nuevo tras volver a calcular.
- Punto abierto: si el decisor usa **Recalcular** en Resultados y cambia la elección de Soporte, el FODA de ese factor puede cambiar, pero HU12 **no borra** el `ResultadoEvaluacion` existente. Quien implemente HU13 debe decidir si regenera o invalida la recomendación cuando cambie el FODA.

## 5. Cómo probarlo rápido con datos de demostración

1. Cree una evaluación nueva con la ficha inicial y guarde la «Valoración de factores» (esto crea las valoraciones).
2. Confirme todas las valoraciones con datos ficticios (solo en una base `_dev`):

        python manage.py aprobar_valoraciones_demo --evaluacion N

3. Abra `http://127.0.0.1:8000/decisor/resultados/?evaluacion=N`, elija si Soporte es interno o externo y pulse «Calcular y guardar PM y FODA».
4. Compruebe en consola que lo guardado es correcto:

        python manage.py verificar_foda --evaluacion N

5. Para ver cómo se muestra una recomendación, cree una de prueba y recargue Resultados:

        python manage.py shell -c "from apps.data.models import ResultadoEvaluacion; ResultadoEvaluacion.objects.create(evaluacion_id=N, recomendacion='Adoptar con piloto controlado', version_regla='v-prueba')"

   Para volver al estado anterior, elimine esa fila.

Cambie `N` por el número real de la evaluación.

## 6. Qué no hace HU12

- No genera la recomendación ni define su regla (HU13).
- No calcula la «Puntuación global ponderada» que aparece en el banner del diseño de Figma. Depende de la regla de recomendación, así que debe definirla HU13.
- No redacta la explicación ni genera el PDF (HU14).

## 7. Referencias

| Qué | Dónde |
|---|---|
| Reglas puras de PM y FODA | `apps/business_rules/pm.py`, `foda.py` |
| Cálculo y guardado | `apps/application/services/pm_foda.py` |
| Lectura para pantalla e informe | `apps/application/services/resultados.py` |
| Verificación en consola | `python manage.py verificar_foda` (`apps/data/management/commands/verificar_foda.py`) |
| Tests | `apps/business_rules/tests/test_pm.py`, `test_foda.py`, `apps/application/tests/test_pm_foda_hu12.py`, `apps/presentation/tests/test_resultados_hu12.py` |
| Cómo ver la pantalla | `HU12_RESULTADOS.md` |