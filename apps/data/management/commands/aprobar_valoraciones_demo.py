"""Confirma de una vez las valoraciones de una evaluación para probar HU12 sin pasar por HU09-HU11.

Usa el servicio real de revisión humana (RevisionHumanaService.resolver), por lo que deja las
decisiones con su auditoría y `para_calculo` las acepta. Los valores se reparten con un patrón
fijo por factor (1 a 4) para que salgan fortalezas, debilidades, oportunidades y amenazas.
Solo corre sobre una base cuyo nombre termine en `_dev`.

Uso:  python manage.py aprobar_valoraciones_demo --evaluacion 5
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.application.services.revision_humana import RevisionHumanaService
from apps.data.models import Evaluacion, ValoracionSubfactor

PATRON = (4, 3, 2, 1)
JUSTIFICACION = 'Valoración de prueba confirmada con datos ficticios (LibreGestión 3.2).'


class Command(BaseCommand):
    help = 'Confirma todas las valoraciones pendientes de una evaluación (solo bases _dev).'

    def add_arguments(self, parser):
        parser.add_argument('--evaluacion', type=int, required=True)

    def handle(self, *args, **options):
        if not str(connection.settings_dict['NAME']).endswith('_dev'):
            raise CommandError('Solo se permite ejecutar en bases de desarrollo _dev.')
        ev = Evaluacion.objects.select_related('usuario').filter(pk=options['evaluacion']).first()
        if ev is None:
            raise CommandError('No existe esa evaluación.')
        pendientes = ValoracionSubfactor.objects.filter(
            evaluacion_factor__evaluacion=ev, evaluacion_factor__relevante=True,
            evaluacion_factor__importancia_relativa__in=(2, 3, 4),
        ).exclude(estado_validacion__in=('CONFIRMADA', 'MODIFICADA')).select_related('evaluacion_factor')
        if not pendientes.exists():
            raise CommandError('No hay valoraciones pendientes. ¿Guardó la "Valoración de factores" de la evaluación?')
        total = 0
        for i, v in enumerate(pendientes.order_by('evaluacion_factor_id', 'pk')):
            actor = ev.usuario
            version = RevisionHumanaService.obtener(actor, ev.pk, v.pk)['version']
            tiene_ia = v.valor_ia is not None and (v.justificacion_ia or '').strip()
            if tiene_ia:
                modo, valor = 'CONFIRMAR', v.valor_ia
            else:
                modo, valor = 'MANUAL', PATRON[(v.evaluacion_factor_id + i // 3) % 4]
            RevisionHumanaService.resolver(actor, ev.pk, v.pk, modo, valor, JUSTIFICACION, version)
            total += 1
        self.stdout.write(self.style.SUCCESS(f'{total} valoraciones confirmadas en la evaluación #{ev.pk}.'))