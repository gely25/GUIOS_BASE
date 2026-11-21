from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [('data', '0001_initial')]
    operations = [
        migrations.CreateModel(
            name='PreguntaComplementaria',
            fields=[
                ('pregunta_id', models.BigAutoField(primary_key=True, serialize=False)),
                ('clave', models.CharField(editable=False, max_length=64)),
                ('texto', models.CharField(max_length=1000)),
                ('origen', models.CharField(choices=[('SIN_EVIDENCIA', 'Sin evidencia'), ('ANALISIS', 'Análisis')], max_length=20)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('respuesta', models.TextField(blank=True, default='')),
                ('fecha_respuesta', models.DateTimeField(blank=True, null=True)),
                ('respondido_por', models.ForeignKey(blank=True, null=True, db_column='respondido_por', on_delete=django.db.models.deletion.PROTECT, related_name='preguntas_respondidas', to=settings.AUTH_USER_MODEL)),
                ('valoracion', models.ForeignKey(db_column='valoracion_id', on_delete=django.db.models.deletion.CASCADE, related_name='preguntas_complementarias', to='data.valoracionsubfactor')),
            ],
            options={'db_table': 'pregunta_complementaria', 'ordering': ['pregunta_id'],
                     'constraints': [models.UniqueConstraint(fields=('valoracion', 'clave'), name='pregunta_valoracion_clave_unica')]},
        ),
    ]
