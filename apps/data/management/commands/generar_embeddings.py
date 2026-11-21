"""
Comando de gestión para generar y sincronizar embeddings en pgvector (HU08).

Uso:
    python manage.py generar_embeddings
    python manage.py generar_embeddings --evaluacion-id 1
    python manage.py generar_embeddings --forzar
"""

from django.core.management.base import BaseCommand

from apps.application.services.retrieval import RetrievalService


class Command(BaseCommand):
    help = 'Genera embeddings de 1536 dimensiones en pgvector para fragmentos documentales.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--evaluacion-id',
            type=int,
            default=None,
            help='ID opcional de la evaluación a sincronizar.',
        )
        parser.add_argument(
            '--forzar',
            action='store_true',
            help='Regenera los embeddings incluso en fragmentos que ya tienen vector.',
        )

    def handle(self, *args, **options):
        evaluacion_id = options['evaluacion_id']
        forzar = options['forzar']

        servicio = RetrievalService()
        resultado = servicio.sincronizar_evaluacion(
            evaluacion_id=evaluacion_id,
            forzar=forzar,
        )

        ambito = f'evaluación #{evaluacion_id}' if evaluacion_id else 'todas las evaluaciones'
        self.stdout.write(
            self.style.SUCCESS(
                f'Sincronización completada ({ambito}): '
                f'{resultado["indexados"]} fragmento(s) indexado(s) en pgvector.'
            )
        )