"""HU09: evaluación adaptativa, orientativa y acotada por subfactor."""
from hashlib import sha256
import json

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.data.models import AnalisisSuficiencia, HistorialSuficiencia
from .preguntas import PreguntasService, MAX_PENDIENTES
from .analisis_preguntas import _filtrar_semantica

MAX_RONDAS = 3


class ResultadoSuficienciaInvalido(ValidationError):
    """La salida del proveedor no cumple el contrato; puede volver a intentarse."""


def _huella(fila):
    return sha256(json.dumps(fila, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _fila(actor, eid, vid):
    fila = next((f for f in PreguntasService.contexto(actor, eid, valoracion_id=vid) if f['valoracion_id'] == vid), None)
    if fila is None or not fila['editable']:
        raise ValidationError('Subfactor no disponible para análisis.')
    return fila


def _entrada(fila):
    fuentes = [{'id': f"E:{e['evidencia_id']}", 'contenido': e['contenido'], 'pagina': e['pagina']}
               for e in fila['evidencias']]
    fuentes += [{'id': f"R:{p['pregunta_id']}", 'pregunta': p['texto'], 'contenido': p['respuesta']}
                for p in fila['preguntas'] if p['estado_respuesta'] == 'APORTADA']
    return {'factor': fila['factor'], 'subfactor': fila['subfactor'], 'fuentes': fuentes,
            'preguntas': [{'texto': p['texto'], 'estado': p['estado_respuesta']} for p in fila['preguntas']],
            'descartadas': [p['texto'] for p in fila['preguntas_descartadas']]}


def _validar(resultado, entrada):
    if not isinstance(resultado, dict) or set(resultado) != {'estado', 'justificacion', 'referencias', 'preguntas'}:
        raise ResultadoSuficienciaInvalido('Resultado de suficiencia inválido.')
    estado, motivo, refs, preguntas = (resultado[k] for k in ('estado', 'justificacion', 'referencias', 'preguntas'))
    ids = {f['id'] for f in entrada['fuentes']}
    if (estado not in ('SUFICIENTE', 'INSUFICIENTE') or not isinstance(motivo, str)
        or not 0 < len(motivo.strip()) <= 1500 or not isinstance(refs, list) or len(refs) > 30
        or any(not isinstance(r, str) or r not in ids for r in refs)
        or not isinstance(preguntas, list) or len(preguntas) > MAX_PENDIENTES
        or any(not isinstance(p, str) or not 0 < len(p.strip()) <= 1000 or not p.strip().endswith('?') for p in preguntas)
        or (estado == 'SUFICIENTE' and (not refs or preguntas))):
        raise ResultadoSuficienciaInvalido('Resultado de suficiencia inválido o sin fuentes válidas.')
    return estado, motivo.strip(), list(dict.fromkeys(refs)), preguntas


class SuficienciaService:
    @staticmethod
    def adjuntar(filas):
        registros = {r.valoracion_id: r for r in AnalisisSuficiencia.objects.filter(
            valoracion_id__in=[f['valoracion_id'] for f in filas])}
        for f in filas:
            r = registros.get(f['valoracion_id'])
            vigente = bool(r and r.huella == _huella(f))
            f['suficiencia'] = r
            f['suficiencia_vigente'] = vigente
        return filas

    @classmethod
    def analizar(cls, actor, eid, vid, proveedor, modelo, vectorizador=None, generar_preguntas=True):
        ev = PreguntasService._evaluacion(actor, eid)
        if ev.estado != 'EN_PROCESO' or ev.fecha_fin is not None:
            raise ValidationError('La evaluación no admite cambios.')
        fila = _fila(actor, eid, vid)
        huella = _huella(fila)
        anterior = AnalisisSuficiencia.objects.filter(valoracion_id=vid).first()
        if anterior and anterior.huella == huella:
            return anterior, 0
        if any(p['estado_respuesta'] == 'PENDIENTE' for p in fila['preguntas']):
            raise ValidationError('Responda o descarte las preguntas pendientes antes de reevaluar.')
        rondas = anterior.rondas if anterior else 0
        entrada = _entrada(fila)
        if rondas >= MAX_RONDAS:
            estado, motivo, refs, elegidas = 'REVISION_MANUAL', 'Límite de rondas alcanzado. El decisor debe revisar la información disponible.', [], []
        else:
            estado, motivo, refs, preguntas = _validar(proveedor(entrada), entrada)
            conocidas = [p['texto'] for p in fila['preguntas'] + fila['preguntas_descartadas']]
            elegidas = _filtrar_semantica(conocidas, preguntas, MAX_PENDIENTES, vectorizador) if generar_preguntas else []
            rondas += 1
            if estado == 'SUFICIENTE':
                estado = 'SUFICIENCIA_PROPUESTA'
            elif not elegidas:
                estado = 'REVISION_MANUAL'
            else:
                estado = 'FALTAN_DATOS'
        with transaction.atomic():
            ev = PreguntasService._evaluacion(actor, eid, escritura=True)
            PreguntasService._valoracion_editable(ev, vid)
            actual = AnalisisSuficiencia.objects.filter(valoracion_id=vid).first()
            if _huella(_fila(actor, eid, vid)) != huella or (actual.fecha if actual else None) != (anterior.fecha if anterior else None):
                raise ValidationError('La información cambió durante el análisis. Repita la operación.')
            nuevas = PreguntasService.registrar_vacios(actor, eid, vid, elegidas)
            registro, _ = AnalisisSuficiencia.objects.update_or_create(valoracion_id=vid, defaults={
                'huella': _huella(_fila(actor, eid, vid)), 'estado': estado, 'justificacion': motivo,
                'referencias': refs, 'rondas': rondas, 'modelo': modelo,
            })
            HistorialSuficiencia.objects.create(valoracion_id=vid, actor_id=actor.pk,
                huella=registro.huella, estado=registro.estado, justificacion=registro.justificacion,
                referencias=registro.referencias, rondas=registro.rondas, modelo=registro.modelo,
                fecha=registro.fecha)
            return registro, len(nuevas)
