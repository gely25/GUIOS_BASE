"""
Vistas del Área de Administración - GUIOS PRO.
"""

from django.shortcuts import render
from apps.presentation.screens import get_admin_dashboard_data
from .preview import require_debug_preview


@require_debug_preview
def admin_home_view(request):
    """
    Vista de la pantalla «Administración · Usuarios y roles» (Figma nodo 7:4928).
    Punto de entrada accesible mediante:
    - /vista-previa/administracion/
    - /vista-previa/administracion/usuarios-roles/
    """
    admin_data = get_admin_dashboard_data()
    context = {
        'dashboard': admin_data,
        'active_tab': 'usuarios-roles',
        'preview_mode': True,
    }
    return render(request, 'presentation/administracion/admin_home.html', context)
