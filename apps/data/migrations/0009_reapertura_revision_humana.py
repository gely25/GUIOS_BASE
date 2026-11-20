from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('data', '0008_borrador_revision_humana')]
    operations = [migrations.CreateModel(
        name='ReaperturaRevisionHumana', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('motivo', models.TextField()),
            ('decision_anterior', models.JSONField(default=dict)),
            ('resultados_anteriores', models.JSONField(default=dict)),
            ('fecha', models.DateTimeField(default=django.utils.timezone.now)),
            ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='data.usuario')),
            ('valoracion', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                related_name='reaperturas_hu11', to='data.valoracionsubfactor')),
        ], options={'db_table': 'reapertura_revision_humana', 'ordering': ['-fecha', '-pk']},
    )]
