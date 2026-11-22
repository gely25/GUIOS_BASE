"""
Vistas de Resultados e Informe (HU14) - Espacio del Decisor.

Capa: presentation. Pide los datos a ReportService y renderiza; no calcula nada.
El decisor solo ve sus propias evaluaciones (el servicio filtra por usuario).
"""

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from apps.application.services.report import InformeNoDisponible, ReportService
from apps.application.services.resultados import ResultadosService


def _evaluacion_pedida(request):
    """Id de evaluación de la URL (?evaluacion=N). None si no vino; 404 si no es un número."""
    valor = request.GET.get('evaluacion')
    if valor is None or valor == '':
        return None
    if not valor.isdigit():
        raise Http404('Evaluación no válida.')
    return int(valor)


def _cargar(request):
    """(informe, id_pedido). informe es None si el decisor aún no tiene resultados."""
    evaluacion_id = _evaluacion_pedida(request)
    try:
        return ReportService().informe(request.user, evaluacion_id), evaluacion_id
    except InformeNoDisponible:
        if evaluacion_id is not None:
            raise Http404('Evaluación no encontrada.')
        return None, None


def _contexto(informe, pantalla):
    url_informe = reverse('presentation:decisor-informe')
    url_resultados = reverse('presentation:decisor-resultados')
    sufijo = f'?evaluacion={informe.evaluacion_id}' if informe else ''
    return {
        'informe': informe,
        'active_tab': pantalla,
        'url_resultados': url_resultados + sufijo,
        'url_informe': url_informe + sufijo,
        'url_pdf': f'{url_informe}?evaluacion={informe.evaluacion_id}&formato=pdf' if informe else None,
        'url_inicio': reverse('presentation:decisor-inicio'),
    }


def resultados_view(request):
    """Resultados (paso 5): PM y FODA calculados por HU12, y la recomendación si ya existe."""
    evaluacion_id = _evaluacion_pedida(request)
    try:
        resultados = ResultadosService.cargar(request.user, evaluacion_id)
    except InformeNoDisponible:
        if evaluacion_id is not None:
            raise Http404('Evaluación no encontrada.')
        resultados = None
    base = reverse('presentation:decisor-revision-valoraciones')
    url_informe = reverse('presentation:decisor-informe')
    contexto = {
        'resultados': resultados, 'active_tab': 'resultados',
        'url_inicio': reverse('presentation:decisor-inicio'),
    }
    if resultados is not None:
        contexto['url_anterior'] = f'{base}?etapa=validacion&evaluacion={resultados.evaluacion_id}'
        contexto['url_informe'] = f'{url_informe}?evaluacion={resultados.evaluacion_id}'
    return render(request, 'presentation/decisor/resultados.html', contexto)


def informe_view(request):
    informe, _ = _cargar(request)
    if informe is not None and request.GET.get('formato') == 'pdf':
        servicio = ReportService()
        respuesta = HttpResponse(servicio.generar_pdf(informe), content_type='application/pdf')
        respuesta['Content-Disposition'] = f'attachment; filename="{servicio.nombre_archivo(informe)}"'
        return respuesta
    return render(request, 'presentation/decisor/informe.html', _contexto(informe, 'informe'))
