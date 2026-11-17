"""
Importancia de la Literatura (IL): reglas de cálculo.

Python puro: este módulo no importa Django ni usa base de datos.

Flujo de HU-03:
    1. r = TC / NS por factor                       -> calcular_relacion_r
    2. cuartiles del conjunto de r de todos los
       factores (percentil lineal, como QUARTILE.INC
       de Excel; rq4 = máximo)                      -> calcular_cuartiles
    3. IL = 1..4 según en qué tramo cae cada r       -> asignar_il
    Los tres pasos juntos para un catálogo completo  -> calcular_il_factores

Los cuartiles y las comparaciones se calculan con fracciones exactas
(fractions.Fraction) para que un r igual a un límite caiga siempre del mismo
lado, sin depender de errores de punto flotante.
"""

from fractions import Fraction
from typing import Dict, Iterable, List, NamedTuple, Tuple


def _validar_entero(valor, nombre):
    """Comprueba que el valor sea un entero (y no un booleano ni un decimal)."""
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError(f"{nombre} debe ser un entero, se recibió {valor!r}.")


def _validar_tc_ns(tc, ns):
    """Valida TC (>= 0) y NS (> 0) como enteros."""
    _validar_entero(tc, "TC")
    _validar_entero(ns, "NS")

    if tc < 0:
        raise ValueError(f"TC no puede ser negativo, se recibió {tc}.")
    if ns <= 0:
        raise ValueError(f"NS debe ser mayor que 0, se recibió {ns}.")


def calcular_relacion_r(tc: int, ns: int) -> float:
    """
    Calcula la relación r = TC / NS de un factor.

    TC: total de referencias asociadas al factor (puede ser 0).
    NS: número de subfactores del catálogo original (debe ser mayor que 0).

    Devuelve el cociente exacto, sin redondear.
    """
    _validar_tc_ns(tc, ns)

    return tc / ns


# ---------------------------------------------------------------------------
# Cuartiles
# ---------------------------------------------------------------------------

class Cuartiles(NamedTuple):
    """Límites superiores (inclusivos) de cada tramo de IL."""

    rq1: Fraction
    rq2: Fraction
    rq3: Fraction
    rq4: Fraction


def _como_fraccion(r, nombre="r"):
    """Convierte un número no negativo (int, float o Fraction) a Fraction."""
    if isinstance(r, bool) or not isinstance(r, (int, float, Fraction)):
        raise TypeError(f"{nombre} debe ser un número, se recibió {r!r}.")
    r = Fraction(r)
    if r < 0:
        raise ValueError(f"{nombre} no puede ser negativo, se recibió {r}.")
    return r


def _percentil_lineal(ordenados: List[Fraction], p: Fraction) -> Fraction:
    """
    Percentil p (entre 0 y 1) con interpolación lineal sobre una lista ya
    ordenada. Es el método de numpy (por defecto) y de QUARTILE.INC de Excel:
    posición = p * (n - 1).
    """
    posicion = p * (len(ordenados) - 1)
    inferior = int(posicion)  # parte entera (posicion >= 0)
    fraccion = posicion - inferior
    if fraccion == 0:
        return ordenados[inferior]
    return ordenados[inferior] + fraccion * (ordenados[inferior + 1] - ordenados[inferior])


def calcular_cuartiles(relaciones: Iterable) -> Cuartiles:
    """
    Calcula rq1, rq2, rq3 y rq4 del conjunto de relaciones r de todos los
    factores.

    rq1, rq2, rq3: percentiles 25, 50 y 75 (interpolación lineal).
    rq4: el valor máximo.

    Acepta int, float o Fraction. Para no perder exactitud conviene pasar
    Fraction (calcular_il_factores ya lo hace). Devuelve fracciones exactas,
    sin redondear.
    """
    ordenados = sorted(_como_fraccion(r) for r in relaciones)

    if len(ordenados) < 2:
        raise ValueError("Se necesitan al menos 2 relaciones para calcular cuartiles.")

    return Cuartiles(
        rq1=_percentil_lineal(ordenados, Fraction(1, 4)),
        rq2=_percentil_lineal(ordenados, Fraction(1, 2)),
        rq3=_percentil_lineal(ordenados, Fraction(3, 4)),
        rq4=ordenados[-1],
    )


def asignar_il(r, cuartiles: Cuartiles) -> int:
    """
    Asigna la Importancia de la Literatura (1 a 4) a una relación r.

    Cortes inclusivos por arriba:
        IL = 1 si r <= rq1
        IL = 2 si rq1 < r <= rq2
        IL = 3 si rq2 < r <= rq3
        IL = 4 si rq3 < r <= rq4

    Un r igual a un límite queda en el tramo inferior. Si r supera rq4 no
    pertenece al conjunto con el que se calcularon los cuartiles y se rechaza.
    """
    r = _como_fraccion(r)

    if r <= cuartiles.rq1:
        return 1
    if r <= cuartiles.rq2:
        return 2
    if r <= cuartiles.rq3:
        return 3
    if r <= cuartiles.rq4:
        return 4
    raise ValueError(f"r={r} es mayor que rq4={cuartiles.rq4}; no está en el conjunto de factores.")


# ---------------------------------------------------------------------------
# IL de un catálogo completo
# ---------------------------------------------------------------------------

class ResultadoIL(NamedTuple):
    """Resultado por factor, con todo lo necesario para explicar el cálculo."""

    tc: int
    ns: int
    r: Fraction
    il: int


def calcular_il_factores(
    factores: Dict[str, Tuple[int, int]],
) -> Tuple[Cuartiles, Dict[str, ResultadoIL]]:
    """
    Calcula la IL de todos los factores a la vez.

    factores: {nombre_del_factor: (TC, NS)}.

    Devuelve (cuartiles, resultados) donde resultados[nombre] es un
    ResultadoIL(tc, ns, r, il). Los cuartiles dependen del conjunto completo,
    por eso no se puede calcular la IL de un factor suelto.
    """
    if len(factores) < 2:
        raise ValueError("Se necesitan al menos 2 factores para calcular cuartiles.")

    relaciones = {}
    for nombre, (tc, ns) in factores.items():
        _validar_tc_ns(tc, ns)
        relaciones[nombre] = Fraction(tc, ns)

    cuartiles = calcular_cuartiles(relaciones.values())

    resultados = {
        nombre: ResultadoIL(
            tc=factores[nombre][0],
            ns=factores[nombre][1],
            r=r,
            il=asignar_il(r, cuartiles),
        )
        for nombre, r in relaciones.items()
    }
    return cuartiles, resultados
