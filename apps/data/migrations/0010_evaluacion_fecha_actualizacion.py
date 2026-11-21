from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('data', '0009_reapertura_revision_humana')]

    operations = [
        migrations.AddField(
            model_name='evaluacion',
            name='fecha_actualizacion',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='evaluacion',
            name='estado',
            field=models.CharField(
                choices=[('EN_PROCESO', 'En curso'), ('CERRADA', 'Cerrada')],
                default='EN_PROCESO',
                max_length=30,
            ),
        ),
    ]
