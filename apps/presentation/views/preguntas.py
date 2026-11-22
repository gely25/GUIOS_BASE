"""Interfaz HU09 y HU10 sobre la ruta de revisión de evidencia y valoración preliminar."""
from django.conf import settings
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
from apps.external_services.ollama_preguntas import AnalisisNoDisponible, OllamaPreguntas
from apps.external_services.ollama_embeddings import OllamaEmbeddings
from apps.external_services.ollama_valoracion import OllamaValoracion
from apps.data.models import Evaluacion, Evidencia, HistorialSuficiencia, ValoracionSubfactor
from apps.application.services.suficiencia import SuficienciaService
from apps.application.services.preparacion_hu10 import PreparacionHU10Service
from apps.application.services.lotes_hu09 import LotesHU09Service, ACTIVOS
from apps.external_services.ollama_suficiencia import OllamaSuficiencia


def _id(valor):
    try:
        numero = int(valor)
        if not 0 < numero <= 9223372036854775807:
            raise ValueError
        return numero
    except (ValueError, TypeError):
        return None


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
        respuesta = JsonResponse({"lote": LotesHU09Service.estado(request.user, eid)})
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
        filas = SuficienciaService.adjuntar(PreguntasService.contexto(request.user, eid))
        fila = next((f for f in filas if f['valoracion_id'] == p.valoracion_id), None)
        if fila is None:
            raise PermissionDenied
        preguntas = [q for f in filas for q in f['preguntas']]
        return JsonResponse({'respuesta': p.respuesta, 'version': p.fecha_respuesta.isoformat() if p.fecha_respuesta else '',
                             'fecha': timezone.localtime(p.fecha_respuesta).strftime('%d/%m/%Y %H:%M') if p.fecha_respuesta else '',
                             'estado': estado_respuesta(p.respuesta), 'estado_informacion': fila['estado_informacion'],
                             'vigente': fila['suficiencia_vigente'], 'total': len(preguntas),
                             'no_informativas': sum(q['estado_respuesta'] == 'NO_INFORMATIVA' for q in preguntas),
                             'respondidas': sum(bool(q['respuesta']) for q in preguntas),
                             'desconocidas': sum(q['estado_respuesta'] == 'DESCONOCE' for q in preguntas)})
    error = None
    respuesta_enviada = None
    pid = None
    if request.method == 'POST':
        accion = request.POST.get('accion')
        try:
            if accion == 'lote':
                if not settings.HU09_OLLAMA_MODEL:
                    raise ValidationError('El análisis local con IA no está configurado.')
                lote = LotesHU09Service.encolar(request.user, eid)
                messages.success(request, f'Lote #{lote.pk} en cola o en curso. El trabajador HU09 procesará los subfactores disponibles.')
            elif accion in ('suficiencia', 'analizar') and (LotesHU09Service.estado(request.user, eid) or {}).get('estado') in ACTIVOS:
                raise ValidationError('Hay un análisis masivo activo. Espere a que termine antes de iniciar otro análisis individual.')
            elif accion == 'detectar':
                nuevas = PreguntasService.detectar_sin_evidencia(request.user, eid)
                messages.success(request, f'Preguntas nuevas registradas: {len(nuevas)}. La evidencia disponible aún requiere análisis semántico.')
            elif accion == 'suficiencia':
                vid = _id(request.POST.get('valoracion'))
                if vid is None:
                    return HttpResponseBadRequest('Subfactor inválido.')
                if not settings.HU09_OLLAMA_MODEL:
                    raise ValidationError('El análisis local con IA no está configurado.')
                proveedor = OllamaSuficiencia(settings.HU09_OLLAMA_MODEL)
                vectorizador = OllamaEmbeddings(settings.HU09_EMBEDDING_MODEL) if settings.HU09_EMBEDDING_MODEL else None
                registro, cantidad = SuficienciaService.analizar(request.user, eid, vid, proveedor, settings.HU09_OLLAMA_MODEL, vectorizador)
                messages.success(request, f'Revisión de suficiencia: {cantidad} preguntas nuevas. Consulte el resultado orientativo del subfactor.')
            elif accion == 'analizar':
                vid = _id(request.POST.get('valoracion'))
                if vid is None:
                    return HttpResponseBadRequest('Subfactor inválido.')
                if not settings.HU09_OLLAMA_MODEL:
                    raise ValidationError('El análisis local con IA no está configurado.')
                analizador = OllamaPreguntas(settings.HU09_OLLAMA_MODEL)
                vectorizador = OllamaEmbeddings(settings.HU09_EMBEDDING_MODEL) if settings.HU09_EMBEDDING_MODEL else None
                nuevas = AnalisisPreguntasService.analizar(request.user, eid, analizador, valoracion_id=vid, vectorizador=vectorizador)
                messages.success(request, f'Análisis IA del subfactor: {len(nuevas)} preguntas nuevas. El resultado no certifica suficiencia.')
            elif accion == 'valorar_hu10':
                vid = _id(request.POST.get('valoracion'))
                if vid is None:
                    return HttpResponseBadRequest('Subfactor inválido.')
                modelo_hu10 = getattr(settings, 'HU10_OLLAMA_MODEL', '') or settings.HU09_OLLAMA_MODEL
                if not modelo_hu10:
                    raise ValidationError('Configure un modelo local HU10 admitido.')
                proveedor_hu10 = OllamaValoracion(modelo_hu10)
                propuesta = AIService.generar_propuesta_preliminar(request.user, eid, vid, proveedor_hu10)
                messages.success(
                    request,
                    f"Propuesta preliminar IA generada ({propuesta['valor_ia']}/4 · {propuesta['etiqueta']}) con fuentes {', '.join(propuesta['referencias'])}. Lista para revisión humana (HU11)."
                )
            elif accion == 'valorar_hu10_lote':
                modelo_hu10 = getattr(settings, 'HU10_OLLAMA_MODEL', '') or settings.HU09_OLLAMA_MODEL
                if not modelo_hu10:
                    raise ValidationError('Configure un modelo local HU10 admitido.')
                proveedor_hu10 = OllamaValoracion(modelo_hu10)
                resumen_lote = AIService.generar_propuestas_pendientes(request.user, eid, proveedor_hu10)
                if resumen_lote['generadas']:
                    messages.success(
                        request,
                        f"Propuestas preliminares HU10 generadas: {resumen_lote['generadas']} de {resumen_lote['pendientes']} pendientes."
                    )
                elif resumen_lote['errores']:
                    raise ValidationError(resumen_lote['errores'][0])
                else:
                    messages.success(request, 'No hay subfactores habilitados pendientes de valoración preliminar HU10.')
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
    filas = SuficienciaService.adjuntar(PreguntasService.contexto(request.user, eid))
    total = sum(len(f['preguntas']) for f in filas)
    respondidas = sum(bool(p['respuesta']) for f in filas for p in f['preguntas'])
    desconocidas = sum(p['estado_respuesta'] == 'DESCONOCE' for f in filas for p in f['preguntas'])
    lote_actual = LotesHU09Service.estado(request.user, eid)
    evaluacion_abierta = evaluacion.estado == 'EN_PROCESO' and evaluacion.fecha_fin is None
    historial = {}
    for registro in HistorialSuficiencia.objects.filter(valoracion_id__in=[f['valoracion_id'] for f in filas]):
        historial.setdefault(registro.valoracion_id, []).append(registro)
    valoraciones_map = {
        v.pk: v
        for v in ValoracionSubfactor.objects.filter(valoracion_id__in=[f['valoracion_id'] for f in filas])
    }
    evidencias_doc_map = {
        e.pk: e.fragmento.documento_id
        for e in Evidencia.objects.filter(valoracion_id__in=[f['valoracion_id'] for f in filas]).select_related('fragmento')
    }
    for f in filas:
        f['historial'] = historial.get(f['valoracion_id'], [])
        f['estado_hu10'] = PreparacionHU10Service.estado(f, evaluacion_abierta, (lote_actual or {}).get('estado') in ACTIVOS)
        val_obj = valoraciones_map.get(f['valoracion_id'])
        f['valor_ia'] = val_obj.valor_ia if val_obj else None
        f['justificacion_ia'] = val_obj.justificacion_ia if val_obj else ''
        f['etiqueta_ia'] = ESCALA_HU10.get(f['valor_ia'], '')
        f['tiene_propuesta_hu10'] = f['valor_ia'] in (1, 2, 3, 4) and bool((f['justificacion_ia'] or '').strip())
        for ev_item in f['evidencias']:
            ev_item['documento_id'] = evidencias_doc_map.get(ev_item['evidencia_id'])
        f['sin_pendientes'] = not any(p['estado_respuesta'] == 'PENDIENTE' for p in f['preguntas'])
        f['cupo_ia'] = max(0, MAX_PENDIENTES - sum(p['estado_respuesta'] == 'PENDIENTE' for p in f['preguntas']))
        for p in f['preguntas']:
            p['version'] = p['fecha_respuesta'].isoformat() if p['fecha_respuesta'] else ''
            p['borrador'] = respuesta_enviada if error and p['pregunta_id'] == pid else p['respuesta']
    habilitados_hu10 = sum(1 for f in filas if f['estado_hu10'] == 'PROPUESTA_HABILITADA')
    propuestas_hu10_listas = sum(1 for f in filas if f['tiene_propuesta_hu10'])
    modelo_hu10 = getattr(settings, 'HU10_OLLAMA_MODEL', '') or settings.HU09_OLLAMA_MODEL
    return render(request, 'presentation/decisor/preguntas.html', {
        'evaluaciones': evaluaciones, 'evaluacion': evaluacion, 'filas': filas,
        'lote': lote_actual,
        'no_informativas': sum(p['estado_respuesta'] == 'NO_INFORMATIVA' for f in filas for p in f['preguntas']),
        'total': total, 'respondidas': respondidas, 'pendientes': total - respondidas,
        'desconocidas': desconocidas, 'descartadas': sum(len(f['preguntas_descartadas']) for f in filas),
        'habilitados_hu10': habilitados_hu10,
        'propuestas_hu10_listas': propuestas_hu10_listas,
        'modelo_ia': settings.HU09_OLLAMA_MODEL,
        'modelo_hu10': modelo_hu10,
        'modelo_embeddings': settings.HU09_EMBEDDING_MODEL, 'error': error,
        'editable': evaluacion.estado == 'EN_PROCESO' and evaluacion.fecha_fin is None,
    }, status=400 if error else 200)