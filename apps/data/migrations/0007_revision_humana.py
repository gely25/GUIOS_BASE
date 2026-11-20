from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('data', '0006_historial_suficiencia')]
    operations = [migrations.CreateModel(
        name='RevisionHumana', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('modo', models.CharField(choices=[('CONFIRMAR', 'Confirmar'), ('MODIFICAR', 'Modificar'), ('MANUAL', 'Manual')], max_length=12)),
            ('valor_ia', models.IntegerField(blank=True, null=True)),
            ('justificacion_ia', models.TextField(blank=True, default='')),
            ('valor', models.IntegerField()),
            ('justificacion', models.TextField()),
            ('huella_contexto', models.CharField(max_length=64)),
            ('fuentes', models.JSONField(default=list)),
            ('fecha', models.DateTimeField(default=django.utils.timezone.now)),
            ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='data.usuario')),
            ('valoracion', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='revisiones_humanas', to='data.valoracionsubfactor')),
        ], options={'db_table': 'revision_humana', 'ordering': ['-fecha', '-pk'],
            'constraints': [models.CheckConstraint(condition=models.Q(valor__range=(1, 4)), name='revision_humana_valor_1_a_4')]},
    )]
