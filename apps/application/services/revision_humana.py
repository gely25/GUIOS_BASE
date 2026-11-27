"""HU11: decisiones humanas atómicas y contrato de puntuaciones revisadas."""
import json
from hashlib import sha256

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder

from apps.data.models import (BorradorRevisionHumana, Evaluacion, EvaluacionFactor, LoteHU09,
    ReaperturaRevisionHumana, ResultadoEvaluacion, RevisionHumana, Subfactor, ValoracionSubfactor)
from apps.business_rules.pm import calcular_pm
from apps.business_rules.foda import clasificar_foda
from .preguntas import PreguntasService


ESTADOS_VALIDOS = ('CONFIRMADA', 'MODIFICADA')
_NO_CONSULTADO = object()


def _valor_valido(valor):
    return type(valor) is int and 1 <= valor <= 4


def _fuentes(fila):
    fuentes = [dict(e, id=f"E:{e['evidencia_id']}", origen='DOCUMENTO') for e in fila['evidencias']]
    fuentes += [dict(id=f"R:{p['pregunta_id']}", origen='DECLARACION_DECISOR',
        pregunta=p['texto'], contenido=p['respuesta'], actor=p['respondido_por'],
        fecha=p['fecha_respuesta'].isoformat() if p['fecha_respuesta'] else None)
        for p in fila['preguntas'] if p['estado_respuesta'] == 'APORTADA']
    return fuentes


