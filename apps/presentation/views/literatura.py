"""
Vista de Indicadores de literatura (HU-03) - GUIOS PRO.

Capa: presentation. Solo pide los indicadores al servicio de aplicación y
renderiza la página de vista previa; no hace cálculos.
"""

from django.shortcuts import render

from apps.application.services.indicadores_literatura import obtener_indicadores_literatura
from .preview import require_debug_preview


@require_debug_preview
def indicadores_literatura_view(request):
    context = {
        'indicadores': obtener_indicadores_literatura(),
        'active_tab': 'actualizacion-bibliografica',
        'preview_mode': True,
    }
    return render(request, 'presentation/administracion/indicadores_literatura_preview.html', context)
