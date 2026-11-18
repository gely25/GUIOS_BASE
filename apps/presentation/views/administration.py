"""
Vistas del Área de Administración - GUIOS PRO.
"""

from django.shortcuts import render

from apps.presentation.screens import get_admin_dashboard_data


def admin_home_view(request):
    """
    Pantalla «Administración · Usuarios y roles» (Figma nodo 7:4928).
    Se abre en /administracion/ y en /administracion/usuarios-roles/.
    """
    context = {
        'dashboard': get_admin_dashboard_data(),
        'active_tab': 'usuarios-roles',
    }
    return render(request, 'presentation/administracion/admin_home.html', context)
