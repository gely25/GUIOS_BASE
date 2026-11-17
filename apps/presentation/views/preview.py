"""
Utilidades de vista previa local - GUIOS PRO.

Capa: presentation.
"""

from functools import wraps

from django.conf import settings
from django.http import Http404


def require_debug_preview(view_func):
    """
    Decorador de seguridad para rutas de vista previa local.
    Si DEBUG=False lanza Http404, de modo que ninguna ruta de vista previa
    quede expuesta en producción.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not settings.DEBUG:
            raise Http404("Las rutas de vista previa local están deshabilitadas en producción.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view
