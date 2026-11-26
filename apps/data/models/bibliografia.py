"""
Información bibliográfica: búsquedas, publicaciones y su relación con los factores (HU02).
"""

from django.db import models
from django.db.models import Q

from .catalogo import Factor


class BusquedaBibliografica(models.Model):
    """
    Una consulta a una fuente científica. Las búsquedas lanzadas juntas comparten `lote`.
    El trabajo lo hace `manage.py procesar_busquedas` en segundo plano; `estado` y
    `progreso` permiten seguirlo desde la interfaz.
    """

    PENDIENTE = 'PENDIENTE'
    EN_CURSO = 'EN_CURSO'
    COMPLETADA = 'COMPLETADA'
    FALLIDA = 'FALLIDA'
    ESTADOS = [(PENDIENTE, 'Pendiente'), (EN_CURSO, 'En curso'),
               (COMPLETADA, 'Completada'), (FALLIDA, 'Fallida')]

    busqueda_id = models.BigAutoField(primary_key=True)
    consulta = models.TextField()
    fuente = models.CharField(max_length=150)
    anio_inicio = models.IntegerField(null=True, blank=True)
    anio_fin = models.IntegerField(null=True, blank=True)
    fecha_ejecucion = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=30, choices=ESTADOS, default=PENDIENTE, blank=True, null=True)
    lote = models.UUIDField(null=True, blank=True, db_index=True)
    factor = models.ForeignKey(
        Factor, on_delete=models.PROTECT, null=True, blank=True,
        db_column='factor_id', related_name='busquedas')
    lanzada_por = models.ForeignKey(
        'data.Usuario', on_delete=models.PROTECT, null=True, blank=True,
        db_column='lanzada_por', related_name='+')
    progreso = models.PositiveSmallIntegerField(default=0)
    total_resultados = models.IntegerField(default=0)
    mensaje_error = models.TextField(blank=True, null=True)
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    analisis_ia_completado = models.BooleanField(default=False)

    class Meta:
        db_table = 'busqueda_bibliografica'
        constraints = [
            models.CheckConstraint(
                condition=Q(estado__isnull=True) | Q(estado__in=['PENDIENTE', 'EN_CURSO', 'COMPLETADA', 'FALLIDA']),
                name='busqueda_estado_valido'),
            models.CheckConstraint(condition=Q(progreso__lte=100), name='busqueda_progreso_0_100'),
            models.CheckConstraint(
                condition=Q(anio_inicio__isnull=True) | Q(anio_fin__isnull=True) | Q(anio_inicio__lte=models.F('anio_fin')),
                name='busqueda_rango_anios_valido'),
        ]


class Publicacion(models.Model):
    publicacion_id = models.BigAutoField(primary_key=True)
    titulo = models.TextField()
    anio = models.IntegerField(null=True, blank=True)
    doi = models.CharField(max_length=255, unique=True, null=True, blank=True)
    url = models.TextField(blank=True, null=True)
    resumen = models.TextField(blank=True, null=True)
    fuente = models.CharField(max_length=150, blank=True, null=True)
    # Clave de deduplicación: hash del DOI normalizado o, si no hay DOI, del título normalizado + año.
    huella = models.CharField(max_length=64, unique=True, null=True, blank=True)

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
    """
    Vínculo publicación <-> factor. Solo los APROBADOS cuentan para el TC.
    `origen` dice si lo propuso la regla de palabras clave o lo creó el administrador.
    """

    MANUAL = 'MANUAL'
    PALABRAS_CLAVE = 'PALABRAS_CLAVE'
    IA = 'IA'
    ORIGENES = [(MANUAL, 'Manual'), (PALABRAS_CLAVE, 'Palabras clave'), (IA, 'Inteligencia artificial')]

    SUGERIDA = 'SUGERIDA'
    APROBADA = 'APROBADA'
    RECHAZADA = 'RECHAZADA'
    ESTADOS = [(SUGERIDA, 'Sugerida'), (APROBADA, 'Aprobada'), (RECHAZADA, 'Rechazada')]

    publicacion_factor_id = models.BigAutoField(primary_key=True)
    publicacion = models.ForeignKey(
        Publicacion, on_delete=models.CASCADE, db_column='publicacion_id', related_name='factores')
    factor = models.ForeignKey(
        Factor, on_delete=models.PROTECT, db_column='factor_id', related_name='publicaciones')
    pertinencia = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    justificacion = models.TextField(blank=True, null=True)
    origen = models.CharField(max_length=20, choices=ORIGENES, default=MANUAL)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=SUGERIDA)
    revisado_por = models.ForeignKey(
        'data.Usuario', on_delete=models.PROTECT, null=True, blank=True,
        db_column='revisado_por', related_name='+')
    fecha_revision = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'publicacion_factor'
        constraints = [
            models.UniqueConstraint(fields=['publicacion', 'factor'], name='pubfactor_publicacion_factor_unico'),
            models.CheckConstraint(
                condition=Q(origen__in=['MANUAL', 'PALABRAS_CLAVE', 'IA']), name='pubfactor_origen_valido'),
            models.CheckConstraint(
                condition=Q(estado__in=['SUGERIDA', 'APROBADA', 'RECHAZADA']), name='pubfactor_estado_valido'),
            models.CheckConstraint(
                condition=Q(pertinencia__isnull=True) | Q(pertinencia__range=(0, 100)),
                name='pubfactor_pertinencia_0_100'),
        ]
