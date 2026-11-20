"""Contrato de lectura para HU10. No genera ni confirma puntuaciones."""
from django.core.exceptions import ValidationError
from apps.data.models import LoteHU09
from .preguntas import PreguntasService
from .suficiencia import SuficienciaService, _huella


class PreparacionHU10Service:
    @staticmethod
    def estado(fila, abierto=True, lote_activo=False):
        if not abierto or not fila['editable']:
            return 'SOLO_LECTURA'
        if lote_activo:
            return 'ANALISIS_EN_CURSO'
        if any(p['estado_respuesta'] == 'PENDIENTE' for p in fila['preguntas']):
            return 'PREGUNTAS_PENDIENTES'
        r = fila.get('suficiencia')
        if not r or not fila.get('suficiencia_vigente'):
            return 'ANALISIS_PENDIENTE'
        if r.estado == 'SUFICIENCIA_PROPUESTA' and r.referencias:
            return 'PROPUESTA_HABILITADA'
        return 'REVISION_MANUAL'

    @classmethod
    def obtener(cls, actor, evaluacion_id):
        """Contexto con procedencia explícita; las respuestas no son hechos certificados.

        HU10 debe comprobar vigencia antes de guardar su propia propuesta.
        No se permite valorar automáticamente una fila en revisión manual.
        """
        ev = PreguntasService._evaluacion(actor, evaluacion_id)
        abierto = ev.estado == 'EN_PROCESO' and ev.fecha_fin is None
        activo = LoteHU09.objects.filter(evaluacion=ev, estado__in=('EN_COLA', 'EN_PROCESO')).exists()
        filas = PreguntasService.contexto(actor, evaluacion_id)
        huellas = {f['valoracion_id']: _huella(f) for f in filas}
        SuficienciaService.adjuntar(filas)
        datos = []
        for f in filas:
            r = f['suficiencia']
            estado = cls.estado(f, abierto, activo)
            fuentes = [dict(e, id=f"E:{e['evidencia_id']}", origen='DOCUMENTO') for e in f['evidencias']]
            fuentes += [dict(id=f"R:{p['pregunta_id']}", origen='DECLARACION_DECISOR',
                pregunta_id=p['pregunta_id'], pregunta=p['texto'], contenido=p['respuesta'],
                actor=p['respondido_por'], fecha=p['fecha_respuesta'].isoformat() if p['fecha_respuesta'] else None)
                for p in f['preguntas'] if p['estado_respuesta'] == 'APORTADA']
            datos.append({'valoracion_id': f['valoracion_id'], 'factor': f['factor'], 'subfactor': f['subfactor'],
                'dimension': f['dimension'], 'ir': f['ir'], 'huella': huellas[f['valoracion_id']],
                'estado': estado, 'fuentes': fuentes,
                'sin_informacion': [{'pregunta_id': p['pregunta_id'], 'estado': p['estado_respuesta']}
                    for p in f['preguntas'] if p['estado_respuesta'] != 'APORTADA'],
                'suficiencia': {'estado': r.estado, 'justificacion': r.justificacion, 'referencias': r.referencias,
                    'modelo': r.modelo, 'fecha': r.fecha.isoformat(), 'rondas': r.rondas}
                    if r and f['suficiencia_vigente'] else None})
        return {'version_contrato': 1, 'evaluacion_id': ev.pk, 'subfactores': datos}

    @classmethod
    def validar_vigencia(cls, actor, eid, vid, huella):
        """HU10 debe invocar dentro de su transacción, tras bloquear evaluación/valoración.

        Devuelve el contexto vigente solo para una propuesta automática habilitada.
        """
        fila = next((f for f in cls.obtener(actor, eid)['subfactores'] if f['valoracion_id'] == vid), None)
        if not fila or fila['estado'] != 'PROPUESTA_HABILITADA' or fila['huella'] != huella:
            raise ValidationError('El contexto HU09 cambió o requiere revisión antes de valorar.')
        return fila
