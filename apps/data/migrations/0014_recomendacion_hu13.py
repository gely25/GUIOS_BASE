from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('data', '0012_actualizacion_bibliografica'),
    ]

    operations = [
        migrations.AddField(
            model_name='resultadoevaluacion',
            name='conteos_foda',
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name='resultadoevaluacion',
            name='factores_criticos',
            field=models.JSONField(default=list),
        ),
    ]
