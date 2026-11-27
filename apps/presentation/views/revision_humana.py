"""Pantalla HU11 dentro de la ruta de trabajo del decisor."""
import json
import re
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from urllib.parse import urlencode

from apps.application.services.ai import AIService
from apps.application.services.preguntas import PreguntasService
from apps.application.services.preparacion_hu10 import PreparacionHU10Service
from apps.application.services.suficiencia import SuficienciaService
from apps.external_services.ai_errors import AnalisisNoDisponible
from apps.external_services.proveedor_ia import configurado, modelo_activo, obtener_proveedor
from apps.application.services.revision_humana import RevisionHumanaService, ESTADOS_VALIDOS, _modo_valido, _lote_activo, _version
from apps.data.models import BorradorRevisionHumana, Evaluacion, Evidencia, FragmentoDocumento, ReaperturaRevisionHumana, RevisionHumana, ValoracionSubfactor
from django.db import transaction
from django.db.models import OuterRef, Subquery

ESCALA = ((1, 'No cumple'), (2, 'Desconozco / No sé'), (3, 'Cumple parcialmente'), (4, 'Cumple'))

_STOP = {'para', 'como', 'esta', 'este', 'estos', 'estas', 'entre', 'sobre', 'desde', 'hasta', 'cuando', 'donde',
         'tiene', 'tienen', 'puede', 'pueden', 'cada', 'otros', 'otras', 'bien', 'sino', 'pero', 'aunque', 'según'}
_CTX = 170


def _raices(texto):
    """Raíces (6 letras) de las palabras significativas del subfactor."""
    vistas = []
    for palabra in re.findall(r'[a-záéíóúñü]{5,}', (texto or '').lower()):
        if palabra not in _STOP and palabra[:6] not in vistas:
            vistas.append(palabra[:6])
    return vistas


def _cola(texto, n=_CTX):
    texto = ' '.join((texto or '').split())
    if len(texto) <= n:
        return texto
    corte = texto[-n:]
    return '… ' + corte[corte.find(' ') + 1:] if ' ' in corte else '… ' + corte


def _cabeza(texto, n=_CTX):
    texto = ' '.join((texto or '').split())
    if len(texto) <= n:
        return texto
    corte = texto[:n]
    return (corte[:corte.rfind(' ')] if ' ' in corte else corte) + ' …'


def _pasaje(contenido, subfactor, antes, despues):
    """Solo presentación: la frase del pasaje que más se parece al subfactor va resaltada; el resto, en gris."""
    texto = ' '.join((contenido or '').split())
    raices = _raices(subfactor)
    frases = re.split(r'(?<=[a-záéíóúñü][.!?])\s+(?=[A-ZÁÉÍÓÚÑ0-9¿¡])', texto) if texto else []
    puntajes = [sum(r in fr.lower() for r in raices) for fr in frases]
    ctx_a = (_cola(antes) + ' ') if antes else ''
    ctx_d = (' ' + _cabeza(despues)) if despues else ''
    if not frases or not max(puntajes) or len(frases) == 1 and not raices:
        return {'ctx_antes': ctx_a, 'pre': '', 'hit': '', 'todo': texto, 'post': '', 'ctx_despues': ctx_d}
    m = max(range(len(frases)), key=lambda i: (puntajes[i], -i))
    return {'ctx_antes': ctx_a, 'pre': ' '.join(frases[:m]) + (' ' if m else ''), 'hit': frases[m], 'todo': '',
            'post': (' ' if m + 1 < len(frases) else '') + ' '.join(frases[m + 1:]), 'ctx_despues': ctx_d}


def _id(raw):
    try:
        numero = int(raw)
        return numero if 0 < numero <= 9223372036854775807 else None
    except (TypeError, ValueError):
        return None


PREGUNTA_FORMAL = '¿Existe documentación o un acuerdo formal que respalde este subfactor?'


def _destino(base, eid, **extra):
    return base + '?' + urlencode({'etapa': 'validacion', 'evaluacion': eid, **extra})


@transaction.atomic
def _preparar_faltantes(actor, eid):
    """Crea las preguntas de los subfactores pendientes que no tienen evidencia ni preguntas. Devuelve cuántos atendió."""
    evaluacion = PreguntasService._evaluacion(actor, eid, escritura=True)
    con_evidencia = set(Evidencia.objects.filter(fragmento__documento__evaluacion=evaluacion).values_list('valoracion_id', flat=True))
    atendidos = 0
    for v in PreguntasService._valoraciones(evaluacion).filter(estado_validacion='PENDIENTE', valor_confirmado__isnull=True):
        if v.pk in con_evidencia or v.preguntas_complementarias.exists():
            continue
        v = PreguntasService._valoracion_editable(evaluacion, v.pk)
        descripcion = v.subfactor.descripcion.strip()[:860]
        for texto in (PREGUNTA_FORMAL, f'¿Qué información verificable puede aportar sobre este subfactor: {descripcion}?'):
            PreguntasService._registrar(v, texto, 'SIN_EVIDENCIA')
        atendidos += 1
    return atendidos


