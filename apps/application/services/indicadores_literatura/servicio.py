"""
Servicio de indicadores de literatura (HU-03).

Capa: application. Orquesta las reglas de apps/business_rules para calcular,
por factor, r = TC / NS, la Importancia de la Literatura (IL, por cuartiles) y
la Importancia Sugerida (IS = f(IE, IL)). No contiene datos fijos: trabaja con
los factores que le entregue la fuente.
"""

from typing import Callable, Dict, Optional, Sequence, Tuple

from apps.business_rules.il import calcular_il_factores
from apps.business_rules.is_ import calcular_is

from .fuente_catalogo import cargar_datos_catalogo
from .modelos import FactorCatalogo, FilaIndicadores, IndicadoresLiteratura


def calcular_indicadores_literatura(factores: Sequence[FactorCatalogo]) -> IndicadoresLiteratura:
    """
    Calcula r, IL e IS de todos los factores recibidos, en el mismo orden.

    Lanza ValueError si hay nombres de factor repetidos o si las reglas de
    negocio rechazan algún dato (por ejemplo, NS = 0).
    """
    entrada: Dict[str, Tuple[int, int]] = {f.nombre: (f.tc, f.ns) for f in factores}
    if len(entrada) != len(factores):
        raise ValueError("Hay nombres de factor repetidos en el catálogo.")

    cuartiles, resultados = calcular_il_factores(entrada)

    filas = [
        FilaIndicadores(
            nombre=f.nombre,
            dimension=f.dimension,
            tc=f.tc,
            ns=f.ns,
            r=float(resultados[f.nombre].r),
            il=resultados[f.nombre].il,
            ie=f.ie,
            is_=calcular_is(f.ie, resultados[f.nombre].il),
        )
        for f in factores
    ]
    return IndicadoresLiteratura(filas=filas, cuartiles=cuartiles, version=None)


def obtener_indicadores_literatura(
    fuente: Optional[Callable[[], Sequence[FactorCatalogo]]] = None,
) -> Optional[IndicadoresLiteratura]:
    """
    Caso de uso completo: obtiene los factores y calcula los indicadores.

    Sin `fuente` usa la versión activa del catálogo en PostgreSQL y devuelve None si
    todavía no hay catálogo cargado. Las pruebas pueden inyectar otra fuente.
    """
    if fuente is not None:
        return calcular_indicadores_literatura(fuente())
    version, factores = cargar_datos_catalogo()
    if not factores:
        return None
    return calcular_indicadores_literatura(factores)._replace(version=version)
