"""Interfaz HU09 y HU10 sobre la ruta de revisión de evidencia y valoración preliminar."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.application.services.ai import AIService, ESCALA_HU10
from apps.application.services.preguntas import PreguntasService, estado_respuesta
from apps.application.services.analisis_preguntas import AnalisisPreguntasService, MAX_PENDIENTES
from apps.external_services.ai_errors import AnalisisNoDisponible
from apps.data.models import Evaluacion, Evidencia, HistorialSuficiencia, ValoracionSubfactor
from apps.application.services.suficiencia import SuficienciaService
from apps.application.services.preparacion_hu10 import PreparacionHU10Service
from apps.application.services.lotes_hu09 import LotesHU09Service, ACTIVOS
from apps.external_services.proveedor_ia import obtener_proveedor, modelo_activo, configurado


_ETIQUETAS_HU10 = {
    'PROPUESTA_HABILITADA': 'Contexto disponible para propuesta preliminar',
    'REVISION_MANUAL': 'Revisión manual necesaria',
    'PREGUNTAS_PENDIENTES': 'Preguntas pendientes',
    'ANALISIS_EN_CURSO': 'Análisis en curso',
    'SOLO_LECTURA': 'Solo lectura',
    'ANALISIS_PENDIENTE': 'Análisis pendiente o desactualizado',
}


def _id(valor):
    try:
        numero = int(valor)
        if not 0 < numero <= 9223372036854775807:
            raise ValueError
        return numero
    except (ValueError, TypeError):
        return None


def _resumen_hu10(evaluacion, filas, lote, valoraciones, modelo):
    abierta = evaluacion.estado == 'EN_PROCESO' and evaluacion.fecha_fin is None
    activo = (lote or {}).get('estado') in ACTIVOS
    habilitados = pendientes = generadas = 0
    resumen_filas = {}
    for fila in filas:
        estado = PreparacionHU10Service.estado(fila, abierta, activo)
        valoracion = valoraciones.get(fila['valoracion_id'])
        valor = valoracion.valor_ia if valoracion else None
        justificacion = valoracion.justificacion_ia if valoracion else ''
        tiene_valor = valor in ESCALA_HU10
        tiene_propuesta = tiene_valor and bool((justificacion or '').strip())
        fila.update(estado_hu10=estado, etiqueta_estado_hu10=_ETIQUETAS_HU10[estado],
                    valor_ia=valor, justificacion_ia=justificacion,
                    etiqueta_ia=ESCALA_HU10.get(valor, ''), tiene_propuesta_hu10=tiene_propuesta)
        habilitado = estado == 'PROPUESTA_HABILITADA'
        resumen_filas[fila['valoracion_id']] = {'etiqueta': _ETIQUETAS_HU10[estado],
                                               'disponible': bool(modelo and habilitado)}
        habilitados += habilitado
        pendientes += habilitado and not tiene_valor
        generadas += tiene_propuesta
    return {'habilitados': habilitados, 'pendientes': pendientes, 'generadas': generadas,
            'disponible': bool(modelo and pendientes), 'filas': resumen_filas}


def _valoraciones_hu10(filas):
    return ValoracionSubfactor.objects.only('valor_ia', 'justificacion_ia').in_bulk(
        [fila['valoracion_id'] for fila in filas],
    )


def _hu10_para_sondeo(evaluacion, lote, filas=None):
    if (lote or {}).get('estado') in ACTIVOS:
        return None
    if filas is None:
        filas = SuficienciaService.adjuntar(PreguntasService._contexto(evaluacion))
    return _resumen_hu10(evaluacion, filas, lote, _valoraciones_hu10(filas), modelo_activo('valoracion'))


@require_http_methods(['GET', 'POST'])
def preguntas_view(request):
    if not request.user.is_authenticated or request.user.rol != 'DECISOR' or not request.user.activo:
        raise PermissionDenied
    if (request.POST if request.method == 'POST' else request.GET).get('etapa') == 'validacion':
        from .revision_humana import revision_humana_view
        return revision_humana_view(request)
    evaluaciones = Evaluacion.objects.filter(usuario=request.user).select_related('software').order_by('-fecha_inicio', '-pk')
    url = reverse('presentation:decisor-revision-valoraciones')
    raw = request.POST.get('evaluacion') if request.method == 'POST' else request.GET.get('evaluacion')
    if raw is None and request.method == 'GET':
        return render(request, 'presentation/decisor/preguntas.html', {'evaluaciones': evaluaciones})
    eid = _id(raw)
    if eid is None:
        return HttpResponseBadRequest('Evaluación inválida.')
    evaluacion = PreguntasService._evaluacion(request.user, eid)
    if request.method == "GET" and request.GET.get("estado_lote") == "1":
        lote = LotesHU09Service.estado_de(evaluacion)
        respuesta = JsonResponse({"lote": lote, "hu10": _hu10_para_sondeo(evaluacion, lote)})
        respuesta["Cache-Control"] = "no-store"
        return respuesta
    if request.method == 'POST' and request.POST.get('accion') == 'autoguardar':
        pid = _id(request.POST.get('pregunta'))
        if pid is None or 'version' not in request.POST:
            return JsonResponse({'error': 'Pregunta o versión inválida.'}, status=400)
        try:
            p = PreguntasService.responder(request.user, eid, pid, request.POST.get('respuesta', ''), version=request.POST['version'])
        except ValidationError as exc:
            return JsonResponse({'error': ' '.join(exc.messages)}, status=400)
        filas = SuficienciaService.adjuntar(PreguntasService._contexto(evaluacion))
        fila = next((f for f in filas if f['valoracion_id'] == p.valoracion_id), None)
        if fila is None:
            raise PermissionDenied
        preguntas = [q for f in filas for q in f['preguntas']]
        lote = LotesHU09Service.estado_de(evaluacion)
        return JsonResponse({'respuesta': p.respuesta, 'version': p.fecha_respuesta.isoformat() if p.fecha_respuesta else '',
                             'fecha': timezone.localtime(p.fecha_respuesta).strftime('%d/%m/%Y %H:%M') if p.fecha_respuesta else '',
                             'estado': estado_respuesta(p.respuesta), 'estado_informacion': fila['estado_informacion'],
                             'vigente': fila['suficiencia_vigente'], 'total': len(preguntas),
                             'no_informativas': sum(q['estado_respuesta'] == 'NO_INFORMATIVA' for q in preguntas),
                             'respondidas': sum(bool(q['respuesta']) for q in preguntas),
                             'desconocidas': sum(q['estado_respuesta'] == 'DESCONOCE' for q in preguntas),
                             'hu10': _hu10_para_sondeo(evaluacion, lote, filas),
                             'lote_activo': (lote or {}).get('estado') in ACTIVOS})
    error = None
    respuesta_enviada = None
    pid = None
    if request.method == 'POST':
        accion = request.POST.get('accion')
        try:
            if accion == 'lote':
                if not configurado():
                    raise ValidationError('El servicio de IA no está configurado. Puede continuar manualmente.')
                lote = LotesHU09Service.encolar(request.user, eid)
                messages.success(request, f'Análisis #{lote.pk} en cola o en curso para los subfactores disponibles.')
            elif accion in ('suficiencia', 'analizar', 'valorar_hu10', 'valorar_hu10_lote') and (
                (LotesHU09Service.estado_de(evaluacion) or {}).get('estado') in ACTIVOS
            ):
                raise ValidationError('Hay un análisis masivo activo. Espere a que termine la evaluación de suficiencia.')
            elif accion == 'detectar':
                nuevas = PreguntasService.detectar_sin_evidencia(request.user, eid)
                messages.success(request, f'Preguntas nuevas registradas: {len(nuevas)}. La evidencia disponible aún requiere análisis semántico.')
            elif accion == 'suficiencia':
                vid = _id(request.POST.get('valoracion'))
                if vid is None:
                    return HttpResponseBadRequest('Subfactor inválido.')
                if not configurado():
                    raise ValidationError('El servicio de IA no está configurado. Puede continuar manualmente.')
                proveedor = obtener_proveedor('suficiencia')
                registro, cantidad = SuficienciaService.analizar(request.user, eid, vid, proveedor, modelo_activo())
                messages.success(request, f'Revisión de suficiencia: {cantidad} preguntas nuevas. Consulte el resultado orientativo del subfactor.')
            elif accion == 'analizar':
                vid = _id(request.POST.get('valoracion'))
                if vid is None:
                    return HttpResponseBadRequest('Subfactor inválido.')
                if not configurado():
                    raise ValidationError('El servicio de IA no está configurado. Puede continuar manualmente.')
                analizador = obtener_proveedor('preguntas')
                nuevas = AnalisisPreguntasService.analizar(request.user, eid, analizador, valoracion_id=vid)
                messages.success(request, f'Análisis IA del subfactor: {len(nuevas)} preguntas nuevas. El resultado no certifica suficiencia.')
            elif accion == 'valorar_hu10':
                vid = _id(request.POST.get('valoracion'))
                if vid is None:
                    return HttpResponseBadRequest('Subfactor inválido.')
                if not modelo_activo('valoracion'):
                    raise ValidationError('La IA no está disponible para generar valoraciones preliminares. Puede continuar manualmente.')
                proveedor_hu10 = obtener_proveedor('valoracion')
                propuesta = AIService.generar_propuesta_preliminar(request.user, eid, vid, proveedor_hu10)
                messages.success(
                    request,
                    f"Propuesta preliminar IA generada ({propuesta['valor_ia']}/4 · {propuesta['etiqueta']}) con fuentes {', '.join(propuesta['referencias'])}. Lista para validación humana."
                )
            elif accion == 'valorar_hu10_lote':
                if not modelo_activo('valoracion'):
                    raise ValidationError('La IA no está disponible para generar valoraciones preliminares. Puede continuar manualmente.')
                proveedor_hu10 = obtener_proveedor('valoracion')
                resumen_lote = AIService.generar_propuestas_pendientes(request.user, eid, proveedor_hu10)
                if resumen_lote['generadas']:
                    messages.success(
                        request,
                        f"Propuestas preliminares generadas: {resumen_lote['generadas']} de {resumen_lote['pendientes']} pendientes."
                    )
                    if resumen_lote['errores']:
                        messages.warning(request, f"{len(resumen_lote['errores'])} propuestas quedaron pendientes. "
                                         f"{resumen_lote['errores'][0]}")
                elif resumen_lote['errores']:
                    raise ValidationError(resumen_lote['errores'][0])
                else:
                    messages.success(request, 'No hay subfactores habilitados pendientes de valoración preliminar.')
            elif accion in ('descartar', 'restaurar'):
                pid = _id(request.POST.get('pregunta'))
                if pid is None:
                    return HttpResponseBadRequest('Pregunta inválida.')
                if accion == 'restaurar':
                    PreguntasService.restaurar(request.user, eid, pid)
                    messages.success(request, 'Pregunta restaurada. Se conserva la auditoría del descarte.')
                else:
                    PreguntasService.descartar(request.user, eid, pid,
                        confirmar=request.POST.get('confirmar') == '1', version=request.POST.get('version'))
                    messages.success(request, 'Pregunta descartada. Se conserva en el historial.')
            elif accion in ('responder', 'desconozco'):
                pid = _id(request.POST.get('pregunta'))
                if pid is None:
                    return HttpResponseBadRequest('Pregunta inválida.')
                respuesta_enviada = 'No lo sé' if accion == 'desconozco' else request.POST.get('respuesta', '')
                PreguntasService.responder(request.user, eid, pid, respuesta_enviada, version=request.POST.get('version'))
                messages.success(request, 'Respuesta guardada correctamente.')
            else:
                return HttpResponseBadRequest('Acción inválida.')
            return redirect(f'{url}?evaluacion={eid}')
        except ValidationError as exc:
            error = ' '.join(exc.messages)
        except AnalisisNoDisponible as exc:
            error = str(exc)
    filas = SuficienciaService.adjuntar(PreguntasService._contexto(evaluacion))
    total = sum(len(f['preguntas']) for f in filas)
    respondidas = sum(bool(p['respuesta']) for f in filas for p in f['preguntas'])
    desconocidas = sum(p['estado_respuesta'] == 'DESCONOCE' for f in filas for p in f['preguntas'])
    lote_actual = LotesHU09Service.estado_de(evaluacion)
    lote_activo = (lote_actual or {}).get('estado') in ACTIVOS
    historial = {}
    for registro in HistorialSuficiencia.objects.filter(valoracion_id__in=[f['valoracion_id'] for f in filas]):
        historial.setdefault(registro.valoracion_id, []).append(registro)
    modelo_hu10 = modelo_activo('valoracion')
    hu10 = _resumen_hu10(evaluacion, filas, lote_actual, _valoraciones_hu10(filas), modelo_hu10)
    evidencias_doc_map = {
        e.pk: e.fragmento.documento_id
        for e in Evidencia.objects.filter(valoracion_id__in=[f['valoracion_id'] for f in filas]).select_related('fragmento')
    }
    for f in filas:
        f['historial'] = historial.get(f['valoracion_id'], [])
        for ev_item in f['evidencias']:
            ev_item['documento_id'] = evidencias_doc_map.get(ev_item['evidencia_id'])
        f['sin_pendientes'] = not any(p['estado_respuesta'] == 'PENDIENTE' for p in f['preguntas'])
        f['cupo_ia'] = max(0, MAX_PENDIENTES - sum(p['estado_respuesta'] == 'PENDIENTE' for p in f['preguntas']))
        for p in f['preguntas']:
            p['version'] = p['fecha_respuesta'].isoformat() if p['fecha_respuesta'] else ''
            p['borrador'] = respuesta_enviada if error and p['pregunta_id'] == pid else p['respuesta']
    return render(request, 'presentation/decisor/preguntas.html', {
        'evaluaciones': evaluaciones, 'evaluacion': evaluacion, 'filas': filas,
        'lote': lote_actual, 'lote_activo': lote_activo,
        'no_informativas': sum(p['estado_respuesta'] == 'NO_INFORMATIVA' for f in filas for p in f['preguntas']),
        'total': total, 'respondidas': respondidas, 'pendientes': total - respondidas,
        'desconocidas': desconocidas, 'descartadas': sum(len(f['preguntas_descartadas']) for f in filas),
        'habilitados_hu10': hu10['habilitados'],
        'propuestas_hu10_listas': hu10['generadas'],
        'hu10': hu10,
        'modelo_ia': modelo_activo(),
        'modelo_hu10': modelo_hu10,
        'modelo_embeddings': '', 'error': error,
        'editable': evaluacion.estado == 'EN_PROCESO' and evaluacion.fecha_fin is None,
    }, status=400 if error else 200)