def _version(v, fila, reapertura=_NO_CONSULTADO):
    datos = {'contexto': fila, 'valor_ia': v.valor_ia, 'justificacion_ia': v.justificacion_ia,
             'estado_validacion': v.estado_validacion, 'valor_confirmado': v.valor_confirmado,
             'justificacion_decisor': v.justificacion_decisor}
    if reapertura is _NO_CONSULTADO:
        reapertura = ReaperturaRevisionHumana.objects.filter(valoracion=v).order_by('-pk').values_list('pk', flat=True).first()
    if reapertura is not None:
        datos['ultima_reapertura'] = reapertura
    return sha256(json.dumps(datos, cls=DjangoJSONEncoder, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _modo_valido(v, modo, valor):
    propuesta = _valor_valido(v.valor_ia) and bool((v.justificacion_ia or '').strip())
    return _valor_valido(valor) and ((modo == 'CONFIRMAR' and propuesta and valor == v.valor_ia)
        or (modo == 'MODIFICAR' and propuesta and valor != v.valor_ia)
        or (modo == 'MANUAL' and not propuesta))


def _version_borrador(v, version):
    b = BorradorRevisionHumana.objects.filter(valoracion=v).first()
    if version != str(b.version if b else 0):
        raise ValidationError('El borrador cambió en otra pestaña. Vuelva a consultar.')
    return b


def _lote_activo(ev):
    return LoteHU09.objects.filter(evaluacion=ev, estado__in=('EN_COLA', 'EN_PROCESO')).exists()


class RevisionHumanaService:
    @classmethod
    def obtener(cls, actor, evaluacion_id, valoracion_id):
        ev = PreguntasService._evaluacion(actor, evaluacion_id)
        v = PreguntasService._valoraciones(ev).filter(pk=valoracion_id).first()
        if v is None:
            raise PermissionDenied('Subfactor no disponible.')
        fila = PreguntasService.contexto(actor, evaluacion_id, valoracion_id=v.pk)[0]
        return dict(fila, valor_ia=v.valor_ia, justificacion_ia=v.justificacion_ia,
            valor_confirmado=v.valor_confirmado, justificacion_decisor=v.justificacion_decisor,
            estado_validacion=v.estado_validacion, fecha_validacion=v.fecha_validacion,
            validado_por=v.validado_por_id, fuentes=_fuentes(fila), version=_version(v, fila),
            editable=fila['editable'] and ev.estado == 'EN_PROCESO' and ev.fecha_fin is None and not _lote_activo(ev),
            reabrible=v.estado_validacion in ESTADOS_VALIDOS and _valor_valido(v.valor_confirmado)
                and ev.estado == 'EN_PROCESO' and ev.fecha_fin is None and not _lote_activo(ev))

    @classmethod
    @transaction.atomic
    def resolver(cls, actor, evaluacion_id, valoracion_id, modo, valor, justificacion, version, version_borrador=None):
        # Mismo orden de bloqueo que HU09: evaluación, luego valoración.
        ev = PreguntasService._evaluacion(actor, evaluacion_id, escritura=True)
        if _lote_activo(ev):
            raise ValidationError('Espere a que termine el análisis de suficiencia.')
        v = PreguntasService._valoracion_editable(ev, valoracion_id)
        fila = PreguntasService.contexto(actor, ev.pk, valoracion_id=v.pk)[0]
        if not isinstance(version, str) or version != _version(v, fila):
            raise ValidationError('La información cambió. Consulte nuevamente antes de decidir.')
        if version_borrador is not None or BorradorRevisionHumana.objects.filter(valoracion=v).exists():
            _version_borrador(v, version_borrador)
        if not isinstance(justificacion, str) or not justificacion.strip() or len(justificacion.strip()) > 4000:
            raise ValidationError('Registre una justificación de entre 1 y 4000 caracteres.')
        if not _valor_valido(valor):
            raise ValidationError('Seleccione una valoración entera entre 1 y 4.')
        propuesta = _valor_valido(v.valor_ia) and bool((v.justificacion_ia or '').strip())
        if modo == 'CONFIRMAR' and propuesta and valor == v.valor_ia:
            estado = 'CONFIRMADA'
        elif modo == 'MODIFICAR' and propuesta and valor != v.valor_ia:
            estado = 'MODIFICADA'
        elif modo == 'MANUAL' and not propuesta:
            estado = 'CONFIRMADA'
        else:
            raise ValidationError('La acción no corresponde a la propuesta disponible.')
        # La decisión explícita del decisor puede reconocer desconocimiento (2).
        # No se deduce ninguna puntuación de las respuestas de HU09.
        fecha = timezone.now()
        registro = RevisionHumana.objects.create(valoracion=v, actor=actor, modo=modo,
            valor_ia=v.valor_ia, justificacion_ia=v.justificacion_ia or '', valor=valor,
            justificacion=justificacion.strip(), huella_contexto=version, fuentes=_fuentes(fila), fecha=fecha)
        v.valor_confirmado = valor
        v.justificacion_decisor = registro.justificacion
        v.estado_validacion = estado
        v.fecha_validacion = fecha
        v.validado_por = actor
        v.save(update_fields=['valor_confirmado', 'justificacion_decisor', 'estado_validacion',
                              'fecha_validacion', 'validado_por'])
        BorradorRevisionHumana.objects.filter(valoracion=v).delete()
        return registro

    @classmethod
    @transaction.atomic
    def guardar_borrador(cls, actor, evaluacion_id, valoracion_id, modo, valor, justificacion, version, version_borrador):
        ev = PreguntasService._evaluacion(actor, evaluacion_id, escritura=True)
        if _lote_activo(ev):
            raise ValidationError('Espere a que termine el análisis de suficiencia.')
        v = PreguntasService._valoracion_editable(ev, valoracion_id)
        fila = PreguntasService.contexto(actor, ev.pk, valoracion_id=v.pk)[0]
        if version != _version(v, fila):
            raise ValidationError('La información cambió. Consulte nuevamente las fuentes.')
        b = _version_borrador(v, version_borrador)
        if modo not in ('', 'CONFIRMAR', 'MODIFICAR', 'MANUAL') or (valor is not None and not _valor_valido(valor)):
            raise ValidationError('Borrador inválido.')
        if not isinstance(justificacion, str) or len(justificacion) > 4000:
            raise ValidationError('La justificación no puede superar los 4000 caracteres.')
        datos = dict(modo=modo, valor=valor, justificacion=justificacion, huella_contexto=version)
        if b and all(getattr(b, k) == val for k, val in datos.items()):
            return b
        if b is None:
            return BorradorRevisionHumana.objects.create(valoracion=v, actor=actor, **datos)
        for k, val in datos.items():
            setattr(b, k, val)
        b.version += 1
        b.save()
        return b

    @classmethod
    @transaction.atomic
    def resolver_lote(cls, actor, evaluacion_id, seleccion):
        """Confirma únicamente borradores explícitamente seleccionados; todo o nada."""
        ev = PreguntasService._evaluacion(actor, evaluacion_id, escritura=True)
        if _lote_activo(ev):
            raise ValidationError('Espere a que termine el análisis de suficiencia.')
        if not seleccion or len(seleccion) > 61 or len({s[0] for s in seleccion}) != len(seleccion):
            raise ValidationError('Seleccione entre 1 y 61 borradores distintos.')
        registros = []
        for vid, revision, huella in sorted(seleccion):
            v = PreguntasService._valoracion_editable(ev, vid)
            b = _version_borrador(v, revision)
            if not b or b.huella_contexto != huella or not _modo_valido(v, b.modo, b.valor) or not b.justificacion.strip():
                raise ValidationError('Un borrador está incompleto o cambió. No se registró ninguna decisión.')
            registros.append(cls.resolver(actor, ev.pk, vid, b.modo, b.valor, b.justificacion, huella, revision))
        return registros

    @classmethod
    @transaction.atomic
    def reabrir(cls, actor, evaluacion_id, valoracion_id, motivo, version):
        """Reapertura explícita: no elimina decisiones históricas ni la propuesta IA."""
        ev = PreguntasService._evaluacion(actor, evaluacion_id)
        ev = Evaluacion.objects.select_for_update().filter(
            pk=ev.pk, usuario_id=actor.pk).first()
        if ev is None:
            raise PermissionDenied('Evaluación no disponible.')
        if ev.estado not in (Evaluacion.EN_PROCESO, Evaluacion.CERRADA):
            raise ValidationError('La evaluación no admite cambios.')
        if ev.estado == Evaluacion.EN_PROCESO and ev.fecha_fin is not None:
            raise ValidationError('La evaluación no admite cambios.')
        if _lote_activo(ev):
            raise ValidationError('Espere a que termine el análisis de suficiencia.')
        if not PreguntasService._valoraciones(ev).filter(pk=valoracion_id).exists():
            raise PermissionDenied('Subfactor no disponible.')
        v = ValoracionSubfactor.objects.select_for_update().get(pk=valoracion_id)
        if v.estado_validacion not in ESTADOS_VALIDOS or not _valor_valido(v.valor_confirmado):
            raise ValidationError('Solo puede reabrir una decisión humana registrada.')
        fila = PreguntasService.contexto(actor, ev.pk, valoracion_id=v.pk)[0]
        if version != _version(v, fila):
            raise ValidationError('La información cambió. Consulte nuevamente antes de reabrir.')
        if not isinstance(motivo, str) or not motivo.strip() or len(motivo.strip()) > 4000:
            raise ValidationError('Registre un motivo de reapertura de entre 1 y 4000 caracteres.')
        previa = RevisionHumana.objects.filter(valoracion=v).order_by('-fecha', '-pk').first()
        factores = EvaluacionFactor.objects.filter(evaluacion=ev)
        resultado = ResultadoEvaluacion.objects.filter(evaluacion=ev).first()
        anteriores = {'factores': list(factores.values('pk', 'ponderacion_media', 'clasificacion_foda')),
            'resultado': dict(id=resultado.pk, recomendacion=resultado.recomendacion,
                explicacion=resultado.explicacion, version_regla=resultado.version_regla,
                conteos_foda=resultado.conteos_foda, factores_criticos=resultado.factores_criticos,
                fecha_generacion=resultado.fecha_generacion) if resultado else None}
        decision = dict(revision_id=previa.pk if previa else None, valor=v.valor_confirmado,
            estado=v.estado_validacion, justificacion=v.justificacion_decisor,
            fecha=v.fecha_validacion, actor_id=v.validado_por_id, valor_ia=v.valor_ia,
            justificacion_ia=v.justificacion_ia)
        evento = ReaperturaRevisionHumana.objects.create(valoracion=v, actor=actor, motivo=motivo.strip(),
            decision_anterior=json.loads(json.dumps(decision, cls=DjangoJSONEncoder)),
            resultados_anteriores=json.loads(json.dumps(anteriores, cls=DjangoJSONEncoder)))
        # Retirar todo resultado derivado obsoleto, después de conservar una copia histórica.
        factores.update(ponderacion_media=None, clasificacion_foda=None)
        if resultado:
            resultado.delete()
        v.valor_confirmado = None
        v.estado_validacion = 'PENDIENTE'
        v.justificacion_decisor = None
        v.fecha_validacion = None
        v.validado_por = None
        v.save(update_fields=['valor_confirmado', 'estado_validacion', 'justificacion_decisor',
                              'fecha_validacion', 'validado_por'])
        BorradorRevisionHumana.objects.filter(valoracion=v).delete()
        if ev.estado == Evaluacion.CERRADA:
            ev.estado = Evaluacion.EN_PROCESO
            ev.fecha_fin = None
            ev.save(update_fields=['estado', 'fecha_fin', 'fecha_actualizacion'])
        return evento

    @classmethod
    @transaction.atomic
    def para_calculo(cls, actor, evaluacion_id):
        """Entrega valores solo cuando todos los factores relevantes están completos.

        El consumidor que persista resultados debe llamar dentro de su transacción
        y mantener el bloqueo de evaluación hasta guardar. No calcula ni persiste PM/FODA.
        """
        ev = PreguntasService._evaluacion(actor, evaluacion_id)
        ev = type(ev).objects.select_for_update().filter(pk=ev.pk, usuario_id=actor.pk).first()
        if ev is None:
            raise PermissionDenied('Evaluación no disponible.')
        factores = list(EvaluacionFactor.objects.filter(evaluacion=ev, relevante=True).select_related('factor').order_by('pk'))
        if any(f.importancia_relativa is None for f in factores):
            raise ValidationError('Existen factores sin importancia relativa definida.')
        relevantes = [f for f in factores if f.importancia_relativa in (2, 3, 4)]
        if not relevantes or _lote_activo(ev):
            raise ValidationError('No hay factores disponibles o existe un análisis en curso.')
        vs = list(ValoracionSubfactor.objects.filter(evaluacion_factor__in=relevantes).select_related('subfactor').order_by('pk'))
        esperados = {}
        for sf in Subfactor.objects.filter(factor_id__in=[f.factor_id for f in relevantes], activo=True):
            esperados.setdefault(sf.factor_id, set()).add(sf.pk)
        # Validar completitud antes de recuperar auditorías y fuentes.
        por_factor = {}
        for v in vs:
            por_factor.setdefault(v.evaluacion_factor_id, []).append(v)
        for f in relevantes:
            filas = por_factor.get(f.pk, [])
            if not filas or esperados.get(f.factor_id, set()) - {v.subfactor_id for v in filas}:
                raise ValidationError('Faltan subfactores de un factor relevante.')
            if any(v.subfactor.factor_id != f.factor_id or v.estado_validacion not in ESTADOS_VALIDOS
                   or not _valor_valido(v.valor_confirmado) or not v.fecha_validacion
                   or v.validado_por_id != ev.usuario_id or not (v.justificacion_decisor or '').strip()
                   for v in filas):
                raise ValidationError('Faltan valoraciones confirmadas de factores relevantes.')
        # Solo decisiones con auditoría vigente; no confiar en puntuaciones escritas directamente.
        ultimas = {}
        for r in RevisionHumana.objects.filter(valoracion_id__in=[v.pk for v in vs]).order_by('valoracion_id', '-fecha', '-pk'):
            ultimas.setdefault(r.valoracion_id, r)
        reaperturas = {}
        for evento in ReaperturaRevisionHumana.objects.filter(valoracion_id__in=[v.pk for v in vs]).order_by('valoracion_id', '-pk'):
            reaperturas.setdefault(evento.valoracion_id, evento)
        contextos = {f['valoracion_id']: f for f in PreguntasService.contexto(actor, ev.pk)}
        datos = []
        for f in relevantes:
            filas = por_factor[f.pk]
            for v in filas:
                r = ultimas.get(v.pk)
                evento = reaperturas.get(v.pk)
                if (not r or (evento and r.fecha <= evento.fecha)
                        or not _modo_valido(v, r.modo, r.valor)
                        or r.valor != v.valor_confirmado or r.actor_id != v.validado_por_id
                        or ('MODIFICADA' if r.modo == 'MODIFICAR' else 'CONFIRMADA') != v.estado_validacion
                        or r.valor_ia != v.valor_ia or r.justificacion_ia != (v.justificacion_ia or '')
                        or r.fecha != v.fecha_validacion or r.justificacion != v.justificacion_decisor
                        or v.pk not in contextos or r.fuentes != _fuentes(contextos[v.pk])):
                    raise ValidationError('Una decisión carece de auditoría vigente o sus fuentes cambiaron. Revise y reabra la valoración.')
            datos.append({'evaluacion_factor_id': f.pk, 'factor_id': f.factor_id,
                'factor': f.factor.nombre, 'alcance': f.factor.alcance, 'ir': f.importancia_relativa, 'valoraciones': [{'valoracion_id': v.pk,
                    'subfactor_id': v.subfactor_id, 'valor': v.valor_confirmado,
                    'justificacion': v.justificacion_decisor, 'revision_id': ultimas[v.pk].pk,
                    'fecha_validacion': v.fecha_validacion.isoformat()} for v in filas]})
        salida = {'version_contrato': 2, 'evaluacion_id': ev.pk, 'factores': datos}
        salida['huella'] = sha256(json.dumps(salida, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return salida

    @classmethod
    def vista_previa(cls, actor, evaluacion_id):
        """Consulta no persistente: HU12 conserva la responsabilidad del cálculo oficial."""
        try:
            datos = cls.para_calculo(actor, evaluacion_id)
        except ValidationError as exc:
            return {'lista_pm': False, 'lista_foda': False, 'motivo': ' '.join(exc.messages), 'factores': []}
        filas = []
        for f in datos['factores']:
            pm = calcular_pm(v['valor'] for v in f['valoraciones'])
            alcance = f['alcance']
            filas.append(dict(factor=f['factor'], ir=f['ir'], cantidad=len(f['valoraciones']),
                pm=f'{float(pm):.2f}', pm_exacta=str(pm), alcance=alcance,
                foda=clasificar_foda(pm, alcance) if alcance in ('interno', 'externo') else None))
        lista_foda = all(f['foda'] is not None for f in filas)
        return {'lista_pm': True, 'lista_foda': lista_foda, 'factores': filas, 'huella': datos['huella'],
            'motivo': '' if lista_foda else 'Falta definir el alcance interno o externo de algún factor.'}

    @classmethod
    @transaction.atomic
    def validar_calculo(cls, actor, evaluacion_id, huella):
        """HU12 debe mantener la transacción exterior hasta persistir sus resultados."""
        datos = cls.para_calculo(actor, evaluacion_id)
        if datos['huella'] != huella:
            raise ValidationError('Las valoraciones cambiaron desde el cálculo. Calcule nuevamente.')
        return datos
