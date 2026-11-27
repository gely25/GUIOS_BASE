from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('data', '0016_planificacion_ia')]

    operations = [
        migrations.AddField('intentoia', 'tokens_cuota', models.PositiveBigIntegerField(null=True)),
        migrations.AddField('intentoia', 'unidades_cuota', models.PositiveBigIntegerField(null=True)),
    ]
