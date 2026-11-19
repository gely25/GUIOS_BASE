"""Resultado orientativo de suficiencia de HU09, sin puntuaciones."""
from django.db import models
from .evaluaciones import ValoracionSubfactor


class AnalisisSuficiencia(models.Model):
    valoracion = models.OneToOneField(ValoracionSubfactor, on_delete=models.CASCADE,
                                     related_name='analisis_suficiencia')
    huella = models.CharField(max_length=64)
    estado = models.CharField(max_length=24)
    justificacion = models.TextField()
    referencias = models.JSONField(default=list)
    rondas = models.PositiveIntegerField(default=0)
    modelo = models.CharField(max_length=100)
    fecha = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analisis_suficiencia'


class HistorialSuficiencia(models.Model):
    """Registro de conclusiones; no duplica el contenido de los documentos."""
    valoracion = models.ForeignKey(ValoracionSubfactor, on_delete=models.CASCADE,
                                   related_name='historial_suficiencia')
    actor = models.ForeignKey('data.Usuario', on_delete=models.PROTECT, null=True, blank=True)
    huella = models.CharField(max_length=64)
    estado = models.CharField(max_length=24)
    justificacion = models.TextField()
    referencias = models.JSONField(default=list)
    rondas = models.PositiveIntegerField(default=0)
    modelo = models.CharField(max_length=100)
    fecha = models.DateTimeField()
    legado = models.BooleanField(default=False)

    class Meta:
        db_table = 'historial_suficiencia'
        ordering = ['-fecha', '-pk']
