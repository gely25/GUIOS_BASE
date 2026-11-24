"""Inicio del decisor: indicadores y continuidad de evaluaciones propias.

Referencia visual: GUIOS_2, pantalla 'Decisor · Inicio'.
Los datos se obtienen de la BD. No se reproducen números del mockup.
"""

from django.core.paginator import Paginator
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from apps.application.services.informe.documento import letra_de
from apps.data.models import Documento, Evaluacion, EvaluacionFactor, ValoracionSubfactor
from apps.presentation.screens import get_decisor_dashboard_data


def _progreso_evaluacion(evaluacion):
    """Deriva un paso sugerido y avance HU11 sin alterar las valoraciones."""
    base = ValoracionSubfactor.objects.filter(
        evaluacion_factor__evaluacion=evaluacion,
        evaluacion_factor__relevante=True,
    ).exclude(evaluacion_factor__importancia_relativa=1)
    total = base.count()
    confirmadas = base.filter(valor_confirmado__isnull=False).count()
    porcentaje = round((100 * confirmadas / total)) if total else 0

    if total:
        paso, nombre = 4, 'Revisión de evidencia'
        enlace = reverse('presentation:decisor-revision-valoraciones') + (
            f'?etapa=validacion&evaluacion={evaluacion.pk}'
        )
    elif Documento.objects.filter(evaluacion=evaluacion).exists():
        paso, nombre = 4, 'Revisión de evidencia'
        enlace = reverse('presentation:decisor-revision-valoraciones') + (
            f'?evaluacion={evaluacion.pk}'
        )
    elif EvaluacionFactor.objects.filter(evaluacion=evaluacion).exists():
        paso, nombre = 3, 'Carga documental'
        enlace = reverse('presentation:decisor-carga-documental') + (
            f'?evaluacion_id={evaluacion.pk}'
        )
    else:
        # La ficha fue creada: el siguiente paso pendiente es la ponderación.
        paso, nombre = 2, 'Valoración de factores'
        enlace = reverse('presentation:decisor-importancia-factores') + (
            f'?evaluacion_id={evaluacion.pk}'
        )

    return {
        'paso': paso,
        'nombre_paso': nombre,
        'total': total,
        'confirmadas': confirmadas,
        'porcentaje': min(100, max(0, porcentaje)),
        'enlace': enlace,
    }


PASOS = ('Ficha', 'Valoración', 'Documentos', 'Revisión', 'Resultados', 'Informe')
POR_PAGINA = 5


def _pasos(paso):
    """Estado de cada uno de los 6 pasos: hecho, actual o pendiente."""
    return [
        {'numero': n, 'nombre': nombre,
         'estado': 'hecho' if n < paso else ('actual' if n == paso else 'pendiente')}
        for n, nombre in enumerate(PASOS, start=1)
    ]


def _actividad(fecha, hoy):
    """'Hoy' o la fecha corta; el decisor no necesita la hora exacta en la tabla."""
    local = timezone.localtime(fecha)
    return {'es_hoy': local.date() == hoy, 'fecha': local}


def decisor_home_view(request):
    """Página de inicio personal del decisor, basada en Figma."""
    usuario = request.user
    evaluaciones = list(
        Evaluacion.objects.filter(usuario=usuario)
        .select_related('software', 'organizacion', 'resultado')
        .order_by('-fecha_actualizacion', '-evaluacion_id')
    )
    en_curso = [ev for ev in evaluaciones if ev.estado == Evaluacion.EN_PROCESO]
    completadas = [ev for ev in evaluaciones if ev.estado == Evaluacion.CERRADA]

    # 'Documentos revisados' = documentos que realmente alimentaron
    # una valoración confirmada. No confundir con todos los archivos subidos.
    documentos_revisados = (
        Documento.objects.filter(
            evaluacion__usuario=usuario,
            fragmentos__evidencias__valoracion__valor_confirmado__isnull=False,
        ).distinct().count()
    )

    actual = en_curso[0] if en_curso else None
    progreso = _progreso_evaluacion(actual) if actual else None
    hoy = timezone.localdate()
    if actual:
        progreso['pasos'] = _pasos(progreso['paso'])
        progreso['anillo'] = round(100 * progreso['paso'] / len(PASOS))
        progreso['documentos'] = Documento.objects.filter(evaluacion=actual).count()
        progreso['actividad'] = _actividad(actual.fecha_actualizacion, hoy)

    paginador = Paginator(evaluaciones, POR_PAGINA)
    pagina = paginador.get_page(request.GET.get('pagina'))
    recientes = []
    for ev in pagina.object_list:
        nombre = ev.software.nombre
        if ev.software.version:
            nombre = f'{nombre} {ev.software.version}'
        recomendacion = getattr(getattr(ev, 'resultado', None), 'recomendacion', None)
        if ev.estado == Evaluacion.CERRADA and (recomendacion or '').strip():
            url = reverse('presentation:decisor-informe') + f'?evaluacion={ev.pk}'
            accion = 'Ver informe'
        elif ev.estado == Evaluacion.CERRADA:
            url = reverse('presentation:decisor-resultados') + f'?evaluacion={ev.pk}'
            accion = 'Ver resultados'
        else:
            url = reverse('presentation:decisor-importancia-factores') + f'?evaluacion_id={ev.pk}'
            accion = 'Continuar'
        paso = len(PASOS) if ev.estado == Evaluacion.CERRADA else _progreso_evaluacion(ev)['paso']
        recientes.append({
            'codigo': f'EV-{ev.pk:03d}',
            'software': nombre,
            'inicial': (ev.software.nombre or '?')[:1].upper(),
            'paso': paso,
            'segmentos': [n <= paso for n in range(1, len(PASOS) + 1)],
            'letra': letra_de(recomendacion or ''),
            'actividad': _actividad(ev.fecha_actualizacion, hoy),
            'estado': ev.get_estado_display(),
            'en_curso': ev.estado == Evaluacion.EN_PROCESO,
            'accion': accion,
            'url': url,
        })

    hora = timezone.localtime().hour
    saludo = 'Buenos días' if hora < 12 else ('Buenas tardes' if hora < 19 else 'Buenas noches')

    return render(request, 'presentation/decisor/decisor_home.html', {
        'dashboard': get_decisor_dashboard_data(),
        'active_tab': 'inicio',
        'saludo': saludo,
        'nombre_decisor': usuario.get_short_name() or 'Decisor',
        'indicadores': {
            'total': len(evaluaciones),
            'en_proceso': len(en_curso),
            'cerradas': len(completadas),
            'documentos_revisados': documentos_revisados,
        },
        'evaluacion_actual': actual,
        'progreso': progreso,
        'evaluaciones_recientes': recientes,
        'pagina': pagina,
        'rango_paginas': list(paginador.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        'pasos_vacios': _pasos(0),
        'hay_evaluaciones': bool(evaluaciones),
        'total_evaluaciones': len(evaluaciones),
    })
