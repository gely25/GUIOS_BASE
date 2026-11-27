"""Estado compartido de admisión y deduplicación de solicitudes de IA."""
from django.db import models


class UnidadCuotaIA(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    cooldown_hasta = models.DateTimeField(null=True)


class CredencialBloqueadaIA(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    estado_http = models.PositiveSmallIntegerField()
    bloqueada = models.DateTimeField(auto_now_add=True)


class TareaIA(models.Model):
    class Estado(models.TextChoices):
        DISPONIBLE = 'DISPONIBLE'
        EN_CURSO = 'EN_CURSO'
        COMPLETADA = 'COMPLETADA'
        INCIERTA = 'INCIERTA'

    id = models.CharField(max_length=64, primary_key=True)
    estado = models.CharField(max_length=12, choices=Estado, default=Estado.DISPONIBLE)
    propietario = models.UUIDField(null=True)
    vence = models.DateTimeField(null=True, db_index=True)
    resultado = models.JSONField(null=True)
    identificador = models.CharField(max_length=120, blank=True)


class IntentoIA(models.Model):
    tarea = models.ForeignKey(TareaIA, on_delete=models.PROTECT, related_name='intentos')
    unidad = models.ForeignKey(UnidadCuotaIA, on_delete=models.PROTECT)
    proveedor = models.CharField(max_length=20)
    modelo = models.CharField(max_length=92)
    operacion = models.CharField(max_length=20)
    inicio = models.DateTimeField()
    vence = models.DateTimeField()
    fin = models.DateTimeField(null=True)
    error = models.CharField(max_length=32, blank=True)
    tokens_reservados = models.PositiveBigIntegerField(default=0)
    tokens_observados = models.PositiveBigIntegerField(null=True)
    unidades_reservadas = models.PositiveBigIntegerField(default=0)
    tokens_cuota = models.PositiveBigIntegerField(null=True)
    unidades_cuota = models.PositiveBigIntegerField(null=True)
    latencia_ms = models.PositiveIntegerField(null=True)
    espera_ms = models.PositiveIntegerField()
    fallback = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=['unidad', 'inicio'], name='ia_unidad_inicio_idx')]
        constraints = [models.UniqueConstraint(
            fields=['tarea'], condition=models.Q(fin__isnull=True), name='ia_un_intento_activo_por_tarea',
        )]
