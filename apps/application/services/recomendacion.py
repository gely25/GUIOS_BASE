"""HU13: recomendación final versionada a partir de PM, FODA e IR guardados por HU12."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.application.services.preguntas import PreguntasService
from apps.application.services.revision_humana import RevisionHumanaService
from apps.data.models import Evaluacion, EvaluacionFactor, ResultadoEvaluacion


# Regla híbrida (v2.0). Combina las dos fuentes de la tesis de Rea Sánchez (2022):
#   - Cap. 6, Recomendación B/C: B si las debilidades/amenazas están en factores con IR opcional;
#     C si las amenazas y debilidades son mayores que las oportunidades y fortalezas.
#   - Prototipo GUIOS PRO (main.py) y Figura 6.5 (caso LibreOffice = C): una debilidad o amenaza
#     en un factor Importante o Fundamental basta para recomendar C.
#     C: alguna D/A con IR >= 3, o negativas > positivas
#     B: hay D/A, todas con IR = 2 (opcional), y no superan a las positivas
#     A: ninguna D/A
# La v1.0 solo contaba F+O contra D+A y no usaba el IR; los resultados ya guardados conservan su versión.
REGLA_VERSION = '2.0'
IR_OPCIONAL = 2

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
    criticos_importantes = [item for item in factores_criticos if item['ir'] > IR_OPCIONAL]

    if criticos_importantes or negativas > positivas:
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
    if criticos_importantes:
        nombres = ', '.join(item['factor'] for item in criticos_importantes)
        explicacion += (f" Hay debilidades o amenazas en factores importantes o fundamentales "
                        f"para la organización: {nombres}.")
    elif negativas >= 1 and tipo == 'B':
        explicacion += " Las debilidades o amenazas están solo en factores opcionales."
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
        evaluacion.estado = Evaluacion.CERRADA
        evaluacion.fecha_fin = timezone.now()
        evaluacion.save(update_fields=['estado', 'fecha_fin', 'fecha_actualizacion'])
        return recomendacion
