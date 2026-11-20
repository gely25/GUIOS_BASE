"""Registro de la decisión humana de HU11, separado de la propuesta IA."""
from django.db import models
from django.utils import timezone
from .evaluaciones import ValoracionSubfactor
from .usuarios import Usuario


class RevisionHumana(models.Model):
    valoracion = models.ForeignKey(ValoracionSubfactor, on_delete=models.PROTECT,
                                   related_name='revisiones_humanas')
    actor = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    modo = models.CharField(max_length=12, choices=[('CONFIRMAR', 'Confirmar'),
        ('MODIFICAR', 'Modificar'), ('MANUAL', 'Manual')])
    valor_ia = models.IntegerField(null=True, blank=True)
    justificacion_ia = models.TextField(blank=True, default='')
    valor = models.IntegerField()
    justificacion = models.TextField()
    huella_contexto = models.CharField(max_length=64)
    fuentes = models.JSONField(default=list)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'revision_humana'
        ordering = ['-fecha', '-pk']
        constraints = [models.CheckConstraint(condition=models.Q(valor__range=(1, 4)),
                           name='revision_humana_valor_1_a_4')]


class BorradorRevisionHumana(models.Model):
    """Trabajo en curso: no constituye una valoración confirmada."""
    valoracion = models.OneToOneField(ValoracionSubfactor, on_delete=models.CASCADE,
                                     related_name='borrador_hu11')
    actor = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    modo = models.CharField(max_length=12, blank=True, default='')
    valor = models.IntegerField(null=True, blank=True)
    justificacion = models.TextField(blank=True, default='')
    huella_contexto = models.CharField(max_length=64)
    version = models.PositiveBigIntegerField(default=1)
    fecha = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'borrador_revision_humana'
        constraints = [models.CheckConstraint(condition=models.Q(valor__isnull=True) | models.Q(valor__range=(1, 4)),
                           name='borrador_hu11_valor_1_a_4')]


class ReaperturaRevisionHumana(models.Model):
    """Evento de reapertura; conserva la decisión invalidada y resultados previos."""
    valoracion = models.ForeignKey(ValoracionSubfactor, on_delete=models.PROTECT,
                                    related_name='reaperturas_hu11')
    actor = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    motivo = models.TextField()
    decision_anterior = models.JSONField(default=dict)
    resultados_anteriores = models.JSONField(default=dict)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'reapertura_revision_humana'
        ordering = ['-fecha', '-pk']
