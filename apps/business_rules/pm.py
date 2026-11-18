"""
Ponderación Media del factor (PM).

La PM es la media aritmética de las valoraciones confirmadas de los subfactores
de un factor relevante (IR distinto de 1). Cada valoración usa la escala de GUIOS:

    1 = No cumple el requisito
    2 = No sé
    3 = Cumple parcialmente el requisito
    4 = Cumple el requisito

El resultado está en el rango [1, 4]. Se devuelve como Fraction para que la
comparación con el umbral del FODA (PM >= 3) sea exacta; usa float(pm) para mostrarla.

Python puro: no importa Django.
"""

from fractions import Fraction

NO_CUMPLE = 1
NO_SE = 2
CUMPLE_PARCIALMENTE = 3
CUMPLE = 4

VALORACIONES_VALIDAS = (NO_CUMPLE, NO_SE, CUMPLE_PARCIALMENTE, CUMPLE)


def calcular_pm(valoraciones) -> Fraction:
    """
    Calcula la PM a partir de las valoraciones (1 a 4) de los subfactores del factor.

    Ejemplo: [4, 4, 3] -> 11/3 (3,67).
    """
    valoraciones = list(valoraciones)
    if not valoraciones:
        raise ValueError("Se necesita al menos una valoración para calcular la PM.")
    for valor in valoraciones:
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise TypeError(f"La valoración debe ser un entero, se recibió {valor!r}.")
        if valor not in VALORACIONES_VALIDAS:
            raise ValueError(f"La valoración debe estar entre 1 y 4, se recibió {valor}.")
    return Fraction(sum(valoraciones), len(valoraciones))
