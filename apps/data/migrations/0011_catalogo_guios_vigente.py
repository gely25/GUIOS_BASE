from datetime import date

from django.db import migrations


def crear_catalogo_vigente(apps, schema_editor):
    catalogo_version = apps.get_model('data', 'CatalogoVersion')
    catalogo, _ = catalogo_version.objects.get_or_create(
        version='GUIOS-V1',
        defaults={
            'fecha_creacion': date.today(),
            'estado': 'ACTIVO',
        },
    )
    if catalogo.estado != 'ACTIVO':
        catalogo.estado = 'ACTIVO'
        catalogo.save(update_fields=['estado'])


def eliminar_catalogo_vigente(apps, schema_editor):
    catalogo_version = apps.get_model('data', 'CatalogoVersion')
    catalogo_version.objects.filter(version='GUIOS-V1', estado='ACTIVO').delete()


class Migration(migrations.Migration):
    dependencies = [('data', '0010_evaluacion_fecha_actualizacion')]

    operations = [
        migrations.RunPython(crear_catalogo_vigente, eliminar_catalogo_vigente),
    ]
