"""
Información bibliográfica: búsquedas, publicaciones y su relación con los factores.
"""

from django.db import models

from .catalogo import Factor


class BusquedaBibliografica(models.Model):
    busqueda_id = models.BigAutoField(primary_key=True)
    consulta = models.TextField()
    fuente = models.CharField(max_length=150)
    anio_inicio = models.IntegerField(null=True, blank=True)
    anio_fin = models.IntegerField(null=True, blank=True)
    fecha_ejecucion = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=30, blank=True, null=True)

    class Meta:
        db_table = 'busqueda_bibliografica'


class Publicacion(models.Model):
    publicacion_id = models.BigAutoField(primary_key=True)
    titulo = models.TextField()
    anio = models.IntegerField(null=True, blank=True)
    doi = models.CharField(max_length=255, unique=True, null=True, blank=True)
    url = models.TextField(blank=True, null=True)
    resumen = models.TextField(blank=True, null=True)
    fuente = models.CharField(max_length=150, blank=True, null=True)

    class Meta:
        db_table = 'publicacion'

    def __str__(self):
        return self.titulo[:80]


class BusquedaPublicacion(models.Model):
    """Tabla intermedia búsqueda <-> publicación."""

    busqueda = models.ForeignKey(
        BusquedaBibliografica, on_delete=models.CASCADE, db_column='busqueda_id', related_name='resultados')
    publicacion = models.ForeignKey(
        Publicacion, on_delete=models.CASCADE, db_column='publicacion_id', related_name='busquedas')
    posicion = models.IntegerField(null=True, blank=True)
    fecha_recuperacion = models.DateTimeField(null=True, blank=True)
    seleccionada = models.BooleanField(default=False)

    class Meta:
        db_table = 'busqueda_publicacion'
        constraints = [
            models.UniqueConstraint(fields=['busqueda', 'publicacion'], name='busqpub_busqueda_publicacion_unico'),
        ]


class PublicacionFactor(models.Model):
    publicacion_factor_id = models.BigAutoField(primary_key=True)
    publicacion = models.ForeignKey(
        Publicacion, on_delete=models.CASCADE, db_column='publicacion_id', related_name='factores')
    factor = models.ForeignKey(
        Factor, on_delete=models.PROTECT, db_column='factor_id', related_name='publicaciones')
    pertinencia = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    justificacion = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'publicacion_factor'
        constraints = [
            models.UniqueConstraint(fields=['publicacion', 'factor'], name='pubfactor_publicacion_factor_unico'),
        ]
