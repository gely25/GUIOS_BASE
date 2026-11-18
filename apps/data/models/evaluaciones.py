"""
Gestión de evaluaciones: software, evaluación, factores evaluados y valoraciones.
"""

from django.db import models
from django.db.models import Q

from .catalogo import CatalogoVersion, Factor, Subfactor
from .usuarios import Organizacion, Usuario


class Software(models.Model):
    software_id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=150)
    version = models.CharField(max_length=50, blank=True, null=True)
    proveedor = models.CharField(max_length=150, blank=True, null=True)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'software'

    def __str__(self):
        return self.nombre


class Evaluacion(models.Model):
    evaluacion_id = models.BigAutoField(primary_key=True)
    organizacion = models.ForeignKey(
        Organizacion, on_delete=models.PROTECT, db_column='organizacion_id', related_name='evaluaciones')
    usuario = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, db_column='usuario_id', related_name='evaluaciones')
    software = models.ForeignKey(
        Software, on_delete=models.PROTECT, db_column='software_id', related_name='evaluaciones')
    catalogo = models.ForeignKey(
        CatalogoVersion, on_delete=models.PROTECT, db_column='catalogo_id', related_name='evaluaciones')
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=30, default='EN_PROCESO')

    class Meta:
        db_table = 'evaluacion'


class EvaluacionFactor(models.Model):
    """Valores de un factor dentro de una evaluación: IS, ID, IR, PM y FODA."""

    evaluacion_factor_id = models.BigAutoField(primary_key=True)
    evaluacion = models.ForeignKey(
        Evaluacion, on_delete=models.CASCADE, db_column='evaluacion_id', related_name='factores')
    factor = models.ForeignKey(
        Factor, on_delete=models.PROTECT, db_column='factor_id', related_name='evaluaciones')
    importancia_sugerida = models.IntegerField(null=True, blank=True)
    importancia_decisor = models.IntegerField(null=True, blank=True)
    importancia_relativa = models.IntegerField(null=True, blank=True)
    ponderacion_media = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    clasificacion_foda = models.CharField(max_length=20, null=True, blank=True)
    relevante = models.BooleanField(default=True)

    class Meta:
        db_table = 'evaluacion_factor'
        constraints = [
            models.UniqueConstraint(fields=['evaluacion', 'factor'], name='evalfactor_evaluacion_factor_unico'),
            models.CheckConstraint(
                condition=Q(clasificacion_foda__isnull=True)
                | Q(clasificacion_foda__in=['Fortaleza', 'Oportunidad', 'Debilidad', 'Amenaza']),
                name='evalfactor_foda_valido'),
            models.CheckConstraint(
                condition=Q(importancia_decisor__isnull=True) | Q(importancia_decisor__range=(1, 4)),
                name='evalfactor_id_1_a_4'),
            models.CheckConstraint(
                condition=Q(importancia_relativa__isnull=True) | Q(importancia_relativa__range=(1, 4)),
                name='evalfactor_ir_1_a_4'),
        ]


class ValoracionSubfactor(models.Model):
    """Valoración de un subfactor: propuesta de la IA y valor confirmado por el decisor."""

    PENDIENTE = 'PENDIENTE'

    valoracion_id = models.BigAutoField(primary_key=True)
    evaluacion_factor = models.ForeignKey(
        EvaluacionFactor, on_delete=models.CASCADE, db_column='evaluacion_factor_id',
        related_name='valoraciones')
    subfactor = models.ForeignKey(
        Subfactor, on_delete=models.PROTECT, db_column='subfactor_id', related_name='valoraciones')
    valor_ia = models.IntegerField(null=True, blank=True)
    valor_confirmado = models.IntegerField(null=True, blank=True)
    justificacion_ia = models.TextField(blank=True, null=True)
    justificacion_decisor = models.TextField(blank=True, null=True)
    estado_validacion = models.CharField(max_length=30, default=PENDIENTE)
    fecha_validacion = models.DateTimeField(null=True, blank=True)
    validado_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, null=True, blank=True, db_column='validado_por',
        related_name='valoraciones_validadas')

    class Meta:
        db_table = 'valoracion_subfactor'
        constraints = [
            models.UniqueConstraint(
                fields=['evaluacion_factor', 'subfactor'], name='valoracion_evalfactor_subfactor_unico'),
            models.CheckConstraint(
                condition=Q(valor_ia__isnull=True) | Q(valor_ia__range=(1, 4)), name='valoracion_ia_1_a_4'),
            models.CheckConstraint(
                condition=Q(valor_confirmado__isnull=True) | Q(valor_confirmado__range=(1, 4)),
                name='valoracion_confirmado_1_a_4'),
        ]
