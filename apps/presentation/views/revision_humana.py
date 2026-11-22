"""Pantalla HU11 dentro de la ruta de trabajo del decisor."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from urllib.parse import urlencode

from apps.application.services.preguntas import PreguntasService
from apps.application.services.revision_humana import RevisionHumanaService, ESTADOS_VALIDOS, _modo_valido, _lote_activo, _version
from apps.data.models import BorradorRevisionHumana, Evaluacion, ReaperturaRevisionHumana, RevisionHumana
from django.db.models import OuterRef, Subquery

ESCALA = ((1, 'No cumple'), (2, 'Desconozco / No sé'), (3, 'Cumple parcialmente'), (4, 'Cumple'))


def _id(raw):
    try:
        numero = int(raw)
        return numero if 0 < numero <= 9223372036854775807 else None
    except (TypeError, ValueError):
        return None


@never_cache
def revision_humana_view(request):
    if not request.user.is_authenticated or not request.user.activo or request.user.rol != 'DECISOR':
        raise PermissionDenied
    params = request.POST if request.method == 'POST' else request.GET
    base = reverse('presentation:decisor-revision-valoraciones')
    evaluaciones = Evaluacion.objects.filter(usuario=request.user).select_related('software').order_by('-fecha_inicio', '-pk')
    ctx = {'evaluaciones': evaluaciones, 'escala': ESCALA, 'base': base}
    template = 'presentation/decisor/revision_humana.html'
    raw = params.get('evaluacion')
    if raw in (None, '') and request.method == 'GET':
        return render(request, template, ctx)
    eid = _id(raw)
    if eid is None:
        return HttpResponseBadRequest('Evaluación inválida.')
    ev = PreguntasService._evaluacion(request.user, eid)
    accion = params.get('accion')
    if request.method == 'POST' and accion == 'resolver_lote_hu11':
        try:
            if params.get('confirmar_lote') != '1':
                raise ValidationError('Confirme expresamente las decisiones seleccionadas.')
            items = params.getlist('seleccion')
            if len(items) > 61:
                raise ValidationError('El lote admite hasta 61 decisiones.')
            seleccion_lote = []
            for item in items:
                partes = item.split(':')
                if len(partes) != 3 or _id(partes[0]) is None or _id(partes[1]) is None or len(partes[2]) != 64:
                    raise ValidationError('Selección inválida.')
                seleccion_lote.append((_id(partes[0]), partes[1], partes[2]))
            registros = RevisionHumanaService.resolver_lote(request.user, eid, seleccion_lote)
            messages.success(request, f'Decisiones humanas registradas: {len(registros)}.')
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
        return redirect(base + '?' + urlencode({'etapa': 'validacion', 'evaluacion': eid}))
    valoraciones = list(PreguntasService._valoraciones(ev).annotate(
        ultimo_modo=Subquery(RevisionHumana.objects.filter(valoracion_id=OuterRef('pk')).order_by('-fecha', '-pk').values('modo')[:1]),
        ultima_reapertura_id=Subquery(ReaperturaRevisionHumana.objects.filter(valoracion_id=OuterRef('pk')).order_by('-pk').values('pk')[:1])))
    vid = _id(params.get('valoracion')) if params.get('valoracion') is not None else None
    if (params.get('valoracion') is not None or request.method == 'POST') and vid is None:
        return HttpResponseBadRequest('Subfactor inválido.')
    if vid is None and valoraciones:
        vid = next((v.pk for v in valoraciones if v.estado_validacion not in ESTADOS_VALIDOS), valoraciones[0].pk)
    if vid is not None and not any(v.pk == vid for v in valoraciones):
        raise PermissionDenied('Subfactor no disponible.')
    if request.method == 'POST' and accion == 'guardar_borrador_hu11':
        raw_valor = params.get('valor', '')
        if raw_valor not in ('', '1', '2', '3', '4'):
            return JsonResponse({'error': 'Valor inválido.'}, status=400)
        try:
            b = RevisionHumanaService.guardar_borrador(request.user, eid, vid, params.get('modo', ''),
                int(raw_valor) if raw_valor else None, params.get('justificacion', ''),
                params.get('version'), params.get('version_borrador'))
        except ValidationError as exc:
            return JsonResponse({'error': ' '.join(exc.messages)}, status=400)
        respuesta = JsonResponse({'version_borrador': str(b.version), 'fecha': b.fecha.isoformat()})
        respuesta['Cache-Control'] = 'no-store'
        return respuesta
    if request.method == 'POST' and accion == 'reabrir_hu11':
        try:
            if params.get('confirmar_reapertura') != '1':
                raise ValidationError('Confirme expresamente la reapertura.')
            RevisionHumanaService.reabrir(request.user, eid, vid, params.get('motivo', ''), params.get('version'))
            messages.success(request, 'Valoración reabierta. La decisión anterior permanece en el historial; los resultados derivados deben recalcularse.')
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
        return redirect(base + '?' + urlencode({'etapa': 'validacion', 'evaluacion': eid, 'valoracion': vid}))
    error = None
    borrador = ''
    if request.method == 'POST':
        if params.get('accion') != 'resolver_hu11':
            return HttpResponseBadRequest('Acción inválida.')
        borrador = params.get('justificacion', '')[:4000]
        try:
            raw_valor = params.get('valor')
            if raw_valor not in ('1', '2', '3', '4'):
                raise ValidationError('Seleccione una valoración entre 1 y 4.')
            RevisionHumanaService.resolver(request.user, eid, vid, params.get('modo'), int(raw_valor), params.get('justificacion', ''), params.get('version'), params.get('version_borrador'))
            messages.success(request, 'Decisión humana registrada. La propuesta original se conserva.')
            return redirect(base + '?' + urlencode({'etapa': 'validacion', 'evaluacion': eid, 'valoracion': vid}))
        except ValidationError as exc:
            error = ' '.join(exc.messages)
    guardados = {b.valoracion_id: b for b in BorradorRevisionHumana.objects.filter(valoracion_id__in=[v.pk for v in valoraciones], actor=request.user)}
    disponibles = []
    obsoletos = []
    candidatos = [v for v in valoraciones if v.pk in guardados and v.estado_validacion == 'PENDIENTE'
                  and v.valor_confirmado is None]
    contextos = {f['valoracion_id']: f for f in PreguntasService.contexto(request.user, eid)} if candidatos else {}
    for v in valoraciones:
        b = guardados.get(v.pk)
        v.tiene_borrador = bool(b)
        v.etiqueta_hu11 = 'VALIDACIÓN MANUAL' if v.ultimo_modo == 'MANUAL' and v.estado_validacion in ESTADOS_VALIDOS else v.estado_validacion
        if b and v.pk in contextos and v.estado_validacion == 'PENDIENTE' and v.valor_confirmado is None:
            if b.huella_contexto != _version(v, contextos[v.pk], v.ultima_reapertura_id):
                obsoletos.append(v)
            elif _modo_valido(v, b.modo, b.valor) and b.justificacion.strip():
                disponibles.append({'v': v, 'b': b})
    seleccion = RevisionHumanaService.obtener(request.user, eid, vid) if vid is not None else None
    if seleccion:
        seleccion['propuesta'] = seleccion['valor_ia'] in (1, 2, 3, 4) and bool((seleccion['justificacion_ia'] or '').strip())
        seleccion['historial'] = RevisionHumana.objects.filter(valoracion_id=vid).select_related('actor')
        seleccion['reaperturas'] = ReaperturaRevisionHumana.objects.filter(valoracion_id=vid).select_related('actor')
        seleccion['ultima_reapertura'] = seleccion['reaperturas'].first()
        seleccion['tiene_pendientes'] = any(p['estado_respuesta'] == 'PENDIENTE' for p in seleccion['preguntas'])
    actual = guardados.get(vid)
    if seleccion:
        seleccion['etiqueta_hu11'] = next(v.etiqueta_hu11 for v in valoraciones if v.pk == vid)
        seleccion['version_borrador'] = params.get('version_borrador', '0') if error else str(actual.version if actual else 0)
        seleccion['borrador_obsoleto'] = bool(actual and actual.huella_contexto != seleccion['version'])
    if not error and actual:
        borrador = actual.justificacion
    revisadas = sum(v.estado_validacion in ESTADOS_VALIDOS and v.valor_confirmado in (1, 2, 3, 4) for v in valoraciones)
    ctx.update(evaluacion=ev, valoraciones=valoraciones, seleccion=seleccion, total=len(valoraciones), revisadas=revisadas,
               pendientes=len(valoraciones)-revisadas, error=error, borrador=borrador,
               valor_elegido=params.get('valor', '') if error else str(actual.valor or '') if actual else '',
               modo_elegido=params.get('modo', '') if error else actual.modo if actual else '',
               borradores=disponibles, borradores_obsoletos=obsoletos, cantidad_borradores=len(guardados), lote_editable=ev.estado == 'EN_PROCESO' and ev.fecha_fin is None and not _lote_activo(ev))
    # Una decisión pudo haber quedado obsoleta: nunca se sustituye su versión silenciosamente.
    if error and seleccion:
        seleccion['version'] = params.get('version', '')
    return render(request, template, ctx, status=400 if error else 200)
