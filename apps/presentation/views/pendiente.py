"""
Vista unificada de módulos pendientes de implementación - GUIOS PRO.
"""

from django.shortcuts import render

from apps.presentation.screens import get_pending_module_data


def modulo_pendiente_view(request, nombre_modulo, area, referencia_figma=None, descripcion_extra=None):
    """
    Recibe el nombre del módulo, el área y metadatos, y muestra el mensaje
    «Módulo no disponible» con el enlace «Volver al inicio» al área de origen.
    El acceso por rol lo controla el middleware, no esta vista.
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
    }
    return render(request, 'presentation/comun/modulo_pendiente.html', context)
