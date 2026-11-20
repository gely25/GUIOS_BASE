"""
Fuente de datos real del catálogo para los indicadores de literatura (HU-03).

Capa: application. Hace lo mismo que `cargar_datos_catalogo` (fuente simulada),
pero lee de PostgreSQL: la versión ACTIVA del catálogo (NS e IE) y el TC que
dejó la actualización bibliográfica (HU02).

Regla del TC: si ya hay publicaciones relacionadas con factores en el periodo,
el TC de TODOS los factores sale de esas publicaciones (0 si un factor no tiene).
Si todavía no se ha hecho ninguna actualización, se usa el `total_citas`
guardado en el catálogo. Así nunca se mezclan dos escalas en un mismo cálculo.
"""

from typing import List, Sequence

from apps.application.services.actualizacion_bibliografica import total_citas_por_factor
from apps.data.models.catalogo import CatalogoVersion, IndicadorFactor

from .modelos import FactorCatalogo


def cargar_datos_catalogo_bd(anio_inicio: int = 2020, anio_fin: int = 2025) -> Sequence[FactorCatalogo]:
    """
    Factores de la versión activa del catálogo con su NS, TC e IE.

    Lanza ValueError si no hay versión activa, si no tiene indicadores o si a
    algún factor le falta la Importancia del Experto.
    """
    version = (
        CatalogoVersion.objects.filter(estado="ACTIVO").order_by("-fecha_creacion", "-catalogo_id").first()
    )
    if version is None:
        raise ValueError("No hay una versión activa del catálogo metodológico.")

    indicadores = list(
        IndicadorFactor.objects
        .filter(catalogo=version, factor__activo=True)
        .select_related("factor__dimension")
        .order_by("factor__dimension_id", "factor_id")
    )
    if not indicadores:
        raise ValueError(f"La versión {version.version} del catálogo no tiene indicadores por factor.")

    tc_publicaciones = total_citas_por_factor(anio_inicio, anio_fin)
    usar_publicaciones = bool(tc_publicaciones)

    factores: List[FactorCatalogo] = []
    for ind in indicadores:
        if ind.importancia_experto is None:
            raise ValueError(f"El factor «{ind.factor.nombre}» no tiene Importancia del Experto (IE).")
        tc = tc_publicaciones.get(ind.factor_id, 0) if usar_publicaciones else (ind.total_citas or 0)
        factores.append(
            FactorCatalogo(
                nombre=ind.factor.nombre,
                dimension=ind.factor.dimension.nombre,
                ns=ind.numero_subfactores,
                tc=tc,
                ie=ind.importancia_experto,
            )
        )
    return factores
