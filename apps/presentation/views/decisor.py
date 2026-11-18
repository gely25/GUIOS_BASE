"""
Vistas del Espacio del Decisor - GUIOS PRO.
"""

from django.shortcuts import render

from apps.presentation.screens import get_decisor_dashboard_data


def decisor_home_view(request):
    """
    Pantalla «Decisor · Inicio» (Figma nodo 7:2970).
    Muestra el espacio de trabajo del decisor y el estado de las evaluaciones.
    """
    context = {
        'dashboard': get_decisor_dashboard_data(),
        'active_tab': 'inicio',
    }
    return render(request, 'presentation/decisor/decisor_home.html', context)
