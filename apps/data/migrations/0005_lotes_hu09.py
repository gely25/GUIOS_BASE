from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('data', '0004_analisis_suficiencia')]
    operations = [migrations.CreateModel(
        name='LoteHU09', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('estado', models.CharField(default='EN_COLA', max_length=16)),
            ('objetivos', models.JSONField(default=list)),
            ('resultados', models.JSONField(default=list)),
            ('creado', models.DateTimeField(auto_now_add=True)),
            ('actualizado', models.DateTimeField(auto_now=True)),
            ('solicitante', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='lotes_hu09_solicitados', to='data.usuario')),
            ('evaluacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lotes_hu09', to='data.evaluacion')),
        ], options={'db_table': 'lote_hu09', 'constraints': [models.UniqueConstraint(fields=('evaluacion',), condition=models.Q(estado__in=['EN_COLA', 'EN_PROCESO']), name='hu09_un_lote_activo')]},
    )]
