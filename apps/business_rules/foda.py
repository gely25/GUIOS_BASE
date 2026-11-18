"""
Clasificación FODA de un factor (ecuación 5.3 de la tesis).

    Fortaleza     si PM >= 3 y el alcance es interno
    Oportunidad   si PM >= 3 y el alcance es externo
    Debilidad     si PM <  3 y el alcance es interno
    Amenaza       si PM <  3 y el alcance es externo

El alcance de cada factor viene del catálogo (Tabla 5.4). Solo el factor Soporte
puede ser interno o externo: el decisor elige uno y ese valor se recibe aquí.

Python puro: no importa Django.
"""

from fractions import Fraction

INTERNO = "interno"
EXTERNO = "externo"

FORTALEZA = "Fortaleza"
OPORTUNIDAD = "Oportunidad"
DEBILIDAD = "Debilidad"
AMENAZA = "Amenaza"

UMBRAL_PM = 3


def clasificar_foda(pm, alcance: str) -> str:
    """Clasifica un factor como Fortaleza, Oportunidad, Debilidad o Amenaza."""
    if isinstance(pm, bool) or not isinstance(pm, (int, float, Fraction)):
        raise TypeError(f"La PM debe ser numérica, se recibió {pm!r}.")
    if not 1 <= pm <= 4:
        raise ValueError(f"La PM debe estar entre 1 y 4, se recibió {pm}.")
    if alcance not in (INTERNO, EXTERNO):
        raise ValueError(f"El alcance debe ser 'interno' o 'externo', se recibió {alcance!r}.")

    alta = pm >= UMBRAL_PM
    if alcance == INTERNO:
        return FORTALEZA if alta else DEBILIDAD
    return OPORTUNIDAD if alta else AMENAZA
