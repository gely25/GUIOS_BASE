"""
Servicio de indicadores de literatura (HU-03).

Capa: application. Orquesta las reglas de apps/business_rules para calcular,
por factor, r = TC / NS, la Importancia de la Literatura (IL, por cuartiles) y
la Importancia Sugerida (IS = f(IE, IL)). No contiene datos fijos: trabaja con
los factores que le entregue la fuente.
"""

from typing import Callable, Dict, Sequence, Tuple

from apps.business_rules.il import calcular_il_factores
from apps.business_rules.is_ import calcular_is

from .fuente_simulada import cargar_datos_catalogo
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
    return IndicadoresLiteratura(filas=filas, cuartiles=cuartiles, simulado=False)


def obtener_indicadores_literatura(
    fuente: Callable[[], Sequence[FactorCatalogo]] = cargar_datos_catalogo,
) -> IndicadoresLiteratura:
    """
    Caso de uso completo: obtiene los datos de la `fuente` y calcula los
    indicadores. Por defecto usa la fuente simulada y marca el resultado como
    simulado; las pruebas pueden inyectar otra fuente.
    """
    resultado = calcular_indicadores_literatura(fuente())
    return resultado._replace(simulado=fuente is cargar_datos_catalogo)
