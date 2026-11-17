"""
Importancia Sugerida (IS).

IS combina la Importancia del Experto (IE, valor fijo del modelo original) con
la Importancia de la Literatura (IL) mediante la función discreta de GUIOS.

Python puro: no importa Django.
"""

from apps.business_rules.funcion_discreta import combinar_importancias


def calcular_is(ie: int, il: int) -> int:
    """
    Calcula la IS (1 a 4) a partir de IE e IL (ambas entre 1 y 4).

    Ejemplos con IE = 3: IL = 4 -> IS 3; IL = 1 -> IS 2.
    """
    return combinar_importancias(ie, il)
