"""HU09: detección básica, registro de vacíos y respuestas complementarias.

El análisis semántico es un consumidor/productor externo de este servicio.
La existencia de fragmentos no demuestra por sí sola suficiencia.
"""
from hashlib import sha256
import re
import unicodedata

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Prefetch
from django.utils import timezone

from apps.data.models import AnalisisSuficiencia, Evaluacion, Evidencia, PreguntaComplementaria, Usuario, ValoracionSubfactor


MAX_PENDIENTES = 3


def estado_respuesta(respuesta):
    """Clasifica declaraciones explícitas de desconocimiento, no negaciones técnicas."""
    if not respuesta or not respuesta.strip():
        return 'PENDIENTE'
    normal = ''.join(c for c in unicodedata.normalize('NFKD', respuesta.casefold())
                     if not unicodedata.combining(c))
    normal = ' '.join(normal.split()).strip(' .!?¿¡')
    normal = re.sub(r'\s+x\d+$', '', normal)
    if normal in {'no se', 'no lo se', 'no lose', 'desconozco', 'lo desconozco',
                  'no tengo informacion', 'no dispongo de informacion', 'no tengo datos'}:
        return 'DESCONOCE'
    # Solo patrones inequívocos de relleno; no se penaliza una respuesta técnica breve.
    if normal in {'sadasd', 'asdf', 'asdfgasdf', 'qwerty'} or not any(c.isalnum() for c in normal) or re.fullmatch(r'([a-z])\1{3,}', normal):
        return 'NO_INFORMATIVA'
    # Secuencias de tecleo repetitivo (fila ASDF), sin espacios ni dígitos.
    # No se aplica a acrónimos breves, códigos de versión ni oraciones.
    if len(normal) >= 9 and re.fullmatch(r'(?:asd|sad|ads|dsa|sda|das|asdf|fdsa)+', normal):
        return 'NO_INFORMATIVA'
    return 'APORTADA'


