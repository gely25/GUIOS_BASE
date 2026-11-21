"""
Búsqueda bibliográfica automatizada (RF01) y registro de publicaciones (RF02, sin IA).

`lanzar_actualizacion` solo deja las búsquedas en cola (PENDIENTE) y vuelve enseguida.
`manage.py procesar_busquedas` las ejecuta en segundo plano con `ejecutar_busqueda`.
"""

import logging
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.business_rules.coincidencia import sugerir_factores
from apps.business_rules.glosario_bibliografico import construir_consulta, terminos_de
from apps.business_rules.rules_engine import ANIO_FIN, ANIO_INICIO
from apps.data.repositorios import bibliografia as repo
from apps.data.repositorios import catalogo as repo_catalogo
from apps.external_services.bibliografia import ErrorFuenteCientifica, fuente_configurada

from .autorizacion import autorizar_administrador

log = logging.getLogger(__name__)

Busqueda = repo.Busqueda
MINUTOS_COLGADA = 30


def terminos_por_factor(factores):
    """Términos de coincidencia: glosario en inglés + nombre del factor en español."""
    return {f.pk: (*terminos_de(f.nombre), f.nombre) for f in factores}


def lanzar_actualizacion(actor_id, factor_ids=None, fuente=None):
    """
    Deja en cola una búsqueda por factor activo de la versión vigente y devuelve el `lote`.
    No llama a la API: eso lo hace el procesador en segundo plano (RNF09).
    """
    actor = autorizar_administrador(actor_id)
    with transaction.atomic():
        if repo.hay_busquedas_activas():
            raise ValidationError('Ya hay una actualización en curso; espera a que termine.')
        factores = repo_catalogo.factores_de(repo_catalogo.version_activa())
        if factor_ids:
            factores = [f for f in factores if f.pk in set(factor_ids)]
        if not factores:
            raise ValidationError('No hay factores activos en el catálogo vigente. '
                                  'Carga el catálogo con: python manage.py cargar_catalogo_guios')
        lote = uuid.uuid4()
        nombre_fuente = (fuente or fuente_configurada()).nombre
        repo.crear_busquedas(lote, [(f.pk, construir_consulta(f.nombre)) for f in factores],
                             nombre_fuente, ANIO_INICIO, ANIO_FIN, actor)
    return lote


def ejecutar_busqueda(busqueda, fuente=None, maximo=None):
    """
    Consulta la fuente, guarda las publicaciones (deduplicadas) y sugiere factores por
    palabras clave. Si la fuente falla, la búsqueda queda FALLIDA y no se interrumpe nada más.
    """
    fuente = fuente or fuente_configurada()
    maximo = maximo or settings.BIBLIOGRAPHIC_MAX_RESULTADOS
    try:
        resultados = fuente.buscar(busqueda.consulta, busqueda.anio_inicio or ANIO_INICIO,
                                   busqueda.anio_fin or ANIO_FIN, maximo)
    except ErrorFuenteCientifica as error:
        repo.actualizar_busqueda(busqueda, estado=Busqueda.FALLIDA, mensaje_error=str(error)[:1000],
                                 fecha_fin=timezone.now(), progreso=100)
        return busqueda

    factores = repo_catalogo.factores_de(repo_catalogo.version_activa())
    terminos = terminos_por_factor(factores)
    total = len(resultados)
    for posicion, resultado in enumerate(resultados, start=1):
        with transaction.atomic():
            publicacion = repo.guardar_publicacion(resultado, fuente.nombre)
            repo.registrar_resultado(busqueda, publicacion, posicion)
            for sugerencia in sugerir_factores(publicacion.titulo, publicacion.resumen or '', terminos):
                repo.sugerir_vinculo(publicacion, sugerencia.clave, sugerencia.pertinencia,
                                     sugerencia.justificacion)
        if posicion % 10 == 0 or posicion == total:
            repo.actualizar_busqueda(busqueda, progreso=int(posicion * 100 / total))

    repo.actualizar_busqueda(busqueda, estado=Busqueda.COMPLETADA, total_resultados=total,
                             progreso=100, fecha_fin=timezone.now(), mensaje_error=None)
    return busqueda


def procesar_pendientes(limite=None, fuente=None):
    """Ejecuta búsquedas pendientes una por una. Devuelve cuántas procesó."""
    repo.liberar_colgadas(MINUTOS_COLGADA)
    procesadas = 0
    while limite is None or procesadas < limite:
        busqueda = repo.tomar_siguiente_pendiente()
        if busqueda is None:
            break
        try:
            ejecutar_busqueda(busqueda, fuente=fuente)
        except Exception as error:  # un error inesperado no debe dejarla EN_CURSO para siempre
            log.exception('Fallo al procesar la búsqueda %s', busqueda.pk)
            repo.actualizar_busqueda(busqueda, estado=Busqueda.FALLIDA, progreso=100,
                                     mensaje_error=f'Error inesperado: {error}'[:1000],
                                     fecha_fin=timezone.now())
        procesadas += 1
    return procesadas


def estado_lote(lote=None):
    """Resumen del avance de un lote (por defecto, el último) para la interfaz."""
    lote = lote or repo.ultimo_lote()
    busquedas = repo.busquedas_del_lote(lote) if lote else []
    total = len(busquedas)
    por_estado = {estado: 0 for estado, _ in Busqueda.ESTADOS}
    for b in busquedas:
        por_estado[b.estado] = por_estado.get(b.estado, 0) + 1
    terminadas = por_estado[Busqueda.COMPLETADA] + por_estado[Busqueda.FALLIDA]
    avance = sum(100 if b.estado in (Busqueda.COMPLETADA, Busqueda.FALLIDA) else b.progreso
                 for b in busquedas)
    return {
        'lote': str(lote) if lote else None,
        'total': total,
        'por_estado': por_estado,
        'terminado': total > 0 and terminadas == total,
        'progreso': int(avance / total) if total else 0,
        'busquedas': busquedas,
    }
