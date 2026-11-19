"""Respuestas complementarias del decisor (HU09), separadas de la evidencia documental."""
from django.db import models

from .evaluaciones import ValoracionSubfactor
from .usuarios import Usuario


class PreguntaComplementaria(models.Model):
    pregunta_id = models.BigAutoField(primary_key=True)
    valoracion = models.ForeignKey(
        ValoracionSubfactor, on_delete=models.CASCADE, related_name='preguntas_complementarias',
        db_column='valoracion_id')
    clave = models.CharField(max_length=64, editable=False)
    texto = models.CharField(max_length=1000)
    origen = models.CharField(max_length=20, choices=[('SIN_EVIDENCIA', 'Sin evidencia'), ('ANALISIS', 'Análisis')])
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    respuesta = models.TextField(blank=True, default='')
    respondido_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, null=True, blank=True,
        related_name='preguntas_respondidas', db_column='respondido_por')
    fecha_respuesta = models.DateTimeField(null=True, blank=True)

    descartada_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, null=True, blank=True,
        related_name='preguntas_descartadas', db_column='descartada_por')
    fecha_descarte = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'pregunta_complementaria'
        ordering = ['pregunta_id']
        constraints = [models.UniqueConstraint(fields=['valoracion', 'clave'], name='pregunta_valoracion_clave_unica')]
