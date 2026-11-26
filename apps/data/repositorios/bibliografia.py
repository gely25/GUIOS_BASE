"""
Consultas de búsquedas, publicaciones y vínculos publicación-factor (HU02).
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.business_rules.publicaciones import huella_publicacion, normalizar_doi
from apps.business_rules.rules_engine import ANIO_FIN, ANIO_INICIO
from apps.data.models import BusquedaBibliografica, BusquedaPublicacion, Publicacion, PublicacionFactor

Busqueda = BusquedaBibliografica


# --- Búsquedas ---------------------------------------------------------------

def crear_busquedas(lote, consultas, fuente, anio_inicio, anio_fin, actor):
    """Una búsqueda PENDIENTE por (factor_id, consulta)."""
    return Busqueda.objects.bulk_create([
        Busqueda(lote=lote, factor_id=factor_id, consulta=consulta, fuente=fuente,
                 anio_inicio=anio_inicio, anio_fin=anio_fin, lanzada_por=actor,
                 estado=Busqueda.PENDIENTE)
        for factor_id, consulta in consultas
    ])


def hay_busquedas_activas():
    return Busqueda.objects.filter(estado__in=[Busqueda.PENDIENTE, Busqueda.EN_CURSO]).exists()


def tomar_siguiente_pendiente():
    """Marca EN_CURSO la búsqueda pendiente más antigua y la devuelve (None si no hay).

    `skip_locked` permite correr varios procesadores sin que tomen la misma búsqueda.
    """
    with transaction.atomic():
        busqueda = (Busqueda.objects.select_for_update(skip_locked=True)
                    .filter(estado=Busqueda.PENDIENTE).order_by('busqueda_id').first())
        if busqueda is None:
            return None
        busqueda.estado = Busqueda.EN_CURSO
        busqueda.fecha_inicio = timezone.now()
        busqueda.progreso = 0
        busqueda.save(update_fields=['estado', 'fecha_inicio', 'progreso'])
        return busqueda


def liberar_colgadas(minutos):
    """Vuelve a PENDIENTE las búsquedas EN_CURSO que llevan demasiado tiempo (el proceso murió)."""
    limite = timezone.now() - timedelta(minutes=minutos)
    return Busqueda.objects.filter(estado=Busqueda.EN_CURSO, fecha_inicio__lt=limite).update(
        estado=Busqueda.PENDIENTE, progreso=0)


def actualizar_busqueda(busqueda, **campos):
    for nombre, valor in campos.items():
        setattr(busqueda, nombre, valor)
    busqueda.save(update_fields=list(campos))


def busquedas_del_lote(lote):
    return list(Busqueda.objects.filter(lote=lote).select_related('factor').order_by('busqueda_id'))


def ultimo_lote():
    ultima = Busqueda.objects.exclude(lote=None).order_by('-busqueda_id').values_list('lote', flat=True).first()
    return ultima


def _busquedas_con_conteos():
    """Consulta base de búsquedas con el número de publicaciones y sugerencias."""
    return (
        Busqueda.objects.select_related('factor', 'lanzada_por')
        .annotate(
            n_resultados=Count('resultados', distinct=True),
            n_sugeridas=Count('resultados__publicacion__factores', distinct=True,
                              filter=Q(resultados__publicacion__factores__estado=PublicacionFactor.SUGERIDA)),
        )
        .order_by('-busqueda_id'))


def busquedas_recientes(limite=50):
    return list(_busquedas_con_conteos()[:limite])


def busquedas_paginables():
    """QuerySet completo para paginar en la vista sin cargar todas las filas."""
    return _busquedas_con_conteos()


def obtener_busqueda(busqueda_id):
    return Busqueda.objects.select_related('factor', 'lanzada_por').get(pk=busqueda_id)


# --- Publicaciones -----------------------------------------------------------

def guardar_publicacion(resultado, fuente):
    """Crea la publicación o devuelve la existente (misma huella: mismo DOI o mismo título+año)."""
    huella = huella_publicacion(resultado.doi, resultado.titulo, resultado.anio)
    existente = Publicacion.objects.filter(huella=huella).first()
    if existente:
        return existente
    doi = normalizar_doi(resultado.doi)
    if doi:
        existente = Publicacion.objects.filter(doi=doi).first()
        if existente:
            return existente
    try:
        with transaction.atomic():
            return Publicacion.objects.create(
                titulo=resultado.titulo, anio=resultado.anio, doi=doi, url=resultado.url,
                resumen=resultado.resumen, fuente=fuente, huella=huella)
    except IntegrityError:
        # Otro proceso la guardó al mismo tiempo.
        return Publicacion.objects.get(Q(huella=huella) | Q(doi=doi) if doi else Q(huella=huella))


def registrar_resultado(busqueda, publicacion, posicion):
    BusquedaPublicacion.objects.get_or_create(
        busqueda=busqueda, publicacion=publicacion,
        defaults={'posicion': posicion, 'fecha_recuperacion': timezone.now()})


def resultados_de(busqueda):
    """Publicaciones recuperadas por la búsqueda, con sus vínculos a factores."""
    return list(
        BusquedaPublicacion.objects.filter(busqueda=busqueda)
        .select_related('publicacion')
        .prefetch_related('publicacion__factores__factor')
        .order_by('posicion', 'pk'))


def busqueda_contiene(busqueda_id, publicacion_id):
    return BusquedaPublicacion.objects.filter(busqueda_id=busqueda_id, publicacion_id=publicacion_id).exists()


def marcar_seleccionada(busqueda_id, publicacion_id):
    BusquedaPublicacion.objects.filter(
        busqueda_id=busqueda_id, publicacion_id=publicacion_id).update(seleccionada=True)


# --- Vínculos publicación-factor --------------------------------------------

def sugerir_vinculo(publicacion, factor_id, pertinencia, justificacion, origen):
    """Crea o actualiza solo sugerencias pendientes; no pisa decisiones del administrador."""
    vinculo, creado = PublicacionFactor.objects.get_or_create(
        publicacion=publicacion, factor_id=factor_id,
        defaults={'pertinencia': pertinencia, 'justificacion': justificacion,
                  'origen': origen, 'estado': PublicacionFactor.SUGERIDA})
    if not creado and vinculo.estado == PublicacionFactor.SUGERIDA:
        vinculo.pertinencia = pertinencia
        vinculo.justificacion = justificacion
        vinculo.origen = origen
        vinculo.save(update_fields=['pertinencia', 'justificacion', 'origen'])
    return vinculo


def obtener_vinculo(vinculo_id, bloquear=False):
    consulta = PublicacionFactor.objects.select_related('publicacion', 'factor')
    if bloquear:
        consulta = consulta.select_for_update()
    return consulta.get(pk=vinculo_id)


def revisar_vinculo(vinculo, estado, actor):
    vinculo.estado = estado
    vinculo.revisado_por = actor
    vinculo.fecha_revision = timezone.now()
    vinculo.save(update_fields=['estado', 'revisado_por', 'fecha_revision'])
    return vinculo


def vincular_manual(publicacion_id, factor_id, justificacion, actor):
    """Vínculo aprobado creado por el administrador. Si ya existía, lo aprueba."""
    vinculo, creado = PublicacionFactor.objects.select_for_update().get_or_create(
        publicacion_id=publicacion_id, factor_id=factor_id,
        defaults={'origen': PublicacionFactor.MANUAL, 'estado': PublicacionFactor.APROBADA,
                  'justificacion': justificacion or None, 'revisado_por': actor,
                  'fecha_revision': timezone.now()})
    if not creado:
        if justificacion:
            vinculo.justificacion = justificacion
            vinculo.save(update_fields=['justificacion'])
        revisar_vinculo(vinculo, PublicacionFactor.APROBADA, actor)
    return vinculo


def aprobadas_por_factor():
    """{factor_id: publicaciones distintas con vínculo APROBADO y año 2020-2025}."""
    filas = (PublicacionFactor.objects
             .filter(estado=PublicacionFactor.APROBADA,
                     publicacion__anio__gte=ANIO_INICIO, publicacion__anio__lte=ANIO_FIN)
             .values('factor_id')
             .annotate(total=Count('publicacion_id', distinct=True)))
    return {f['factor_id']: f['total'] for f in filas}


def conteo_vinculos():
    return PublicacionFactor.objects.aggregate(
        aprobados=Count('pk', filter=Q(estado=PublicacionFactor.APROBADA)),
        sugeridos=Count('pk', filter=Q(estado=PublicacionFactor.SUGERIDA)),
        rechazados=Count('pk', filter=Q(estado=PublicacionFactor.RECHAZADA)),
    )
