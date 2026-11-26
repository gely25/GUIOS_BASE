"""Cola HU09: sin llamadas externas dentro de la transacción de asignación."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from apps.data.models import LoteHU09
from apps.external_services.ai_errors import AnalisisNoDisponible
from .preguntas import PreguntasService
from .suficiencia import ResultadoSuficienciaInvalido, SuficienciaService

ACTIVOS = ('EN_COLA', 'EN_PROCESO')


class LotesHU09Service:
    @staticmethod
    @transaction.atomic
    def encolar(actor, eid):
        ev = PreguntasService._evaluacion(actor, eid, escritura=True)
        anterior = LoteHU09.objects.filter(evaluacion=ev, estado__in=ACTIVOS).first()
        if anterior:
            return anterior
        filas = SuficienciaService.adjuntar(PreguntasService.contexto(actor, eid))
        objetivos = [f['valoracion_id'] for f in filas if f['editable'] and not f['suficiencia_vigente']
                     and not any(p['estado_respuesta'] == 'PENDIENTE' for p in f['preguntas'])]
        if not objetivos:
            raise ValidationError('No hay subfactores disponibles para analizar. Responda las preguntas pendientes o cambie la información.')
        return LoteHU09.objects.create(evaluacion=ev, solicitante=actor, objetivos=objetivos)

    @staticmethod
    def estado(actor, eid):
        ev = PreguntasService._evaluacion(actor, eid)
        lote = LoteHU09.objects.filter(evaluacion=ev).order_by('-pk').first()
        if not lote:
            return None
        return {'id': lote.pk, 'estado': lote.estado, 'total': len(lote.objetivos),
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
        for vid in lote.objetivos:
            if vid in terminados:
                continue
            resultado = {'valoracion': vid, 'preguntas': 0}
            try:
                filas = SuficienciaService.adjuntar(PreguntasService.contexto(actor, lote.evaluacion_id, valoracion_id=vid))
                fila = next((f for f in filas if f['valoracion_id'] == vid), None)
                if not fila or not fila['editable'] or fila['suficiencia_vigente'] or any(p['estado_respuesta']=='PENDIENTE' for p in fila['preguntas']):
                    resultado['estado'] = 'OMITIDO'
                else:
                    registro, cantidad = SuficienciaService.analizar(actor, lote.evaluacion_id, vid, proveedor, modelo, vectorizador)
                    resultado.update(estado=registro.estado, preguntas=cantidad)
            except (AnalisisNoDisponible, ResultadoSuficienciaInvalido):
                resultado['estado'] = 'ERROR'
            except (PermissionDenied, ValidationError):
                resultado['estado'] = 'OMITIDO'
            lote.resultados = [*lote.resultados, resultado]
            lote.save(update_fields=['resultados', 'actualizado'])
        lote.estado = 'FINALIZADO'
        lote.save(update_fields=['estado', 'actualizado'])
        return lote
