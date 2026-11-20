from django.db import migrations, models
import django.db.models.deletion


def conservar_anteriores(apps, schema_editor):
    Analisis = apps.get_model('data', 'AnalisisSuficiencia')
    Historial = apps.get_model('data', 'HistorialSuficiencia')
    alias = schema_editor.connection.alias
    for r in Analisis.objects.using(alias).iterator():
        Historial.objects.using(alias).create(valoracion_id=r.valoracion_id, huella=r.huella,
            estado=r.estado, justificacion=r.justificacion, referencias=r.referencias,
            rondas=r.rondas, modelo=r.modelo, fecha=r.fecha, legado=True)


class Migration(migrations.Migration):
    dependencies = [('data', '0005_lotes_hu09')]
    operations = [migrations.CreateModel(
        name='HistorialSuficiencia', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('huella', models.CharField(max_length=64)),
            ('estado', models.CharField(max_length=24)),
            ('justificacion', models.TextField()),
            ('referencias', models.JSONField(default=list)),
            ('rondas', models.PositiveIntegerField(default=0)),
            ('modelo', models.CharField(max_length=100)),
            ('fecha', models.DateTimeField()),
            ('legado', models.BooleanField(default=False)),
            ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='data.usuario')),
            ('valoracion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                related_name='historial_suficiencia', to='data.valoracionsubfactor')),
        ], options={'db_table': 'historial_suficiencia', 'ordering': ['-fecha', '-pk']},
    ), migrations.RunPython(conservar_anteriores, migrations.RunPython.noop)]
