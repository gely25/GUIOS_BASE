"""Muestra en consola si el cálculo de PM y FODA funciona, con resultados que se pueden comprobar a mano.

Parte 1 (siempre): un caso con valoraciones inventadas cuyo resultado esperado está calculado a mano
y escrito en este archivo, sin pasar por el código. Se compara con lo que devuelven las reglas reales
(`calcular_pm` y `clasificar_foda`) e incluye los bordes importantes (PM = 3 exacto, justo debajo de 3).

Parte 2 (con --evaluacion N): lee una evaluación real de la base, recalcula la PM de cada factor a
partir de sus valoraciones confirmadas y la compara con lo que quedó guardado, y revisa que la
etiqueta FODA sea coherente con la PM y con el alcance del factor. Solo lee; no modifica nada.

Uso:
    python manage.py verificar_foda
    python manage.py verificar_foda --evaluacion 6
"""

from fractions import Fraction

from django.core.management.base import BaseCommand, CommandError

from apps.application.services.pm_foda import _redondear
from apps.business_rules.foda import EXTERNO, INTERNO, clasificar_foda
from apps.business_rules.pm import calcular_pm
from apps.data.models import EvaluacionFactor, ValoracionSubfactor

_INTERNAS = ('Fortaleza', 'Debilidad')
_ALTAS = ('Fortaleza', 'Oportunidad')
_VALIDAS = ('CONFIRMADA', 'MODIFICADA')

# (nombre, valoraciones de los subfactores, alcance, PM esperada calculada a mano, FODA esperado)
CASO_A_MANO = [
    ('Funcionalidad (4,4,3)', [4, 4, 3], INTERNO, '11/3', 'Fortaleza'),          # 11 / 3 = 3,67 >= 3, interno
    ('Compatibilidad (3,3,2,3)', [3, 3, 2, 3], EXTERNO, '11/4', 'Amenaza'),       # 11 / 4 = 2,75 < 3, externo
    ('Soporte elegido externo (4,4)', [4, 4], EXTERNO, '4', 'Oportunidad'),       # 8 / 2 = 4, externo
    ('Soporte elegido interno (4,4)', [4, 4], INTERNO, '4', 'Fortaleza'),         # igual PM, otro alcance
    ('Costo total (2,3)', [2, 3], INTERNO, '5/2', 'Debilidad'),                   # 5 / 2 = 2,5 < 3, interno
    ('Borde: PM = 3 exacto (3,3,3)', [3, 3, 3], INTERNO, '3', 'Fortaleza'),       # 3 cuenta como alta
    ('Borde: justo bajo 3 (3,3,3,3,3,2)', [3, 3, 3, 3, 3, 2], EXTERNO, '17/6', 'Amenaza'),  # 2,83
    ('Todo "No cumple" (1,1)', [1, 1], INTERNO, '1', 'Debilidad'),                # mínimo posible
]


def _texto_pm(pm):
    """PM exacta y su valor con 2 decimales, como se guarda: '11/3 = 3.67'."""
    return f'{pm.numerator}/{pm.denominator} = {_redondear(pm)}' if pm.denominator != 1 else f'{pm.numerator} = {_redondear(pm)}'


