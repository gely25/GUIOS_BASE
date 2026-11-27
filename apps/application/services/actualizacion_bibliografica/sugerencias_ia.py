"""Clasificación bajo demanda de publicaciones recuperadas con IA (HU02)."""

import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.data.models import BusquedaBibliografica, BusquedaPublicacion, Publicacion, PublicacionFactor
from apps.data.repositorios import bibliografia as repo
from apps.external_services.ai_errors import AnalisisNoDisponible
from ..tareas_ia import en_orden, solicitar

from .autorizacion import autorizar_administrador

MAX_BYTES_ENTRADA = 12000
MAX_PUBLICACIONES_LOTE = 8


def _entrada(factor, publicaciones):
    return {
        'factor': {'id': factor.pk, 'nombre': factor.nombre},
        'publicaciones': publicaciones,
    }


def _lotes(factor, publicaciones):
    lote = []
    for publicacion in publicaciones:
        candidato = lote + [publicacion]
        entrada = _entrada(factor, candidato)
        excede_tamano = len(json.dumps(entrada, ensure_ascii=False).encode('utf-8')) > MAX_BYTES_ENTRADA
        if lote and (excede_tamano or len(candidato) > MAX_PUBLICACIONES_LOTE):
            yield lote
            lote = []
            candidato = [publicacion]
            entrada = _entrada(factor, candidato)
            excede_tamano = len(json.dumps(entrada, ensure_ascii=False).encode('utf-8')) > MAX_BYTES_ENTRADA
        if excede_tamano:
            raise AnalisisNoDisponible(
                'El título o resumen de una publicación supera el límite de contexto de la IA.')
        lote = candidato
    if lote:
        yield lote


def _validar_respuesta(respuesta, ids_validos):
    if not isinstance(respuesta, dict) or set(respuesta) != {'sugerencias'}:
        raise AnalisisNoDisponible('La IA devolvió una estructura inválida para las sugerencias bibliográficas.')
    sugerencias = respuesta['sugerencias']
    if not isinstance(sugerencias, list) or len(sugerencias) > len(ids_validos):
        raise AnalisisNoDisponible('La IA devolvió una lista inválida de sugerencias bibliográficas.')

    validadas = []
    ids_vistos = set()
    for sugerencia in sugerencias:
        if not isinstance(sugerencia, dict) or set(sugerencia) != {
            'publicacion_id', 'pertinencia', 'justificacion'
        }:
            raise AnalisisNoDisponible('La IA devolvió una sugerencia bibliográfica inválida.')
        publicacion_id = sugerencia['publicacion_id']
        if type(publicacion_id) is not int or publicacion_id not in ids_validos or publicacion_id in ids_vistos:
            raise AnalisisNoDisponible('La IA citó una publicación inexistente o repetida.')
        puntuacion = sugerencia['pertinencia']
        if isinstance(puntuacion, bool) or not isinstance(puntuacion, (int, float)):
            raise AnalisisNoDisponible('La pertinencia de una sugerencia debe ser numérica.')
        try:
            pertinencia = Decimal(str(puntuacion))
        except InvalidOperation as error:
            raise AnalisisNoDisponible('La pertinencia de una sugerencia es inválida.') from error
        if not pertinencia.is_finite() or not Decimal('1') <= pertinencia <= Decimal('100'):
            raise AnalisisNoDisponible('La pertinencia debe estar entre 1 y 100.')
        justificacion = sugerencia['justificacion']
        if not isinstance(justificacion, str) or not justificacion.strip() or len(justificacion.strip()) > 350:
            raise AnalisisNoDisponible('La justificación de una sugerencia bibliográfica es inválida.')
        ids_vistos.add(publicacion_id)
        validadas.append({
            'publicacion_id': publicacion_id,
            'pertinencia': pertinencia.quantize(Decimal('0.01')),
            'justificacion': justificacion.strip(),
        })
    return validadas


def sugerir_publicaciones(actor_id, busqueda_id, proveedor):
    """Analiza publicaciones de una búsqueda completada sin aprobar automáticamente sus vínculos."""
    autorizar_administrador(actor_id)
    busqueda = repo.obtener_busqueda(busqueda_id)
    if busqueda.estado != BusquedaBibliografica.COMPLETADA:
        raise ValidationError('Solo se pueden analizar con IA búsquedas completadas.')
    if busqueda.analisis_ia_completado:
        raise ValidationError('Esta búsqueda ya fue analizada con IA.')
    if busqueda.factor is None:
        raise ValidationError('La búsqueda no tiene un factor asociado.')

    resultados = repo.resultados_de(busqueda)
    if not resultados:
        raise ValidationError('La búsqueda no tiene publicaciones para analizar.')

    publicaciones = {resultado.publicacion.pk: resultado.publicacion for resultado in resultados}
    por_id = [
        {'id': publicacion.pk, 'titulo': publicacion.titulo, 'resumen': publicacion.resumen or ''}
        for publicacion in publicaciones.values()
    ]
    sugerencias = []
    factor = busqueda.factor

    def analizar(lote):
        entrada = _entrada(factor, lote)
        ids_lote = {publicacion['id'] for publicacion in lote}
        respuesta = solicitar(proveedor, entrada, ['busqueda', busqueda_id], actor_id)
        return _validar_respuesta(respuesta, ids_lote)

    for validadas in en_orden(proveedor, analizar, _lotes(factor, por_id)):
        sugerencias.extend(validadas)

    with transaction.atomic():
        bloqueada = BusquedaBibliografica.objects.select_for_update().get(pk=busqueda_id)
        if bloqueada.estado != BusquedaBibliografica.COMPLETADA:
            raise ValidationError('La búsqueda dejó de estar completada durante el análisis.')
        if bloqueada.analisis_ia_completado:
            raise ValidationError('Esta búsqueda ya fue analizada con IA.')
        # Dos búsquedas pueden compartir publicaciones en distinto orden.
        list(Publicacion.objects.select_for_update().filter(pk__in=publicaciones)
             .order_by('pk').values_list('pk', flat=True))
        vigentes = [
            {'id': pk, 'titulo': titulo, 'resumen': resumen or ''}
            for pk, titulo, resumen in BusquedaPublicacion.objects.filter(busqueda=bloqueada)
            .order_by('posicion', 'pk')
            .values_list('publicacion_id', 'publicacion__titulo', 'publicacion__resumen')
        ]
        if (bloqueada.factor_id != factor.pk or bloqueada.factor.nombre != factor.nombre
                or vigentes != por_id):
            raise ValidationError('Los resultados de la búsqueda cambiaron durante el análisis.')
        for sugerencia in sugerencias:
            repo.sugerir_vinculo(
                publicaciones[sugerencia['publicacion_id']],
                bloqueada.factor_id,
                sugerencia['pertinencia'],
                sugerencia['justificacion'],
                origen=PublicacionFactor.IA,
            )
        bloqueada.analisis_ia_completado = True
        bloqueada.save(update_fields=['analisis_ia_completado'])
    return len(sugerencias)
