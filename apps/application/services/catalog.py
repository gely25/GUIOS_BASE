"""
Servicio de Aplicación: CatalogService.

Capa: application. Catálogo metodológico: dimensiones, factores, subfactores y sus versiones (HU05).
"""

from django.core.exceptions import ValidationError

from apps.data.models import CatalogoVersion


class CatalogService:
    """Catálogo metodológico: dimensiones, factores, subfactores y sus versiones (HU05)."""

    @staticmethod
    def obtener_version_vigente():
        """Devuelve la versión activa vigente; no crea ni modifica catálogos."""
        catalogo = CatalogoVersion.objects.filter(estado='ACTIVO').order_by('-fecha_creacion', '-pk').first()
        if catalogo is None:
            raise ValidationError('No existe una versión vigente del catálogo de factores.')
        return catalogo
