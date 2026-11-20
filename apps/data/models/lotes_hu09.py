"""Cola persistente de análisis de suficiencia por evaluación."""
from django.db import models
from .evaluaciones import Evaluacion
from .usuarios import Usuario


class LoteHU09(models.Model):
    evaluacion = models.ForeignKey(Evaluacion, on_delete=models.CASCADE, related_name='lotes_hu09')
    solicitante = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="lotes_hu09_solicitados")
    estado = models.CharField(max_length=16, default='EN_COLA')
    objetivos = models.JSONField(default=list)
    resultados = models.JSONField(default=list)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'lote_hu09'
        constraints = [models.UniqueConstraint(fields=['evaluacion'], condition=models.Q(estado__in=['EN_COLA', 'EN_PROCESO']), name='hu09_un_lote_activo')]
