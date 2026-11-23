"""Vista del historial de evaluaciones (HU15)."""

from django.shortcuts import render
from django.urls import reverse

from apps.application.services.historial import HistorialEvaluacionesService


def historial_evaluaciones_view(request):
    filas = HistorialEvaluacionesService.cargar(request.user)
    return render(request, "presentation/decisor/historial_evaluaciones.html", {
        "evaluaciones": filas,
        "active_tab": "historial-evaluaciones",
        "url_inicio": reverse("presentation:decisor-inicio"),
        "url_nueva": reverse("presentation:decisor-ficha-inicial"),
    })
