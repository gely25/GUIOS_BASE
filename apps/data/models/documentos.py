"""
Documentos y evidencias: archivos cargados, fragmentos con embedding (pgvector) y evidencia.
"""

from django.db import models
from pgvector.django import VectorField

from .evaluaciones import Evaluacion, ValoracionSubfactor
from .usuarios import Usuario

DIMENSIONES_EMBEDDING = 1536


class Documento(models.Model):
    documento_id = models.BigAutoField(primary_key=True)
    evaluacion = models.ForeignKey(
        Evaluacion, on_delete=models.CASCADE, db_column='evaluacion_id', related_name='documentos')
    usuario = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, db_column='usuario_id', related_name='documentos')
    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20)
    ubicacion = models.TextField()
    version = models.CharField(max_length=50, blank=True, null=True)
    hash_sha256 = models.CharField(max_length=64, blank=True, null=True)
    fecha_carga = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'documento'


class FragmentoDocumento(models.Model):
    fragmento_id = models.BigAutoField(primary_key=True)
    documento = models.ForeignKey(
        Documento, on_delete=models.CASCADE, db_column='documento_id', related_name='fragmentos')
    pagina = models.IntegerField(null=True, blank=True)
    seccion = models.CharField(max_length=255, blank=True, null=True)
    hoja = models.CharField(max_length=255, blank=True, null=True)
    contenido = models.TextField()
    embedding = VectorField(dimensions=DIMENSIONES_EMBEDDING, null=True, blank=True)

    class Meta:
        db_table = 'fragmento_documento'


class Evidencia(models.Model):
    evidencia_id = models.BigAutoField(primary_key=True)
    valoracion = models.ForeignKey(
        ValoracionSubfactor, on_delete=models.CASCADE, db_column='valoracion_id', related_name='evidencias')
    fragmento = models.ForeignKey(
        FragmentoDocumento, on_delete=models.PROTECT, db_column='fragmento_id', related_name='evidencias')
    relevancia = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    referencia = models.TextField(blank=True, null=True)
    justificacion = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'evidencia'
