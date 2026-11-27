"""Cola HU09: sin llamadas externas dentro de la transacción de asignación."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from apps.data.models import LoteHU09
from apps.external_services.ai_errors import AnalisisNoDisponible
from .preguntas import PreguntasService
from .suficiencia import ResultadoSuficienciaInvalido, SuficienciaService
from .tareas_ia import en_orden

ACTIVOS = ('EN_COLA', 'EN_PROCESO')
ETIQUETAS_LOTE = {'EN_COLA': 'En cola', 'EN_PROCESO': 'En curso', 'FINALIZADO': 'Finalizado'}


class LotesHU09Service:
    @staticmethod
    def objetivos(actor, eid):
        filas = SuficienciaService.adjuntar(PreguntasService.contexto(actor, eid))
        return [f['valoracion_id'] for f in filas if f['editable'] and not f['suficiencia_vigente']
                and not any(p['estado_respuesta'] == 'PENDIENTE' for p in f['preguntas'])]

    @staticmethod
    @transaction.atomic
    def encolar(actor, eid):
        ev = PreguntasService._evaluacion(actor, eid, escritura=True)
        anterior = LoteHU09.objects.filter(evaluacion=ev, estado__in=ACTIVOS).first()
        if anterior:
            return anterior
        objetivos = LotesHU09Service.objetivos(actor, eid)
        if not objetivos:
            raise ValidationError('No hay subfactores disponibles para analizar. Responda las preguntas pendientes o cambie la información.')
        return LoteHU09.objects.create(evaluacion=ev, solicitante=actor, objetivos=objetivos)

    @staticmethod
    def estado(actor, eid):
        return LotesHU09Service.estado_de(PreguntasService._evaluacion(actor, eid))

    @staticmethod
    def estado_de(ev):
        lote = LoteHU09.objects.filter(evaluacion=ev).order_by('-pk').first()
        if not lote:
            return None
        return {'id': lote.pk, 'estado': lote.estado, 'etiqueta_estado': ETIQUETAS_LOTE.get(lote.estado, 'Sin estado disponible'),
                'total': len(lote.objetivos),
                'procesados': len(lote.resultados),
                'errores': sum(r['estado'] == 'ERROR' for r in lote.resultados),
                'omitidos': sum(r['estado'] == 'OMITIDO' for r in lote.resultados),
                'preguntas_nuevas': sum(r.get('preguntas', 0) for r in lote.resultados),
                'resultados': lote.resultados}

    @staticmethod
    @transaction.atomic
    def tomar():
        lote = LoteHU09.objects.select_for_update(skip_locked=True).filter(estado='EN_COLA').order_by('pk').first()
        if lote:
            lote.estado = 'EN_PROCESO'
            lote.save(update_fields=['estado', 'actualizado'])
        return lote

    @staticmethod
    def procesar(lote, proveedor, modelo, vectorizador=None):
        """Invocado por el worker tras reclamar el lote; conserva resultados parciales."""
        if lote.estado != 'EN_PROCESO':
            raise ValidationError('El lote no está asignado al trabajador.')
        actor = lote.solicitante
        terminados = {r['valoracion'] for r in lote.resultados}
        def analizar(vid):
            resultado = {'valoracion': vid, 'preguntas': 0}
            try:
                registro, cantidad = SuficienciaService.analizar(
                    actor, lote.evaluacion_id, vid, proveedor, modelo, vectorizador, omitir_vigente=True,
                )
                resultado.update(estado=registro.estado if registro else 'OMITIDO', preguntas=cantidad)
            except (AnalisisNoDisponible, ResultadoSuficienciaInvalido):
                resultado['estado'] = 'ERROR'
            except (PermissionDenied, ValidationError):
                resultado['estado'] = 'OMITIDO'
            return resultado

        pendientes = dict.fromkeys(vid for vid in lote.objetivos if vid not in terminados)
        for resultado in en_orden(proveedor, analizar, pendientes):
            lote.resultados = [*lote.resultados, resultado]
            lote.save(update_fields=['resultados', 'actualizado'])
        lote.estado = 'FINALIZADO'
        lote.save(update_fields=['estado', 'actualizado'])
        return lote
