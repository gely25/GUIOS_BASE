from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('data', '0002_pregunta_complementaria')]
    operations = [
        migrations.AddField(
            model_name='preguntacomplementaria', name='descartada_por',
            field=models.ForeignKey(blank=True, null=True, db_column='descartada_por',
                on_delete=django.db.models.deletion.PROTECT, related_name='preguntas_descartadas',
                to=settings.AUTH_USER_MODEL)),
        migrations.AddField(
            model_name='preguntacomplementaria', name='fecha_descarte',
            field=models.DateTimeField(blank=True, null=True)),
    ]
