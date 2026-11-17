"""
Vistas del Espacio del Decisor - GUIOS PRO.
"""

from django.shortcuts import render
from apps.presentation.screens import get_decisor_dashboard_data
from .preview import require_debug_preview


@require_debug_preview
def decisor_home_view(request):
    """
    Vista de la pantalla «Decisor · Inicio» (Figma nodo 7:2970).
    Muestra el espacio de trabajo del decisor y el estado de las evaluaciones.
    """
    dashboard_data = get_decisor_dashboard_data()
    context = {
        'dashboard': dashboard_data,
        'active_tab': 'inicio',
        'preview_mode': True,
    }
    return render(request, 'presentation/decisor/decisor_home.html', context)
