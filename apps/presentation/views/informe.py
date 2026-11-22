"""
Vistas de Resultados e Informe (HU14) - Espacio del Decisor.

Capa: presentation. Pide los datos a ReportService y renderiza; no calcula nada.
El decisor solo ve sus propias evaluaciones (el servicio filtra por usuario).
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.application.services.pm_foda import PmFodaService
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


def _alcances(params):
    """Elecciones interno/externo del formulario: campos `alcance_<id del factor>`."""
    return {int(k[8:]): v for k, v in params.items() if k.startswith('alcance_') and k[8:].isdigit()}


def resultados_view(request):
    """
    Resultados (paso 5): aquí se calculan y se muestran la PM y el FODA (HU12).

    Si las valoraciones ya están confirmadas y aún no hay PM, ofrece calcularla (con la
    elección interno/externo de Soporte). La recomendación final llega de otra historia.
    """
    if request.method == 'POST':
        crudo = request.POST.get('evaluacion', '')
        if not crudo.isdigit():
            raise Http404('Evaluación no válida.')
        eid = int(crudo)
        try:
            filas = PmFodaService.calcular_y_guardar(request.user, eid, _alcances(request.POST))
            messages.success(request, f'PM y FODA calculados y guardados para {len(filas)} factores.')
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
        return redirect(reverse('presentation:decisor-resultados') + '?' + urlencode({'evaluacion': eid}))

    evaluacion_id = _evaluacion_pedida(request)
    evaluacion = ResultadosService.evaluacion_de(request.user, evaluacion_id)
    if evaluacion is None and evaluacion_id is not None:
        raise Http404('Evaluación no encontrada.')
    try:
        resultados = ResultadosService.cargar(request.user, evaluacion.pk) if evaluacion else None
    except InformeNoDisponible:
        resultados = None
    preparacion = PmFodaService.vista_previa(request.user, evaluacion.pk) if evaluacion else None

    revision = reverse('presentation:decisor-revision-valoraciones')
    url_informe = reverse('presentation:decisor-informe')
    contexto = {
        'resultados': resultados, 'preparacion': preparacion, 'evaluacion': evaluacion,
        'active_tab': 'resultados', 'url_inicio': reverse('presentation:decisor-inicio'),
    }
    if evaluacion is not None:
        contexto['url_anterior'] = f'{revision}?evaluacion={evaluacion.pk}'
        contexto['url_informe'] = f'{url_informe}?evaluacion={evaluacion.pk}'
    return render(request, 'presentation/decisor/resultados.html', contexto)


def informe_view(request):
    informe, _ = _cargar(request)
    if informe is not None and request.GET.get('formato') == 'pdf':
        servicio = ReportService()
        respuesta = HttpResponse(servicio.generar_pdf(informe), content_type='application/pdf')
        respuesta['Content-Disposition'] = f'attachment; filename="{servicio.nombre_archivo(informe)}"'
        return respuesta
    return render(request, 'presentation/decisor/informe.html', _contexto(informe, 'informe'))
