"""
Resultado final de una evaluación (una por evaluación).
"""

from django.db import models

from .evaluaciones import Evaluacion


class ResultadoEvaluacion(models.Model):
    resultado_id = models.BigAutoField(primary_key=True)
    evaluacion = models.OneToOneField(
        Evaluacion, on_delete=models.CASCADE, db_column='evaluacion_id', related_name='resultado')
    recomendacion = models.TextField()
    explicacion = models.TextField(blank=True, null=True)
    version_regla = models.CharField(max_length=30)
    fecha_generacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'resultado_evaluacion'
