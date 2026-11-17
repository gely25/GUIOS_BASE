"""
Comando de gestión: verifica la conexión a PostgreSQL y la extensión pgvector.

Uso: python manage.py check_db
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = 'Comprueba la conexión a PostgreSQL y la disponibilidad de pgvector (extensión vector).'

    def handle(self, *args, **options):
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT version();')
                version = cursor.fetchone()[0]
                self.stdout.write(self.style.SUCCESS('[OK] Conexión a PostgreSQL establecida.'))
                self.stdout.write(f'     Servidor: {version}')

                cursor.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'vector';")
                disponible = cursor.fetchone() is not None

                cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
                activa = cursor.fetchone()
        except Exception as error:
            raise CommandError(f'No se pudo conectar a la base de datos: {error}')

        if activa:
            self.stdout.write(self.style.SUCCESS(f"[OK] Extensión 'vector' activa (versión {activa[0]})."))
        elif disponible:
            self.stdout.write(self.style.WARNING(
                "[AVISO] pgvector está instalado en el servidor pero aún no está activado. "
                "Ejecuta: python manage.py migrate"
            ))
        else:
            raise CommandError(
                "pgvector NO está instalado en este servidor PostgreSQL. "
                "Instálalo (o usa un PostgreSQL con pgvector, por ejemplo en Docker) antes de migrar."
            )
