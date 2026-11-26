from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('data', '0014_recomendacion_hu13'),
    ]

    operations = [
        migrations.AddField(
            model_name='busquedabibliografica',
            name='analisis_ia_completado',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='publicacionfactor',
            name='origen',
            field=models.CharField(
                choices=[
                    ('MANUAL', 'Manual'),
                    ('PALABRAS_CLAVE', 'Palabras clave'),
                    ('IA', 'Inteligencia artificial'),
                ],
                default='MANUAL',
                max_length=20,
            ),
        ),
        migrations.RemoveConstraint(
            model_name='publicacionfactor',
            name='pubfactor_origen_valido',
        ),
        migrations.AddConstraint(
            model_name='publicacionfactor',
            constraint=models.CheckConstraint(
                condition=models.Q(('origen__in', ['MANUAL', 'PALABRAS_CLAVE', 'IA'])),
                name='pubfactor_origen_valido',
            ),
        ),
    ]
