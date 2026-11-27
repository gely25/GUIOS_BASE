"""
Recálculo de TC, IL e IS y versionado del catálogo (RF03, RF04, RF05, RF20).

    1. crear_borrador: copia la versión activa y recalcula con las publicaciones aprobadas.
    2. comparacion:    versión activa frente al borrador, factor por factor.
    3. publicar:       el borrador pasa a ACTIVO y la versión anterior a HISTORICO.

Las evaluaciones guardan su `catalogo_id`, así que conservan los indicadores con los
que se calcularon. Todo cálculo lo hace business_rules.rules_engine.
"""

from typing import List, NamedTuple, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.business_rules.rules_engine import EntradaFactor, recalcular_indicadores, tc_actualizado
from apps.data.models import CatalogoVersion
from apps.data.repositorios import bibliografia as repo_bib
from apps.data.repositorios import catalogo as repo

from .autorizacion import autorizar_administrador


def _nombre_nueva_version():
    base = f'v{repo.siguiente_numero_version()}-{timezone.localdate():%Y-%m-%d}'
    nombre, n = base, 2
    while not repo.nombre_disponible(nombre):
        nombre, n = f'{base}-{n}', n + 1
    return nombre


@transaction.atomic
def crear_borrador(actor_id):
    """Crea (o rehace) el borrador: TC = TC 2021 + aprobadas 2020-2025; luego r_i, IL e IS."""
    autorizar_administrador(actor_id)
    activa = repo.version_activa(bloquear=True)
    if activa is None:
        raise ValidationError('No hay versión activa del catálogo. '
                              'Solicite al equipo de soporte que cargue el catálogo.')
    anterior = repo.version_borrador(bloquear=True)
    if anterior is not None:
        repo.eliminar_borrador(anterior)

    indicadores = [i for i in repo.indicadores_de(activa) if i.factor.activo]
    aprobadas = repo_bib.aprobadas_por_factor()
    entradas = [
        EntradaFactor(
            clave=i.factor_id, ns=i.numero_subfactores,
            tc=tc_actualizado(i.total_citas_base, aprobadas.get(i.factor_id, 0)),
            ie=i.importancia_experto)
        for i in indicadores
    ]
    try:
        _, calculados = recalcular_indicadores(entradas)
    except (TypeError, ValueError) as error:
        raise ValidationError(f'No se pudo recalcular el catálogo: {error}') from error

    borrador = repo.crear_version(_nombre_nueva_version(), CatalogoVersion.BORRADOR, timezone.localdate())
    for i in indicadores:
        c = calculados[i.factor_id]
        repo.guardar_indicador(
            borrador, i.factor_id,
            numero_subfactores=c.ns, total_citas_base=i.total_citas_base, total_citas=c.tc,
            relacion_ri=c.relacion_ri, importancia_experto=c.ie,
            importancia_literatura=c.il, importancia_sugerida=c.is_)
    return borrador


@transaction.atomic
def publicar(actor_id):
    actor = autorizar_administrador(actor_id)
    borrador = repo.version_borrador(bloquear=True)
    if borrador is None:
        raise ValidationError('No hay un borrador para publicar. Recalcula primero.')
    activa = repo.version_activa(bloquear=True)
    if activa is not None:
        repo.cambiar_estado(activa, CatalogoVersion.HISTORICO)
    repo.cambiar_estado(borrador, CatalogoVersion.ACTIVO,
                        publicado_por=actor, fecha_publicacion=timezone.now())
    return borrador


@transaction.atomic
def descartar(actor_id):
    autorizar_administrador(actor_id)
    borrador = repo.version_borrador(bloquear=True)
    if borrador is not None:
        repo.eliminar_borrador(borrador)


class FilaComparacion(NamedTuple):
    factor: str
    dimension: str
    ns: int
    tc_base: int
    nuevas: Optional[int]
    tc_activa: Optional[int]
    tc_borrador: Optional[int]
    ri_activa: Optional[object]
    ri_borrador: Optional[object]
    il_activa: Optional[int]
    il_borrador: Optional[int]
    ie: Optional[int]
    is_activa: Optional[int]
    is_borrador: Optional[int]

    @property
    def cambia(self):
        return self.tc_borrador is not None and (
            self.il_activa != self.il_borrador or self.is_activa != self.is_borrador)


class Comparacion(NamedTuple):
    activa: Optional[CatalogoVersion]
    borrador: Optional[CatalogoVersion]
    filas: List[FilaComparacion]
    historial: list


def comparacion():
    activa, borrador = repo.version_activa(), repo.version_borrador()
    de_activa = {i.factor_id: i for i in repo.indicadores_de(activa)}
    de_borrador = {i.factor_id: i for i in repo.indicadores_de(borrador)}
    orden = list(de_borrador.values()) or list(de_activa.values())
    filas = []
    for ref in orden:
        a, b = de_activa.get(ref.factor_id), de_borrador.get(ref.factor_id)
        filas.append(FilaComparacion(
            factor=ref.factor.nombre, dimension=ref.factor.dimension.nombre,
            ns=ref.numero_subfactores, tc_base=ref.total_citas_base,
            nuevas=(b.total_citas - b.total_citas_base) if b else None,
            tc_activa=a.total_citas if a else None, tc_borrador=b.total_citas if b else None,
            ri_activa=a.relacion_ri if a else None, ri_borrador=b.relacion_ri if b else None,
            il_activa=a.importancia_literatura if a else None,
            il_borrador=b.importancia_literatura if b else None,
            ie=ref.importancia_experto,
            is_activa=a.importancia_sugerida if a else None,
            is_borrador=b.importancia_sugerida if b else None,
        ))
    return Comparacion(activa=activa, borrador=borrador, filas=filas, historial=repo.historial_versiones())
