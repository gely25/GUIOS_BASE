"""
Vista de Indicadores de literatura (HU-03) - GUIOS PRO.

Capa: presentation. Solo pide los indicadores al servicio de aplicación y
renderiza la página; no hace cálculos.
"""

from django.shortcuts import render

from apps.application.services.indicadores_literatura import obtener_indicadores_literatura


def indicadores_literatura_view(request):
    context = {
        'indicadores': obtener_indicadores_literatura(),
        'active_tab': 'actualizacion-bibliografica',
    }
    return render(request, 'presentation/administracion/indicadores_literatura_preview.html', context)