class PreguntasService:
    @staticmethod
    def _evaluacion(actor, evaluacion_id, escritura=False):
        if not getattr(actor, 'pk', None) or not Usuario.objects.filter(
            pk=actor.pk, activo=True, rol=Usuario.DECISOR
        ).exists():
            raise PermissionDenied('Se requiere un decisor activo.')
        consulta = Evaluacion.objects.filter(pk=evaluacion_id, usuario_id=actor.pk)
        if escritura:
            consulta = consulta.select_for_update()
        evaluacion = consulta.first()
        if evaluacion is None:
            raise PermissionDenied('Evaluación no disponible.')
        if escritura and (evaluacion.estado != 'EN_PROCESO' or evaluacion.fecha_fin is not None):
            raise ValidationError('La evaluación no admite cambios.')
        return evaluacion

    @staticmethod
    def _valoraciones(evaluacion):
        return ValoracionSubfactor.objects.filter(
            evaluacion_factor__evaluacion=evaluacion,
            evaluacion_factor__relevante=True,
            evaluacion_factor__importancia_relativa__in=(2, 3, 4),
            evaluacion_factor__factor_id=F('subfactor__factor_id'),
        ).select_related('subfactor', 'evaluacion_factor__factor__dimension').order_by('evaluacion_factor__factor__dimension__nombre', 'evaluacion_factor__factor__nombre', 'pk')

    @classmethod
    def _valoracion_editable(cls, evaluacion, valoracion_id):
        valoracion = cls._valoraciones(evaluacion).filter(
            pk=valoracion_id, estado_validacion=ValoracionSubfactor.PENDIENTE,
            valor_confirmado__isnull=True,
        ).first()
        if valoracion is None:
            raise PermissionDenied('Subfactor no disponible para cambios.')
        # Evitar bloquear relaciones externas; solo se bloquea la valoración.
        valoracion = ValoracionSubfactor.objects.select_for_update().get(pk=valoracion.pk)
        if valoracion.estado_validacion != ValoracionSubfactor.PENDIENTE or valoracion.valor_confirmado is not None:
            raise ValidationError('La valoración ya fue revisada.')
        return valoracion

    @staticmethod
    def _evidencias(evaluacion, valoracion):
        return [e for e in Evidencia.objects.filter(
            valoracion=valoracion, fragmento__documento__evaluacion=evaluacion,
        ).select_related('fragmento__documento').order_by('pk') if e.fragmento.contenido.strip()]

    @staticmethod
    def invalidar_propuestas(evaluacion, valoraciones):
        """Invalida propuestas pendientes bajo el bloqueo de la evaluación."""
        ValoracionSubfactor.objects.filter(
            evaluacion_factor__evaluacion=evaluacion, pk__in=valoraciones,
            estado_validacion=ValoracionSubfactor.PENDIENTE,
            valor_confirmado__isnull=True, valor_ia__isnull=False,
        ).update(valor_ia=None, justificacion_ia=None)

    @staticmethod
    def _registrar(valoracion, texto, origen):
        if not isinstance(texto, str) or not texto.strip() or len(texto.strip()) > 1000:
            raise ValidationError('La pregunta debe contener entre 1 y 1000 caracteres.')
        texto = texto.strip()
        clave = sha256(' '.join(texto.split()).casefold().encode('utf-8')).hexdigest()
        pregunta, creada = PreguntaComplementaria.objects.get_or_create(
            valoracion=valoracion, clave=clave, defaults={'texto': texto, 'origen': origen})
        if creada and valoracion.valor_ia is not None:
            PreguntasService.invalidar_propuestas(valoracion.evaluacion_factor.evaluacion_id, [valoracion.pk])
        return pregunta

    @classmethod
    @transaction.atomic
    def detectar_sin_evidencia(cls, actor, evaluacion_id):
        """Genera una petición básica solo si no hay evidencia ni respuestas previas.

        No es un análisis semántico. Los subfactores con fragmentos deben ser
        analizados por HU09 antes de afirmar que la información es suficiente.
        """
        evaluacion = cls._evaluacion(actor, evaluacion_id, escritura=True)
        preguntas = []
        for v in cls._valoraciones(evaluacion).filter(
            estado_validacion=ValoracionSubfactor.PENDIENTE, valor_confirmado__isnull=True
        ):
            if cls._evidencias(evaluacion, v) or v.preguntas_complementarias.exists():
                continue
            v = cls._valoracion_editable(evaluacion, v.pk)
            descripcion = v.subfactor.descripcion.strip()[:860]
            preguntas.append(cls._registrar(v, f'¿Qué información verificable puede aportar sobre este subfactor: {descripcion}?', 'SIN_EVIDENCIA'))
        return preguntas

    @classmethod
    @transaction.atomic
    def registrar_vacios(cls, actor, evaluacion_id, valoracion_id, preguntas):
        """Contrato para el analizador semántico: registra únicamente preguntas recibidas.

        El llamador debe analizar evidencia y respuestas antes de invocar este método.
        Un resultado vacío no cambia la valoración ni afirma suficiencia.
        """
        if not isinstance(preguntas, (list, tuple)):
            raise ValidationError('Se requiere una lista de preguntas.')
        evaluacion = cls._evaluacion(actor, evaluacion_id, escritura=True)
        valoracion = cls._valoracion_editable(evaluacion, valoracion_id)
        resultado = {}
        for texto in preguntas:
            pregunta = cls._registrar(valoracion, texto, 'ANALISIS')
            resultado[pregunta.pk] = pregunta
        return list(resultado.values())

    @classmethod
    @transaction.atomic
    def responder(cls, actor, evaluacion_id, pregunta_id, respuesta, version=None):
        if not isinstance(respuesta, str) or not respuesta.strip() or len(respuesta.strip()) > 10000:
            raise ValidationError('La respuesta debe contener entre 1 y 10000 caracteres.')
        evaluacion = cls._evaluacion(actor, evaluacion_id, escritura=True)
        pregunta = PreguntaComplementaria.objects.filter(
            pk=pregunta_id, valoracion__evaluacion_factor__evaluacion=evaluacion).first()
        if pregunta is None:
            raise PermissionDenied('Pregunta no disponible.')
        cls._valoracion_editable(evaluacion, pregunta.valoracion_id)
        pregunta = PreguntaComplementaria.objects.select_for_update().get(pk=pregunta.pk)
        if pregunta.fecha_descarte is not None:
            raise ValidationError('La pregunta fue descartada.')
        actual = pregunta.fecha_respuesta.isoformat() if pregunta.fecha_respuesta else ''
        if version is not None and version != actual:
            raise ValidationError('La respuesta cambió en otra sesión. Copie su borrador y recargue la página.')
        if pregunta.respuesta == respuesta.strip():
            return pregunta
        pregunta.respuesta = respuesta.strip()
        pregunta.respondido_por_id = actor.pk
        pregunta.fecha_respuesta = timezone.now()
        pregunta.save(update_fields=['respuesta', 'respondido_por', 'fecha_respuesta'])
        cls.invalidar_propuestas(evaluacion, [pregunta.valoracion_id])
        return pregunta

    @classmethod
    @transaction.atomic
    def descartar(cls, actor, evaluacion_id, pregunta_id, confirmar=False, version=None):
        """Retira propuestas sin borrar sus respuestas; exige confirmar la versión respondida."""
        evaluacion = cls._evaluacion(actor, evaluacion_id, escritura=True)
        pregunta = PreguntaComplementaria.objects.filter(
            pk=pregunta_id, valoracion__evaluacion_factor__evaluacion=evaluacion).first()
        if pregunta is None:
            raise PermissionDenied('Pregunta no disponible.')
        cls._valoracion_editable(evaluacion, pregunta.valoracion_id)
        pregunta = PreguntaComplementaria.objects.select_for_update().get(pk=pregunta_id)
        if pregunta.fecha_descarte is not None:
            return pregunta
        actual = pregunta.fecha_respuesta.isoformat() if pregunta.fecha_respuesta else ''
        if version is not None and version != actual:
            raise ValidationError('La respuesta cambió. Recargue antes de descartar.')
        if pregunta.respuesta.strip() and (not confirmar or version != actual):
            raise ValidationError('Confirme el descarte de la respuesta actual.')
        pregunta.descartada_por_id = actor.pk
        pregunta.fecha_descarte = timezone.now()
        pregunta.save(update_fields=['descartada_por', 'fecha_descarte'])
        # El historial conserva la huella original; la conclusión actual queda obsoleta.
        AnalisisSuficiencia.objects.filter(valoracion_id=pregunta.valoracion_id).update(huella='')
        cls.invalidar_propuestas(evaluacion, [pregunta.valoracion_id])
        return pregunta

    @classmethod
    @transaction.atomic
    def restaurar(cls, actor, evaluacion_id, pregunta_id):
        """Recupera una pregunta sin perder la auditoría del descarte anterior."""
        from django.contrib.admin.models import CHANGE, LogEntry
        from django.contrib.contenttypes.models import ContentType
        import json

        evaluacion = cls._evaluacion(actor, evaluacion_id, escritura=True)
        pregunta = PreguntaComplementaria.objects.filter(
            pk=pregunta_id, valoracion__evaluacion_factor__evaluacion=evaluacion).first()
        if pregunta is None:
            raise PermissionDenied('Pregunta no disponible.')
        valoracion = cls._valoracion_editable(evaluacion, pregunta.valoracion_id)
        pregunta = PreguntaComplementaria.objects.select_for_update().get(pk=pregunta_id)
        if pregunta.fecha_descarte is None:
            return pregunta
        pendientes = sum(estado_respuesta(p.respuesta) == 'PENDIENTE' for p in
                         valoracion.preguntas_complementarias.filter(fecha_descarte__isnull=True))
        if estado_respuesta(pregunta.respuesta) == 'PENDIENTE' and pendientes >= MAX_PENDIENTES:
            raise ValidationError('Cupo de preguntas pendientes alcanzado. Responda o descarte otra pregunta antes de restaurar.')
        LogEntry.objects.create(user_id=actor.pk, content_type=ContentType.objects.get_for_model(pregunta),
                                object_id=str(pregunta.pk), object_repr=pregunta.texto[:200], action_flag=CHANGE,
                                change_message=json.dumps({'accion': 'restaurar_pregunta_hu09',
                                    'descartada_por': pregunta.descartada_por_id,
                                    'fecha_descarte': pregunta.fecha_descarte.isoformat()}, ensure_ascii=False))
        pregunta.fecha_descarte = None
        pregunta.descartada_por = None
        pregunta.save(update_fields=['fecha_descarte', 'descartada_por'])
        AnalisisSuficiencia.objects.filter(valoracion_id=pregunta.valoracion_id).update(huella='')
        cls.invalidar_propuestas(evaluacion, [pregunta.valoracion_id])
        return pregunta

    @classmethod
    def contexto(cls, actor, evaluacion_id, valoracion_id=None):
        """Entrada auditable para futuros análisis HU09/HU10, sin asignar puntuaciones."""
        return cls._contexto(cls._evaluacion(actor, evaluacion_id), valoracion_id)

    @classmethod
    def _contexto(cls, evaluacion, valoracion_id=None):
        """Construye el contexto de una evaluación cuya autorización ya se comprobó."""
        resultado = []
        valoraciones = cls._valoraciones(evaluacion)
        if valoracion_id is not None:
            valoraciones = valoraciones.filter(pk=valoracion_id)
        # Dos consultas de relaciones para todos los subfactores, sin cargar embeddings.
        valoraciones = valoraciones.prefetch_related(
            Prefetch('evidencias', queryset=Evidencia.objects.filter(
                fragmento__documento__evaluacion=evaluacion
            ).select_related('fragmento__documento').defer('fragmento__embedding').order_by('pk'),
                to_attr='evidencias_hu09'),
            Prefetch('preguntas_complementarias', queryset=PreguntaComplementaria.objects.order_by('pk'),
                to_attr='preguntas_hu09'),
        )
        for v in valoraciones:
            evidencias = [e for e in v.evidencias_hu09 if e.fragmento.contenido.strip()]
            todas = v.preguntas_hu09
            preguntas = [p for p in todas if p.fecha_descarte is None]
            descartadas = [p for p in todas if p.fecha_descarte is not None]
            estado = ('REVISION_PENDIENTE' if evidencias or any(estado_respuesta(p.respuesta) == 'APORTADA' for p in preguntas)
                      else 'DESCONOCE' if any(estado_respuesta(p.respuesta) == 'DESCONOCE' for p in preguntas)
                      else 'SIN_APORTE' if any(estado_respuesta(p.respuesta) == 'NO_INFORMATIVA' for p in preguntas)
                      else 'SIN_EVIDENCIA')
            resultado.append({
                'valoracion_id': v.pk, 'subfactor': v.subfactor.descripcion,
                'factor': v.evaluacion_factor.factor.nombre,
                'dimension': v.evaluacion_factor.factor.dimension.nombre,
                'ir': v.evaluacion_factor.importancia_relativa,
                'editable': v.estado_validacion == ValoracionSubfactor.PENDIENTE and v.valor_confirmado is None,
                'estado_informacion': estado,
                'evidencias': [{'evidencia_id': e.pk, 'fragmento_id': e.fragmento_id,
                                'documento': e.fragmento.documento.nombre, 'pagina': e.fragmento.pagina,
                                'contenido': e.fragmento.contenido, 'referencia': e.referencia} for e in evidencias],
                'preguntas_descartadas': [{'pregunta_id': p.pk, 'texto': p.texto,
                                          'descartada_por': p.descartada_por_id, 'fecha_descarte': p.fecha_descarte,
                                          **({'respuesta': p.respuesta, 'respondido_por': p.respondido_por_id,
                                              'fecha_respuesta': p.fecha_respuesta} if p.respuesta else {})}
                                         for p in descartadas],
                'preguntas': [{'pregunta_id': p.pk, 'texto': p.texto, 'respuesta': p.respuesta,
                               'respondido_por': p.respondido_por_id, 'fecha_respuesta': p.fecha_respuesta,
                               'estado_respuesta': estado_respuesta(p.respuesta)}
                              for p in preguntas],
            })
        return resultado
