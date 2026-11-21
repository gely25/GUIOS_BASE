"""
Servicio de Aplicación: CatalogService.

Capa: application. Catálogo metodológico: dimensiones, factores, subfactores y sus versiones (HU05).
"""

from django.core.exceptions import ValidationError

from apps.data.models import CatalogoVersion


class CatalogService:
    """Catálogo metodológico: dimensiones, factores, subfactores y sus versiones (HU05)."""

    @staticmethod
    def obtener_version_vigente(*, bloquear=False):
        """
        Devuelve la única versión activa.

        Si bloquear=True, bloquea la fila mientras se crea la evaluación.
        La restricción de base de datos complementa esta validación.
        """
        catalogos = CatalogoVersion.objects.filter(estado='ACTIVO')
        if bloquear:
            catalogos = catalogos.select_for_update()

        encontrados = list(catalogos.order_by('catalogo_id')[:2])

        if not encontrados:
            raise ValidationError(
                'No existe una versión vigente del catálogo de factores.'
            )

        if len(encontrados) > 1:
            raise ValidationError(
                'Existe más de una versión activa del catálogo metodológico. '
                'Debe existir una única versión vigente.'
            )

        return encontrados[0]
