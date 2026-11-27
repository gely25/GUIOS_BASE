from django.core.management.base import BaseCommand, CommandError

from apps.external_services.planificador_ia import PlanificadorIA


class Command(BaseCommand):
    help = 'Recupera reservas vencidas y limpia resultados de IA fuera de su vigencia.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirmar-termino', metavar='ID_TAREA',
            help='Reabre una tarea incierta después de verificar externamente que el intento terminó.',
        )

    def handle(self, *args, **options):
        clave = options['confirmar_termino']
        if clave and not PlanificadorIA.reabrir_confirmada(clave):
            raise CommandError('No se encontró una tarea incierta con ese identificador.')
        total = 0
        while cantidad := PlanificadorIA.mantener():
            total += cantidad
        self.stdout.write(f'Tareas mantenidas: {total}.')
