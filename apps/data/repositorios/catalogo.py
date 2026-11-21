"""
Consultas del catálogo versionado (HU02 / HU03).
"""

from apps.data.models import CatalogoVersion, IndicadorFactor


def version_activa(bloquear=False):
    consulta = CatalogoVersion.objects.filter(estado=CatalogoVersion.ACTIVO)
    if bloquear:
        consulta = consulta.select_for_update()
    return consulta.first()


def version_borrador(bloquear=False):
    consulta = CatalogoVersion.objects.filter(estado=CatalogoVersion.BORRADOR)
    if bloquear:
        consulta = consulta.select_for_update()
    return consulta.first()


def historial_versiones():
    return list(CatalogoVersion.objects.select_related('publicado_por').order_by('-catalogo_id'))


def indicadores_de(version):
    """Indicadores de una versión con su factor y dimensión, en el orden del catálogo."""
    if version is None:
        return []
    return list(
        IndicadorFactor.objects.filter(catalogo=version)
        .select_related('factor', 'factor__dimension')
        .order_by('factor__dimension_id', 'factor_id'))


def factores_de(version, solo_activos=True):
    factores = [i.factor for i in indicadores_de(version)]
    return [f for f in factores if f.activo] if solo_activos else factores


def crear_version(nombre, estado, fecha):
    return CatalogoVersion.objects.create(version=nombre, estado=estado, fecha_creacion=fecha)


def siguiente_numero_version():
    return CatalogoVersion.objects.count() + 1


def nombre_disponible(nombre):
    return not CatalogoVersion.objects.filter(version=nombre).exists()


def guardar_indicador(version, factor_id, **valores):
    IndicadorFactor.objects.update_or_create(catalogo=version, factor_id=factor_id, defaults=valores)


def eliminar_borrador(version):
    IndicadorFactor.objects.filter(catalogo=version).delete()
    version.delete()


def cambiar_estado(version, estado, **campos):
    version.estado = estado
    for nombre, valor in campos.items():
        setattr(version, nombre, valor)
    version.save(update_fields=['estado', *campos])