def _guardar_respuestas(actor, eid, crudo):
    """Guarda en lote las respuestas del modal. Devuelve (guardadas, errores)."""
    try:
        items = json.loads(crudo or '[]')
    except ValueError:
        raise ValidationError('Respuestas inválidas.')
    if not isinstance(items, list) or len(items) > 500:
        raise ValidationError('Respuestas inválidas.')
    guardadas, errores = 0, []
    for item in items:
        if not isinstance(item, dict) or _id(item.get('id')) is None or not isinstance(item.get('respuesta'), str) or not item['respuesta'].strip():
            continue
        version = item.get('version')
        try:
            PreguntasService.responder(actor, eid, _id(item['id']), item['respuesta'], version if isinstance(version, str) else '')
            guardadas += 1
        except (ValidationError, PermissionDenied) as exc:
            errores.append(' '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
    return guardadas, errores


def _fuentes_rv(contexto, subfactor, con_documentos, referencias=None, razon=''):
    """Fuentes para el modal. Los pasajes solo se muestran cuando la IA ya propuso un valor; antes son candidatos sin evaluar."""
    fuentes = []
    if con_documentos:
        citadas = [e for e in contexto.get('evidencias', []) if f"E:{e['evidencia_id']}" in (referencias or [])]
        for e in (citadas or contexto.get('evidencias', [])):
            consulta = subfactor + ' ' + re.sub(r'E:\d+', ' ', razon or '')
            p = _pasaje(e['contenido'], consulta, None, None)
            fuentes.append({'b': p['pre'], 'm': p['hit'] or p['todo'], 'a': p['post'],
                            's': e['documento'] + (f" · pág. {e['pagina']}" if e.get('pagina') else '')})
    for q in contexto.get('preguntas', []):
        if q['estado_respuesta'] == 'APORTADA':
            fuentes.append({'b': '', 'm': q['respuesta'], 'a': '', 's': 'Declaración del decisor'})
    return fuentes


def _version_borrador_actual(v):
    """La decisión rápida no usa borradores; si quedó uno antiguo, su versión se informa para no chocar con él."""
    b = BorradorRevisionHumana.objects.filter(valoracion=v).first()
    return str(b.version if b else 0)


def _analizar_ia(actor, eid, vid):
    """Encadena los servicios existentes: suficiencia (HU09) y propuesta preliminar (HU10) de un subfactor."""
    if not configurado():
        raise ValidationError('El análisis con IA no está disponible. Puede valorar manualmente.')
    modelo = modelo_activo()

    def fila():
        return next((f for f in PreparacionHU10Service.obtener(actor, eid)['subfactores'] if f['valoracion_id'] == vid), None)

    f = fila()
    if f is None:
        raise ValidationError('Subfactor no disponible.')
    nuevas = 0
    try:
        if f['estado'] == 'ANALISIS_PENDIENTE':
            _, nuevas = SuficienciaService.analizar(actor, eid, vid, obtener_proveedor('suficiencia'), modelo, generar_preguntas=False)
            f = fila()
        valor = ValoracionSubfactor.objects.filter(pk=vid).values_list('valor_ia', flat=True).first()
        if f and f['estado'] == 'PROPUESTA_HABILITADA' and valor is None:
            AIService.generar_propuesta_preliminar(actor, eid, vid, obtener_proveedor('valoracion'))
            valor = ValoracionSubfactor.objects.filter(pk=vid).values_list('valor_ia', flat=True).first()
            f = fila()
    except AnalisisNoDisponible as exc:
        raise ValidationError(str(exc))
    actual = RevisionHumanaService.obtener(actor, eid, vid)
    propuesta = valor in (1, 2, 3, 4) and bool((actual['justificacion_ia'] or '').strip())
    return {'estado': f['estado'] if f else '', 'valor_ia': valor, 'preguntas': nuevas,
            'jia': actual['justificacion_ia'] or '', 'version': actual['version'],
            'fuentes': _fuentes_rv(actual, actual['subfactor'], propuesta, (f.get('suficiencia') or {}).get('referencias') if f else None, actual['justificacion_ia'])}


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
    if request.method == 'POST' and accion == 'aceptar_propuestas_hu11':
        try:
            items = params.getlist('seleccion')
            if not items or len(items) > 61:
                raise ValidationError('Seleccione entre 1 y 61 subfactores.')
            pares = []
            for item in items:
                partes = item.split(':')
                if len(partes) != 2 or _id(partes[0]) is None or len(partes[1]) != 64:
                    raise ValidationError('Selección inválida.')
                pares.append((_id(partes[0]), partes[1]))
            if len({p[0] for p in pares}) != len(pares):
                raise ValidationError('Selección repetida.')
            propias = {v.pk: v for v in PreguntasService._valoraciones(ev).filter(pk__in=[p[0] for p in pares])}
            versiones = {}
            with transaction.atomic():
                for vid_, version in pares:
                    v = propias.get(vid_)
                    if v is None:
                        raise PermissionDenied('Subfactor no disponible.')
                    if v.valor_ia not in (1, 2, 3, 4) or not (v.justificacion_ia or '').strip():
                        raise ValidationError('Un subfactor seleccionado no tiene propuesta de IA válida. No se registró ninguna decisión.')
                    texto = ('Propuesta de la IA aceptada tras revisar la evidencia. ' + v.justificacion_ia.strip())[:4000]
                    RevisionHumanaService.resolver(request.user, eid, vid_, 'CONFIRMAR', v.valor_ia, texto, version, _version_borrador_actual(v))
                    versiones[vid_] = RevisionHumanaService.obtener(request.user, eid, vid_)['version']
        except (ValidationError, PermissionDenied) as exc:
            return JsonResponse({'error': ' '.join(exc.messages) if isinstance(exc, ValidationError) else (str(exc) or 'Subfactor no disponible.') + ' Recargue la página.'}, status=400)
        respuesta = JsonResponse({'aceptadas': len(versiones), 'versiones': versiones})
        respuesta['Cache-Control'] = 'no-store'
        return respuesta
    if request.method == 'POST' and accion == 'preparar_faltantes_hu11':
        try:
            atendidos = _preparar_faltantes(request.user, eid)
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, ' '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
            return redirect(_destino(base, eid))
        if not atendidos:
            messages.info(request, 'No hay subfactores nuevos que necesiten preguntas.')
        return redirect(_destino(base, eid, completar=1, **({'valoracion': params.get('valoracion')} if _id(params.get('valoracion')) else {})))
    if request.method == 'POST' and accion == 'responder_faltantes_hu11':
        extra = {'valoracion': params.get('valoracion')} if _id(params.get('valoracion')) else {}
        try:
            guardadas, errores = _guardar_respuestas(request.user, eid, params.get('respuestas'))
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
            return redirect(_destino(base, eid, completar=1, **extra))
        if guardadas:
            messages.success(request, f'Respuestas guardadas: {guardadas}. Quedan como declaraciones suyas, no como evidencia documental.')
        elif not errores:
            messages.info(request, 'No había respuestas nuevas para guardar.')
        for e in errores[:3]:
            messages.error(request, e)
        return redirect(_destino(base, eid, **({'completar': 1} if errores else {}), **extra))
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
    if request.method == 'POST' and accion == 'analizar_ia_hu11':
        try:
            r = _analizar_ia(request.user, eid, vid)
        except ValidationError as exc:
            return JsonResponse({'error': ' '.join(exc.messages)}, status=400)
        respuesta = JsonResponse(r)
        respuesta['Cache-Control'] = 'no-store'
        return respuesta
    if request.method == 'POST' and accion == 'confirmar_rapida_hu11':
        v = next(v for v in valoraciones if v.pk == vid)
        raw_valor = params.get('valor', '')
        if raw_valor not in ('1', '2', '3', '4'):
            return JsonResponse({'error': 'Seleccione una valoración entre 1 y 4.'}, status=400)
        valor = int(raw_valor)
        propuesta = v.valor_ia in (1, 2, 3, 4) and bool((v.justificacion_ia or '').strip())
        modo = 'MANUAL' if not propuesta else ('CONFIRMAR' if valor == v.valor_ia else 'MODIFICAR')
        etiquetas = dict(ESCALA)
        texto = (params.get('justificacion') or '').strip()
        if not texto:
            if modo == 'MANUAL':
                texto = f'Valoración manual del decisor: {etiquetas[valor]} (sin propuesta de IA).'
            elif modo == 'CONFIRMAR':
                texto = f'Propuesta de la IA confirmada por el decisor: {etiquetas[valor]}.'
            else:
                texto = f'Valoración modificada por el decisor: {etiquetas[valor]} (la IA propuso {etiquetas[v.valor_ia]}).'
        try:
            RevisionHumanaService.resolver(request.user, eid, vid, modo, valor, texto,
                                           params.get('version'), _version_borrador_actual(v))
            version = RevisionHumanaService.obtener(request.user, eid, vid)['version']
        except (ValidationError, PermissionDenied) as exc:
            return JsonResponse({'error': ' '.join(exc.messages) if isinstance(exc, ValidationError) else (str(exc) or 'Subfactor no disponible.') + ' Recargue la página.'}, status=400)
        respuesta = JsonResponse({'version': version, 'modo': modo, 'justificacion': texto})
        respuesta['Cache-Control'] = 'no-store'
        return respuesta
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
    contextos = {f['valoracion_id']: f for f in PreguntasService.contexto(request.user, eid)}
    for v in valoraciones:
        b = guardados.get(v.pk)
        v.tiene_borrador = bool(b)
        c = contextos.get(v.pk) or {}
        v.n_evidencia = len(c.get('evidencias', []))
        v.con_declaracion = any(p['estado_respuesta'] == 'APORTADA' for p in c.get('preguntas', []))
        v.ev_estado = 'si' if v.n_evidencia else 'dc' if v.con_declaracion else 'no'
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
        # Solo presentación: nivel de relevancia con que el sistema asoció cada pasaje (no altera la versión de las fuentes).
        relevancias = dict(Evidencia.objects.filter(
            pk__in=[f['evidencia_id'] for f in seleccion['fuentes'] if f.get('origen') == 'DOCUMENTO']).values_list('pk', 'relevancia'))
        docs = dict(FragmentoDocumento.objects.filter(
            pk__in=[f['fragmento_id'] for f in seleccion['fuentes'] if f.get('origen') == 'DOCUMENTO']).values_list('pk', 'documento_id'))
        base_carga = reverse('presentation:decisor-carga-documental')
        for f in seleccion['fuentes']:
            r = relevancias.get(f.get('evidencia_id'))
            f['nivel'] = None if r is None else ('alta' if r >= Decimal('0.40') else 'media' if r >= Decimal('0.20') else 'baja')
            if f.get('origen') == 'DOCUMENTO' and f.get('fragmento_id') in docs:
                doc_id, frag_id = docs[f['fragmento_id']], f['fragmento_id']
                vecinos = FragmentoDocumento.objects.filter(documento_id=doc_id)
                antes = vecinos.filter(pk__lt=frag_id).order_by('-pk').values_list('contenido', flat=True).first()
                despues = vecinos.filter(pk__gt=frag_id).order_by('pk').values_list('contenido', flat=True).first()
                f['antes'], f['despues'] = antes, despues
                f['pasaje'] = _pasaje(f.get('contenido'), seleccion['subfactor'], antes, despues)
                f['url_documento'] = f'{base_carga}?{urlencode({"evaluacion_id": eid, "doc_id": doc_id, "panel": 1})}'
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
    # Solo presentación: posición y subfactor anterior/siguiente para la barra de navegación.
    ids = [v.pk for v in valoraciones]
    if seleccion and vid in ids:
        i = ids.index(vid)
        ctx.update(posicion=i + 1, anterior_pk=ids[i - 1] if i else None, siguiente_pk=ids[i + 1] if i + 1 < len(ids) else None)
    if seleccion:
        seleccion['hay_documentos'] = any(f.get('origen') == 'DOCUMENTO' for f in seleccion['fuentes'])
    # Solo presentación: cobertura de evidencia y datos del modal «Completar información faltante».
    faltantes = []
    for v in valoraciones:
        c = contextos.get(v.pk) or {}
        if v.n_evidencia or not c.get('editable') or not c.get('preguntas'):
            continue
        faltantes.append({'vid': v.pk, 'factor': v.evaluacion_factor.factor.nombre, 'subfactor': v.subfactor.descripcion,
            'preguntas': [{'id': p['pregunta_id'], 'texto': p['texto'], 'respuesta': p['respuesta'],
                           'version': p['fecha_respuesta'].isoformat() if p['fecha_respuesta'] else ''} for p in c['preguntas']]})
    con_ev = sum(1 for v in valoraciones if v.n_evidencia)
    sin_ev = [v for v in valoraciones if not v.n_evidencia]
    ctx.update(faltantes=faltantes, n_con_evidencia=con_ev, n_sin_evidencia=len(sin_ev),
               n_sin_evidencia_resp=sum(1 for v in sin_ev if v.con_declaracion),
               n_sin_evidencia_pend=sum(1 for v in sin_ev if not v.con_declaracion),
               completar=params.get('completar') == '1' and request.method == 'GET',
               puede_completar=ev.estado == 'EN_PROCESO' and ev.fecha_fin is None and any(
                   not v.n_evidencia and v.estado_validacion == 'PENDIENTE' and v.valor_confirmado is None for v in valoraciones))
    # Solo presentación: subfactores que la pantalla «Análisis de IA» puede procesar (con evidencia primero).
    abierto = ev.estado == 'EN_PROCESO' and ev.fecha_fin is None
    filas_ia = {f['valoracion_id']: f for f in PreparacionHU10Service.obtener(request.user, eid)['subfactores']}
    estados_ia = {k: f['estado'] for k, f in filas_ia.items()}
    objetivos = [v for v in valoraciones if abierto and v.estado_validacion == 'PENDIENTE' and v.valor_confirmado is None and v.valor_ia is None
                 and v.n_evidencia and estados_ia.get(v.pk) in ('ANALISIS_PENDIENTE', 'PROPUESTA_HABILITADA')]
    ctx.update(ia_disponible=configurado(), ia_pendientes=len(objetivos), ia_remota=configurado(),
               ia_objetivos=[{'vid': v.pk, 'nombre': v.subfactor.descripcion[:140]} for v in objetivos])
    # Solo presentación: datos de la revisión rápida (un registro por subfactor; la evidencia se abre en un modal).
    rv_datos = []
    for v in valoraciones:
        c = contextos.get(v.pk) or {}
        propuesta = v.valor_ia in (1, 2, 3, 4) and bool((v.justificacion_ia or '').strip())
        hecho = v.estado_validacion in ESTADOS_VALIDOS and v.valor_confirmado in (1, 2, 3, 4)
        fuentes = _fuentes_rv(c, v.subfactor.descripcion, propuesta, ((filas_ia.get(v.pk) or {}).get('suficiencia') or {}).get('referencias'), v.justificacion_ia)
        rv_datos.append({
            'id': v.pk, 'dim': v.evaluacion_factor.factor.dimension.nombre, 'fac': v.evaluacion_factor.factor.nombre,
            'text': v.subfactor.descripcion, 'ia': v.valor_ia if propuesta else None, 'jia': v.justificacion_ia or '',
            'est': estados_ia.get(v.pk, ''),
            'val': v.valor_confirmado if hecho else None, 'ok': hecho, 'nev': v.n_evidencia, 'fuentes': fuentes,
            'version': _version(v, c, v.ultima_reapertura_id) if c else '',
            'just': (v.justificacion_decisor or '') if hecho else '',
            'fecha': v.fecha_validacion.strftime('%d/%m/%Y %H:%M') if hecho and v.fecha_validacion else '',
        })
    ctx.update(rv_datos=rv_datos, rv_editable=abierto and not _lote_activo(ev))
    # Solo presentación: árbol dimensión -> factor para la lista lateral y subfactores del factor activo.
    arbol, por_factor = [], {}
    for v in valoraciones:
        ef = v.evaluacion_factor
        dim = ef.factor.dimension.nombre
        if not arbol or arbol[-1]['nombre'] != dim:
            arbol.append({'nombre': dim, 'factores': []})
        fs = arbol[-1]['factores']
        if not fs or fs[-1]['id'] != ef.pk:
            fs.append({'id': ef.pk, 'nombre': ef.factor.nombre, 'ir': ef.importancia_relativa, 'items': [], 'ok': 0, 'primero': v.pk, 'actual': False})
        f = fs[-1]
        hecho = v.estado_validacion in ESTADOS_VALIDOS and v.valor_confirmado in (1, 2, 3, 4)
        f['items'].append({'pk': v.pk, 'n': len(f['items']) + 1, 'titulo': v.subfactor.descripcion, 'estado': v.etiqueta_hu11,
                           'hecho': hecho, 'actual': v.pk == vid})
        f['ok'] += 1 if hecho else 0
        if v.pk == vid:
            f['actual'] = True
    for d in arbol:
        d['ok'] = d['total'] = 0
        d['actual'] = False
        for f in d['factores']:
            f['total'] = len(f['items'])
            d['ok'] += f['ok']
            d['total'] += f['total']
            if f['actual']:
                d['actual'] = True
                ctx['hermanos'] = f
    ctx['arbol'] = arbol
    # Una decisión pudo haber quedado obsoleta: nunca se sustituye su versión silenciosamente.
    if error and seleccion:
        seleccion['version'] = params.get('version', '')
    return render(request, template, ctx, status=400 if error else 200)
