"""
Vistas y utilidades de vista previa local - GUIOS PRO.
"""

from functools import wraps
from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from apps.presentation.screens import get_pending_module_data


def require_debug_preview(view_func):
    """
    Decorador de seguridad para rutas de vista previa local.
    Si DEBUG=False, deniega el acceso lanzando un error Http404,
    garantizando que ninguna ruta de vista previa quede expuesta en producción.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not settings.DEBUG:
            raise Http404("Las rutas de vista previa local están deshabilitadas en producción.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


@require_debug_preview
def modulo_pendiente_view(request, nombre_modulo, area, referencia_figma=None, descripcion_extra=None):
    """
    Vista unificada para módulos pendientes de implementación.
    Recibe el nombre del módulo, área y metadatos, mostrando el mensaje
    «Módulo no disponible» y el enlace «Volver al inicio» que regresa al área de origen.
    """
    module_data = get_pending_module_data(
        nombre_modulo=nombre_modulo,
        area=area,
        referencia_figma=referencia_figma,
        descripcion_extra=descripcion_extra,
    )
    context = {
        'modulo': module_data,
        'active_tab': nombre_modulo.lower().replace(' ', '-'),
        'preview_mode': True,
    }
    return render(request, 'presentation/comun/modulo_pendiente.html', context)
