"""Contrato HU09 para analizar vacíos con un proveedor semántico inyectable.

No califica subfactores ni declara suficiencia certificada. El proveedor debe
recibir exclusivamente información de la valoración y devolver preguntas.
"""
import math
import re
import unicodedata

from django.core.exceptions import ValidationError
from django.db import transaction
from apps.data.models import AnalisisSuficiencia

from apps.application.services.preguntas import PreguntasService, MAX_PENDIENTES
from .tareas_ia import solicitar

UMBRAL_SEMANTICO = .88


def _tokens(texto):
    texto = ''.join(c for c in unicodedata.normalize('NFKD', texto.casefold())
                    if not unicodedata.combining(c))
    return re.findall(r'\w+', texto)


def _marcas(tokens):
    return {t for t in tokens if any(c.isdigit() for c in t) or t in {'no', 'sin'}}


def _parecida(a, b):
    a, b = _tokens(a), _tokens(b)
    if a == b:
        return True
    # Filtro conservador de variaciones textuales; no prueba equivalencia semántica.
    if _marcas(a) != _marcas(b):
        return False
    sa, sb = set(a), set(b)
    return min(len(sa), len(sb)) >= 5 and len(sa & sb) / len(sa | sb) >= .9


def _normalizar_vectores(vectores, cantidad):
    if not isinstance(vectores, (list, tuple)) or len(vectores) != cantidad:
        raise ValidationError('Cantidad de embeddings inválida.')
    normalizados = []
    dimension = None
    for v in vectores:
        try:
            if not isinstance(v, (list, tuple)) or not v or any(type(x) not in (float, int) or not math.isfinite(x) for x in v):
                raise ValueError
            if dimension is not None and len(v) != dimension:
                raise ValueError
            dimension = len(v)
            norma = math.hypot(*v)
            if not math.isfinite(norma) or norma == 0:
                raise ValueError
            normalizados.append(tuple(x / norma for x in v))
        except (ValueError, OverflowError):
            raise ValidationError('Embedding inválido.')
    return normalizados


def _filtrar_semantica(conocidas, propuestas, cupo, vectorizador=None):
    # Compara también preguntas descartadas y propuestas aceptadas en esta ronda.
    candidatas = [p.strip() for p in propuestas if not any(_parecida(p, a) for a in conocidas)]
    if not candidatas:
        return []
    textos = conocidas + candidatas
    vectores = (_normalizar_vectores(vectorizador(textos), len(textos))
                if vectorizador is not None else None)
    indices = list(range(len(conocidas)))
    elegidas = []
    for i in range(len(conocidas), len(textos)):
        if any(_parecida(textos[i], textos[j]) or (
            vectores is not None and _marcas(_tokens(textos[i])) == _marcas(_tokens(textos[j]))
            and math.fsum(x*y for x, y in zip(vectores[i], vectores[j])) >= UMBRAL_SEMANTICO
        ) for j in indices):
            continue
        elegidas.append(textos[i])
        indices.append(i)
        if len(elegidas) == cupo:
            break
    return elegidas


class AnalisisPreguntasService:
    @classmethod
    def analizar(cls, actor, evaluacion_id, analizador, valoracion_id=None, vectorizador=None):
        """analizador(entrada) -> list[str]; no realizar llamadas bajo bloqueo.

        El analizador debe distinguir hechos, ausencia y desconocimiento y no
        preguntar por aspectos ya cubiertos. Una lista vacía no implica que
        la evidencia haya sido validada definitivamente.
        """
        evaluacion = PreguntasService._evaluacion(actor, evaluacion_id)
        if evaluacion.estado != 'EN_PROCESO' or evaluacion.fecha_fin is not None:
            raise ValidationError('La evaluación no admite cambios.')
        inicial = PreguntasService.contexto(actor, evaluacion_id)
        seleccion = [f for f in inicial if f['editable'] and (valoracion_id is None or f['valoracion_id'] == valoracion_id)]
        if valoracion_id is not None and not seleccion:
            raise ValidationError('Subfactor no disponible para análisis.')
        propuestas = []
        for fila in seleccion:
            if not fila['editable']:
                continue
            if AnalisisSuficiencia.objects.filter(valoracion_id=fila['valoracion_id']).exists():
                if valoracion_id is not None:
                    raise ValidationError('Continúe mediante la evaluación de suficiencia adaptativa.')
                continue
            cupo = max(0, MAX_PENDIENTES - sum(p['estado_respuesta'] == 'PENDIENTE' for p in fila['preguntas']))
            if not cupo:
                continue
            entrada = {
                'max_preguntas': cupo,
                'preguntas_descartadas': [p['texto'] for p in fila['preguntas_descartadas']],
                'factor': fila['factor'], 'subfactor': fila['subfactor'],
                'evidencias': [{'contenido': e['contenido'], 'pagina': e['pagina']} for e in fila['evidencias']],
                'preguntas': [{'texto': p['texto'], 'respuesta': p['respuesta'] if p['estado_respuesta'] == 'APORTADA' else '',
                               'estado_respuesta': p['estado_respuesta']} for p in fila['preguntas']],
            }
            preguntas = solicitar(analizador, entrada, ['evaluacion', evaluacion_id, fila['valoracion_id']], actor.pk)
            if not isinstance(preguntas, (tuple, list)) or len(preguntas) > MAX_PENDIENTES or any(
                not isinstance(p, str) or not p.strip() or len(p.strip()) > 1000 for p in preguntas
            ):
                raise ValidationError('El analizador devolvió preguntas inválidas.')
            conocidas = [p['texto'] for p in fila['preguntas'] + fila['preguntas_descartadas']]
            elegidas = _filtrar_semantica(conocidas, preguntas, cupo, vectorizador)
            propuestas.append((fila['valoracion_id'], elegidas))
        with transaction.atomic():
            PreguntasService._evaluacion(actor, evaluacion_id, escritura=True)
            if inicial != PreguntasService.contexto(actor, evaluacion_id):
                raise ValidationError('La información cambió durante el análisis. Repita la operación.')
            existentes = {p['pregunta_id'] for f in inicial for p in f['preguntas'] + f['preguntas_descartadas']}
            nuevas = {}
            for valoracion_id, preguntas in propuestas:
                if AnalisisSuficiencia.objects.filter(valoracion_id=valoracion_id).exists():
                    raise ValidationError('La revisión adaptativa cambió durante el análisis. Repita la operación.')
                for pregunta in PreguntasService.registrar_vacios(actor, evaluacion_id, valoracion_id, preguntas):
                    if pregunta.pk not in existentes:
                        nuevas[pregunta.pk] = pregunta
            return list(nuevas.values())
