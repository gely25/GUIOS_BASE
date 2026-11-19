from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('data', '0003_descarte_preguntas')]
    operations = [migrations.CreateModel(
        name='AnalisisSuficiencia',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('huella', models.CharField(max_length=64)),
            ('estado', models.CharField(max_length=24)),
            ('justificacion', models.TextField()),
            ('referencias', models.JSONField(default=list)),
            ('rondas', models.PositiveIntegerField(default=0)),
            ('modelo', models.CharField(max_length=100)),
            ('fecha', models.DateTimeField(auto_now=True)),
            ('valoracion', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                 related_name='analisis_suficiencia', to='data.valoracionsubfactor')),
        ], options={'db_table': 'analisis_suficiencia'},
    )]
