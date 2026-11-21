"""
RulesEngine de la actualización bibliográfica (HU02): TC, r_i, IL e IS.

Python puro y determinista: no importa Django ni toca la base de datos. Reutiliza
las reglas ya validadas contra el caso de referencia (il.py, is_.py).

    TC   = TC de GUIOS 2021 + publicaciones nuevas aprobadas (2020-2025)
    r_i  = TC / NS
    IL   = cuartil de r_i dentro de todos los factores del catálogo (1..4)
    IS   = función discreta(IE, IL)
"""

from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Dict, Hashable, NamedTuple, Sequence, Tuple

from apps.business_rules.il import Cuartiles, calcular_il_factores
from apps.business_rules.is_ import calcular_is

ANIO_INICIO = 2020
ANIO_FIN = 2025

_CUATRO_DECIMALES = Decimal('0.0001')


class EntradaFactor(NamedTuple):
    """Datos de un factor para recalcular: clave (cualquier identificador), NS, TC e IE."""

    clave: Hashable
    ns: int
    tc: int
    ie: int


class IndicadoresFactor(NamedTuple):
    tc: int
    ns: int
    r: Fraction          # exacto: es el que decide el cuartil
    relacion_ri: Decimal  # r redondeado a 4 decimales para guardar en indicador_factor
    il: int
    ie: int
    is_: int


def tc_actualizado(tc_base: int, nuevas: int) -> int:
    """TC de una versión: el TC de GUIOS 2021 más las publicaciones nuevas aprobadas."""
    for valor, nombre in ((tc_base, 'TC base'), (nuevas, 'Publicaciones nuevas')):
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise TypeError(f'{nombre} debe ser un entero, se recibió {valor!r}.')
        if valor < 0:
            raise ValueError(f'{nombre} no puede ser negativo, se recibió {valor}.')
    return tc_base + nuevas


def redondear_ri(r: Fraction) -> Decimal:
    """r_i con 4 decimales (NUMERIC(10,4)), redondeo comercial."""
    return (Decimal(r.numerator) / Decimal(r.denominator)).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)


def recalcular_indicadores(
    factores: Sequence[EntradaFactor],
) -> Tuple[Cuartiles, Dict[Hashable, IndicadoresFactor]]:
    """
    Recalcula r_i, IL e IS de todo el catálogo a la vez (los cuartiles dependen del conjunto).

    Lanza ValueError si hay claves repetidas, menos de 2 factores o algún NS = 0.
    """
    entrada = {f.clave: (f.tc, f.ns) for f in factores}
    if len(entrada) != len(factores):
        raise ValueError('Hay factores repetidos en el catálogo.')

    cuartiles, resultados = calcular_il_factores(entrada)
    return cuartiles, {
        f.clave: IndicadoresFactor(
            tc=f.tc,
            ns=f.ns,
            r=resultados[f.clave].r,
            relacion_ri=redondear_ri(resultados[f.clave].r),
            il=resultados[f.clave].il,
            ie=f.ie,
            is_=calcular_is(f.ie, resultados[f.clave].il),
        )
        for f in factores
    }


def anio_en_periodo(anio) -> bool:
    """La publicación cuenta solo si su año está entre 2020 y 2025."""
    return isinstance(anio, int) and not isinstance(anio, bool) and ANIO_INICIO <= anio <= ANIO_FIN
