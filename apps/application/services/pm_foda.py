"""
Capa: application. Cálculo y persistencia de la Ponderación Media (PM) y la clasificación FODA (HU12).

Usa únicamente los valores confirmados que entrega RevisionHumanaService.para_calculo y las
reglas puras de business_rules (calcular_pm, clasificar_foda). No genera la recomendación final.

El alcance de cada factor viene del catálogo. Solo los factores de alcance 'ambos' (Soporte)
requieren que el decisor elija interno o externo; esa elección no se guarda aparte: queda
reflejada en la clasificación (Fortaleza/Debilidad = interno, Oportunidad/Amenaza = externo).
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.application.services.preguntas import PreguntasService
from apps.application.services.revision_humana import RevisionHumanaService
from apps.business_rules.foda import EXTERNO, INTERNO, clasificar_foda
from apps.business_rules.pm import calcular_pm
from apps.data.models import EvaluacionFactor

ALCANCES_ELEGIBLES = (INTERNO, EXTERNO)
_INTERNAS = ('Fortaleza', 'Debilidad')


def _redondear(pm):
    """PM exacta (Fraction) a 2 decimales para guardarla en la base."""
    return (Decimal(pm.numerator) / Decimal(pm.denominator)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class PmFodaService:
    """PM y FODA de los factores relevantes de una evaluación."""

    @staticmethod
    def _alcance_de(factor, alcances):
        """Alcance efectivo: el del catálogo, o la elección del decisor si es 'ambos'."""
        if factor['alcance'] in ALCANCES_ELEGIBLES:
            return factor['alcance']
        eleccion = (alcances or {}).get(factor['factor_id'])
        return eleccion if eleccion in ALCANCES_ELEGIBLES else None

    @classmethod
    def _filas(cls, datos, alcances):
        filas = []
        for f in datos['factores']:
            pm = calcular_pm(v['valor'] for v in f['valoraciones'])
            alcance = cls._alcance_de(f, alcances)
            filas.append({
                'evaluacion_factor_id': f['evaluacion_factor_id'], 'factor_id': f['factor_id'],
                'factor': f['factor'], 'ir': f['ir'], 'cantidad': len(f['valoraciones']),
                'pm': pm, 'pm_texto': f'{float(pm):.2f}', 'alcance_catalogo': f['alcance'],
                'alcance': alcance, 'elegible': f['alcance'] not in ALCANCES_ELEGIBLES,
                'foda': clasificar_foda(pm, alcance) if alcance else None,
            })
        return filas

    @classmethod
    def vista_previa(cls, actor, evaluacion_id, alcances=None):
        """Cálculo sin guardar. `alcances` = {factor_id: 'interno'|'externo'} para los factores 'ambos'."""
        try:
            datos = RevisionHumanaService.para_calculo(actor, evaluacion_id)
        except ValidationError as exc:
            return {'lista': False, 'motivo': ' '.join(exc.messages), 'filas': [], 'guardado': False,
                    'pendientes_alcance': []}
        filas = cls._filas(datos, alcances)
        guardados = dict(EvaluacionFactor.objects.filter(
            pk__in=[f['evaluacion_factor_id'] for f in filas]).values_list('pk', 'clasificacion_foda'))
        for fila in filas:
            fila['foda_guardado'] = guardados.get(fila['evaluacion_factor_id'])
            if fila['elegible'] and fila['alcance'] is None and fila['foda_guardado']:
                # Elección previa, recuperada de la clasificación ya guardada.
                fila['alcance'] = INTERNO if fila['foda_guardado'] in _INTERNAS else EXTERNO
                fila['foda'] = clasificar_foda(fila['pm'], fila['alcance'])
        pendientes = [f for f in filas if f['alcance'] is None]
        return {
            'lista': not pendientes, 'filas': filas, 'huella': datos['huella'],
            'pendientes_alcance': pendientes,
            'guardado': all(f['foda_guardado'] for f in filas),
            'motivo': '' if not pendientes else 'Elija si el factor de alcance mixto es interno o externo.',
        }

    @classmethod
    @transaction.atomic
    def calcular_y_guardar(cls, actor, evaluacion_id, alcances=None):
        """Calcula y persiste PM y FODA en una sola transacción; devuelve las filas calculadas."""
        PreguntasService._evaluacion(actor, evaluacion_id, escritura=True)  # abierta y del decisor
        datos = RevisionHumanaService.para_calculo(actor, evaluacion_id)
        filas = cls._filas(datos, alcances)
        faltan = [f['factor'] for f in filas if f['alcance'] is None]
        if faltan:
            raise ValidationError('Elija interno o externo para: ' + ', '.join(faltan) + '.')
        RevisionHumanaService.validar_calculo(actor, evaluacion_id, datos['huella'])
        for fila in filas:
            EvaluacionFactor.objects.filter(pk=fila['evaluacion_factor_id'], evaluacion_id=evaluacion_id).update(
                ponderacion_media=_redondear(fila['pm']), clasificacion_foda=fila['foda'])
        return filas