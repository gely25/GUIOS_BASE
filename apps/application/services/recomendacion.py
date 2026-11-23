"""HU13: recomendación final versionada a partir de PM, FODA e IR guardados por HU12."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.application.services.preguntas import PreguntasService
from apps.application.services.revision_humana import RevisionHumanaService
from apps.data.models import EvaluacionFactor, ResultadoEvaluacion


# Esta formalización sigue las descripciones cualitativas de la tesis de Rea Sánchez (2022),
# sección 6.1.1, Paso 6. Es una decisión del equipo y está pendiente de validación con el docente.
REGLA_VERSION = '1.0'

TEXTOS_RECOMENDACION = {
    'A': 'Adoptar el FLOSS seleccionado',
    'B': 'Es posible adoptar, con matices',
    'C': 'Se sugiere analizar la adopción y debería ser pospuesta',
}

FODA_VALIDOS = ('Fortaleza', 'Oportunidad', 'Debilidad', 'Amenaza')


@dataclass(frozen=True)
class Recomendacion:
    tipo: str
    texto: str
    conteos: dict
    factores_criticos: list
    explicacion: str
    version: str


def calcular_recomendacion(factores: Iterable[Mapping]) -> Recomendacion:
    """Función pura. Solo considera factores relevantes con IR mayor que 1."""
    conteos = {clase: 0 for clase in ('F', 'O', 'D', 'A')}
    factores_criticos = []

    for fila in factores:
        ir = fila.get('ir')
        foda = fila.get('foda')
        if ir is None or ir <= 1 or foda not in FODA_VALIDOS:
            continue

        inicial = {'Fortaleza': 'F', 'Oportunidad': 'O',
                   'Debilidad': 'D', 'Amenaza': 'A'}[foda]
        conteos[inicial] += 1
        if inicial in ('D', 'A'):
            pm = fila.get('pm')
            factores_criticos.append({
                'factor': fila['factor'],
                'ir': ir,
                'pm': str(pm) if pm is not None else None,
                'foda': foda,
            })

    if sum(conteos.values()) == 0:
        raise ValidationError('No hay factores relevantes con clasificación FODA.')

    negativas = conteos['D'] + conteos['A']
    positivas = conteos['F'] + conteos['O']

    if negativas > positivas:
        tipo = 'C'
    elif negativas >= 1:
        tipo = 'B'
    else:
        tipo = 'A'

    criticos = ', '.join(
        f"{item['factor']} (IR {item['ir']}, PM {item['pm']}, {item['foda']})"
        for item in factores_criticos
    )
    conteos_texto = (
        f"Fortalezas: {conteos['F']}; Oportunidades: {conteos['O']}; "
        f"Debilidades: {conteos['D']}; Amenazas: {conteos['A']}."
    )
    explicacion = (
        f"{conteos_texto} "
        f"El número de factores negativos ({negativas}) "
        f"{'es mayor que' if negativas > positivas else 'no supera'} "
        f"los factores positivos ({positivas})."
    )
    if criticos:
        explicacion += f" Factores críticos considerados: {criticos}."

    return Recomendacion(
        tipo=tipo,
        texto=TEXTOS_RECOMENDACION[tipo],
        conteos=conteos,
        factores_criticos=factores_criticos,
        explicacion=explicacion,
        version=REGLA_VERSION,
    )


class RecomendacionService:
    @classmethod
    @transaction.atomic
    def generar(cls, actor, evaluacion_id):
        evaluacion = PreguntasService._evaluacion(actor, evaluacion_id, escritura=True)

        # Esta llamada verifica auditoría y completitud; HU13 no puede producir
        # una recomendación si hay valoraciones sin confirmar.
        RevisionHumanaService.para_calculo(actor, evaluacion_id)

        filas = list(EvaluacionFactor.objects.filter(
            evaluacion=evaluacion,
            relevante=True,
            importancia_relativa__in=(2, 3, 4),
            ponderacion_media__isnull=False,
            clasificacion_foda__isnull=False,
        ).select_related('factor').order_by('factor__dimension_id', 'factor_id'))

        recomendacion = calcular_recomendacion([
            {
                'factor': fila.factor.nombre,
                'ir': fila.importancia_relativa,
                'pm': fila.ponderacion_media,
                'foda': fila.clasificacion_foda,
            }
            for fila in filas
        ])

        resultado, _ = ResultadoEvaluacion.objects.update_or_create(
            evaluacion=evaluacion,
            defaults={
                'recomendacion': recomendacion.texto,
                'explicacion': recomendacion.explicacion,
                'version_regla': recomendacion.version,
                'conteos_foda': recomendacion.conteos,
                'factores_criticos': recomendacion.factores_criticos,
            },
        )
        return recomendacion
