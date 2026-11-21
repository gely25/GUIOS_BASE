"""
Modelos de datos de los indicadores de literatura (HU-03).

Capa: application. Solo define las estructuras que viajan entre la fuente de
datos, el servicio y la presentación; no contiene lógica.
"""

from typing import List, NamedTuple, Optional

from apps.business_rules.il import Cuartiles


class FactorCatalogo(NamedTuple):
    """Datos de entrada de un factor: lo que la fuente de datos debe entregar."""

    nombre: str
    dimension: str
    ns: int  # número de subfactores del catálogo
    tc: int  # total de citas: TC GUIOS 2021 + publicaciones aprobadas (HU02)
    ie: int  # Importancia del Experto (valor fijo del modelo original)


class FilaIndicadores(NamedTuple):
    """Resultado por factor, listo para mostrarse."""

    nombre: str
    dimension: str
    tc: int
    ns: int
    r: float
    il: int
    ie: int
    is_: int


class IndicadoresLiteratura(NamedTuple):
    """Resultado completo: filas por factor, cuartiles usados y versión del catálogo (None si la fuente es otra)."""

    filas: List[FilaIndicadores]
    cuartiles: Cuartiles
    version: Optional[str]
