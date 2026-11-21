from django.db import migrations, models
from django.db.models import Q


def normalizar_catalogo_vigente(apps, schema_editor):
    """
    Conserva GUIOS-V1 como catálogo oficial activo y desactiva versiones
    demo/duplicadas que pudieron quedar activas antes de esta migración.
    """
    CatalogoVersion = apps.get_model('data', 'CatalogoVersion')
    activos = CatalogoVersion.objects.filter(estado='ACTIVO')

    vigente = activos.filter(version='GUIOS-V1').first()
    if vigente is None:
        vigente = activos.order_by('-fecha_creacion', '-catalogo_id').first()

    if vigente is not None:
        activos.exclude(pk=vigente.pk).update(estado='INACTIVO')


class Migration(migrations.Migration):
    dependencies = [
        ('data', '0010_evaluacion_fecha_actualizacion'),
    ]

    operations = [
        migrations.RunPython(
            normalizar_catalogo_vigente,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='evaluacion',
            name='fecha_actualizacion',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddConstraint(
            model_name='catalogoversion',
            constraint=models.UniqueConstraint(
                fields=('estado',),
                condition=Q(estado='ACTIVO'),
                name='catalogo_unico_activo',
            ),
        ),
    ]
