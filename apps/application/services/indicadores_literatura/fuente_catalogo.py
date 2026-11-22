"""
Fuente de datos de los indicadores de literatura (HU-03): la versión ACTIVA del catálogo.

Capa: application. Es el ÚNICO punto que sabe de dónde salen los datos. El TC ya
incluye las publicaciones aprobadas en la actualización bibliográfica (HU02).
"""

from typing import Optional, Sequence, Tuple

from apps.data.repositorios import catalogo as repo

from .modelos import FactorCatalogo


def cargar_datos_catalogo() -> Tuple[Optional[str], Sequence[FactorCatalogo]]:
    """(nombre de la versión activa, factores activos con su NS, TC e IE). Sin versión: (None, [])."""
    version = repo.version_activa()
    factores = [
        FactorCatalogo(
            nombre=i.factor.nombre,
            dimension=i.factor.dimension.nombre,
            ns=i.numero_subfactores,
            tc=i.total_citas or 0,
            ie=i.importancia_experto,
        )
        for i in repo.indicadores_de(version)
        if i.factor.activo
    ]
    return (version.version if version else None), factores
