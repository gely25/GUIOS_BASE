"""
Procesa en segundo plano las búsquedas bibliográficas en cola (HU02, RNF09).

Uso:
    python manage.py procesar_busquedas            # se queda escuchando la cola
    python manage.py procesar_busquedas --una-vez  # procesa lo pendiente y termina

La interfaz solo deja las búsquedas en estado PENDIENTE; este proceso las ejecuta
y va actualizando `estado` y `progreso`.
"""

import time

from django.core.management.base import BaseCommand

from apps.application.services.bibliographic import BibliographicService


class Command(BaseCommand):
    help = 'Ejecuta las búsquedas bibliográficas pendientes (cola en la base de datos).'

    def add_arguments(self, parser):
        parser.add_argument('--una-vez', action='store_true', help='Procesa lo pendiente y termina.')
        parser.add_argument('--intervalo', type=int, default=5,
                            help='Segundos entre revisiones de la cola (por defecto 5).')

    def handle(self, *args, **opciones):
        servicio = BibliographicService()
        if opciones['una_vez']:
            n = servicio.procesar_pendientes()
            self.stdout.write(self.style.SUCCESS(f'[OK] {n} búsqueda(s) procesada(s).'))
            return

        self.stdout.write('Escuchando la cola de búsquedas bibliográficas (Ctrl+C para salir)...')
        try:
            while True:
                n = servicio.procesar_pendientes()
                if n:
                    self.stdout.write(f'{n} búsqueda(s) procesada(s).')
                time.sleep(opciones['intervalo'])
        except KeyboardInterrupt:
            self.stdout.write('Procesador detenido.')