class Command(BaseCommand):
    help = 'Comprueba en consola que la PM y el FODA se calculan bien (caso a mano y, opcional, una evaluación real).'

    def add_arguments(self, parser):
        parser.add_argument('--evaluacion', type=int, help='Número de una evaluación real para revisar sus resultados guardados.')

    def handle(self, *args, **options):
        fallas = self._caso_a_mano()
        if options['evaluacion']:
            fallas += self._evaluacion_real(options['evaluacion'])
        self.stdout.write('')
        if fallas:
            raise CommandError(f'RESULTADO: {fallas} comprobación(es) fallaron.')
        self.stdout.write(self.style.SUCCESS('RESULTADO: todo coincide. La lógica de PM y FODA funciona.'))

    def _linea(self, cols, anchos):
        return '  '.join(str(c).ljust(a) for c, a in zip(cols, anchos))

    def _caso_a_mano(self):
        self.stdout.write(self.style.MIGRATE_HEADING('PARTE 1 · Caso calculado a mano (esperado vs obtenido)'))
        self.stdout.write('PM = suma de las valoraciones / cantidad. PM >= 3 es Fortaleza u Oportunidad; PM < 3, Debilidad o Amenaza.')
        self.stdout.write('Interno: Fortaleza o Debilidad. Externo: Oportunidad o Amenaza.\n')
        anchos = (36, 16, 9, 22, 28, 7)
        self.stdout.write(self._linea(('Factor', 'PM a mano', 'Alcance', 'PM obtenida', 'FODA esperado / obtenido', ''), anchos))
        self.stdout.write("-" * 118)
        fallas = 0
        for nombre, valores, alcance, pm_mano, foda_mano in CASO_A_MANO:
            pm = calcular_pm(valores)
            foda = clasificar_foda(pm, alcance)
            bien = pm == Fraction(pm_mano) and foda == foda_mano
            fallas += not bien
            fila = self._linea((nombre, pm_mano, alcance, _texto_pm(pm), f'{foda_mano} / {foda}', 'OK' if bien else 'FALLA'), anchos)
            self.stdout.write(self.style.SUCCESS(fila) if bien else self.style.ERROR(fila))
        self.stdout.write(f'\nCaso a mano: {len(CASO_A_MANO) - fallas} de {len(CASO_A_MANO)} correctos.')
        return fallas

    def _evaluacion_real(self, evaluacion_id):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(f'PARTE 2 · Evaluación real #{evaluacion_id} (recalculado vs guardado)'))
        factores = list(EvaluacionFactor.objects.filter(
            evaluacion_id=evaluacion_id, relevante=True, ponderacion_media__isnull=False,
        ).select_related('factor').order_by('factor__dimension_id', 'factor_id'))
        if not factores:
            raise CommandError('Esa evaluación no existe o aún no tiene PM guardada. Calcúlela en la pantalla de Resultados.')
        valoraciones = {}
        for v in ValoracionSubfactor.objects.filter(
                evaluacion_factor__evaluacion_id=evaluacion_id, estado_validacion__in=_VALIDAS,
                valor_confirmado__in=(1, 2, 3, 4)).order_by('subfactor_id'):
            valoraciones.setdefault(v.evaluacion_factor_id, []).append(v.valor_confirmado)

        anchos = (34, 14, 20, 11, 12, 13, 7)
        self.stdout.write(self._linea(('Factor', 'Valoraciones', 'PM recalculada', 'PM guardada', 'Alcance', 'FODA guardado', ''), anchos))
        self.stdout.write("-" * 118)
        fallas = 0
        for ef in factores:
            valores = valoraciones.get(ef.pk, [])
            motivos = []
            if not valores:
                motivos.append('sin valoraciones confirmadas')
                pm = None
            else:
                pm = calcular_pm(valores)
                if _redondear(pm) != ef.ponderacion_media:
                    motivos.append('la PM guardada no coincide')
            alcance = 'interno' if ef.clasificacion_foda in _INTERNAS else 'externo'
            if ef.clasificacion_foda is None:
                motivos.append('sin etiqueta FODA')
            elif pm is not None and clasificar_foda(pm, alcance) != ef.clasificacion_foda:
                motivos.append('la etiqueta no sigue la regla (PM >= 3)')
            if ef.factor.alcance in (INTERNO, EXTERNO) and ef.clasificacion_foda and alcance != ef.factor.alcance:
                motivos.append(f'el catálogo dice {ef.factor.alcance}')
            bien = not motivos
            fallas += not bien
            fila = self._linea((ef.factor.nombre[:33], ','.join(map(str, valores)) or '-',
                                _texto_pm(pm) if pm is not None else '-', ef.ponderacion_media, alcance,
                                ef.clasificacion_foda or '-', 'OK' if bien else 'FALLA'), anchos)
            self.stdout.write(self.style.SUCCESS(fila) if bien else self.style.ERROR(fila + '  <- ' + '; '.join(motivos)))
        self.stdout.write(f'\nEvaluación #{evaluacion_id}: {len(factores) - fallas} de {len(factores)} factores correctos.')
        return fallas