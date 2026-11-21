"""
Fuentes científicas externas para la actualización bibliográfica (HU02).
"""

from django.conf import settings

from .base import ErrorFuenteCientifica, FuenteCientifica, ResultadoPublicacion
from .openalex import OpenAlexFuente

__all__ = ['ErrorFuenteCientifica', 'FuenteCientifica', 'ResultadoPublicacion', 'OpenAlexFuente',
           'fuente_configurada']


def fuente_configurada() -> FuenteCientifica:
    """La fuente definida en settings (variables BIBLIOGRAPHIC_* del .env)."""
    return OpenAlexFuente(
        url_base=settings.BIBLIOGRAPHIC_BASE_URL,
        api_key=settings.BIBLIOGRAPHIC_API_KEY,
        timeout=settings.BIBLIOGRAPHIC_TIMEOUT,
    )
