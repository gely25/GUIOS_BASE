from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('data', '0007_revision_humana')]
    operations = [migrations.CreateModel(
        name='BorradorRevisionHumana', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('modo', models.CharField(blank=True, default='', max_length=12)),
            ('valor', models.IntegerField(blank=True, null=True)),
            ('justificacion', models.TextField(blank=True, default='')),
            ('huella_contexto', models.CharField(max_length=64)),
            ('version', models.PositiveBigIntegerField(default=1)),
            ('fecha', models.DateTimeField(auto_now=True)),
            ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='data.usuario')),
            ('valoracion', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='borrador_hu11', to='data.valoracionsubfactor')),
        ], options={'db_table': 'borrador_revision_humana', 'constraints': [
            models.CheckConstraint(condition=models.Q(valor__isnull=True) | models.Q(valor__range=(1, 4)), name='borrador_hu11_valor_1_a_4')]},
    )]
