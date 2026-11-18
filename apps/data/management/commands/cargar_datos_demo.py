"""
Carga usuarios de demostración para probar el acceso por rol en desarrollo.

Es repetible: si el correo ya existe, actualiza sus datos y su contraseña.
Solo corre sobre una base cuyo nombre termine en `_dev`.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.data.models import Organizacion, Usuario

USUARIOS_DEMO = [
    # correo, contraseña, nombre, rol, activo
    ('admin.demo@guios.local', 'Demo-Admin-123', 'Admin Demo', Usuario.ADMINISTRADOR, True),
    ('decisor.demo@guios.local', 'Demo-Decisor-123', 'Decisor Demo', Usuario.DECISOR, True),
    ('inactivo.demo@guios.local', 'Demo-Inactivo-123', 'Decisor Inactivo', Usuario.DECISOR, False),
]


class Command(BaseCommand):
    help = 'Crea usuarios de demostración (administrador, decisor, decisor inactivo).'

    def handle(self, *args, **opciones):
        base = connection.settings_dict['NAME']
        if not base.endswith('_dev'):
            raise CommandError(
                f'Por seguridad solo corre en una base de desarrollo (nombre termina en _dev); '
                f'la actual es "{base}".')

        organizacion, _ = Organizacion.objects.get_or_create(
            nombre='Organización Demo',
            defaults={'sector': 'Educación', 'tamano': 'Mediana'})

        self.stdout.write('Usuarios de demostración:')
        for correo, clave, nombre, rol, activo in USUARIOS_DEMO:
            usuario, creado = Usuario.objects.get_or_create(
                correo=correo,
                defaults={'nombre': nombre, 'rol': rol, 'activo': activo,
                          'organizacion': organizacion})
            usuario.nombre, usuario.rol, usuario.activo = nombre, rol, activo
            usuario.organizacion = organizacion
            usuario.set_password(clave)
            usuario.save()
            estado = 'creado' if creado else 'actualizado'
            self.stdout.write(
                f'  [{estado}] {rol:<14} {correo:<28} {clave}'
                f'{"" if activo else "  (inactivo)"}')
