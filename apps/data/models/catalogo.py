"""
Catálogo metodológico GUIOS: dimensión, factor, subfactor, versión e indicadores.
"""

from django.db import models
from django.db.models import Q


class Dimension(models.Model):
    dimension_id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = 'dimension'

    def __str__(self):
        return self.nombre


class Factor(models.Model):
    INTERNO = 'interno'
    EXTERNO = 'externo'
    AMBOS = 'ambos'  # solo Soporte: el decisor elige uno al evaluar
    ALCANCES = [(INTERNO, 'Interno'), (EXTERNO, 'Externo'), (AMBOS, 'Interno o externo')]

    factor_id = models.BigAutoField(primary_key=True)
    dimension = models.ForeignKey(
        Dimension, on_delete=models.PROTECT, db_column='dimension_id', related_name='factores')
    nombre = models.CharField(max_length=150)
    alcance = models.CharField(max_length=20, choices=ALCANCES)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'factor'
        constraints = [
            models.UniqueConstraint(fields=['dimension', 'nombre'], name='factor_dimension_nombre_unico'),
            models.CheckConstraint(
                condition=Q(alcance__in=['interno', 'externo', 'ambos']), name='factor_alcance_valido'),
        ]

    def __str__(self):
        return self.nombre


class Subfactor(models.Model):
    subfactor_id = models.BigAutoField(primary_key=True)
    factor = models.ForeignKey(
        Factor, on_delete=models.PROTECT, db_column='factor_id', related_name='subfactores')
    descripcion = models.TextField()
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'subfactor'

    def __str__(self):
        return self.descripcion[:60]


class CatalogoVersion(models.Model):
    catalogo_id = models.BigAutoField(primary_key=True)
    version = models.CharField(max_length=30, unique=True)
    fecha_creacion = models.DateField()
    estado = models.CharField(max_length=20, default='ACTIVO')

    class Meta:
        db_table = 'catalogo_version'

    def __str__(self):
        return self.version


class IndicadorFactor(models.Model):
    """Indicadores de un factor en una versión del catálogo (NS, TC, r_i, IE, IL, IS)."""

    indicador_id = models.BigAutoField(primary_key=True)
    catalogo = models.ForeignKey(
        CatalogoVersion, on_delete=models.PROTECT, db_column='catalogo_id', related_name='indicadores')
    factor = models.ForeignKey(
        Factor, on_delete=models.PROTECT, db_column='factor_id', related_name='indicadores')
    numero_subfactores = models.IntegerField()
    total_citas = models.IntegerField(default=0, null=True)
    relacion_ri = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    importancia_experto = models.IntegerField(null=True, blank=True)
    importancia_literatura = models.IntegerField(null=True, blank=True)
    importancia_sugerida = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'indicador_factor'
        constraints = [
            models.UniqueConstraint(fields=['catalogo', 'factor'], name='indicador_catalogo_factor_unico'),
            models.CheckConstraint(
                condition=Q(importancia_experto__isnull=True) | Q(importancia_experto__range=(1, 4)),
                name='indicador_ie_1_a_4'),
            models.CheckConstraint(
                condition=Q(importancia_literatura__isnull=True) | Q(importancia_literatura__range=(1, 4)),
                name='indicador_il_1_a_4'),
            models.CheckConstraint(
                condition=Q(importancia_sugerida__isnull=True) | Q(importancia_sugerida__range=(1, 4)),
                name='indicador_is_1_a_4'),
        ]
