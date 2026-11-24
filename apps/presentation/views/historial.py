"""Vista del historial de evaluaciones (HU15)."""

from django.shortcuts import render
from django.urls import reverse

from apps.application.services.historial import HistorialEvaluacionesService


def historial_evaluaciones_view(request):
    filas = HistorialEvaluacionesService.cargar(request.user)
    return render(request, "presentation/decisor/historial_evaluaciones.html", {
        "evaluaciones": filas,
        "total": len(filas),
        "con_informe": sum(1 for fila in filas if fila.tiene_recomendacion),
        "en_curso": sum(1 for fila in filas if fila.estado == "En curso"),
        "active_tab": "historial-evaluaciones",
        "url_inicio": reverse("presentation:decisor-inicio"),
        "url_nueva": reverse("presentation:decisor-ficha-inicial"),
    })
