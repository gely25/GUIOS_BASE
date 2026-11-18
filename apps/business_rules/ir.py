"""
Importancia Relativa (IR).

IR combina la Importancia del Decisor (ID) con la Importancia
Sugerida (IS) mediante la función discreta de GUIOS. Un factor con IR = 1
(Irrelevante) se excluye de la evaluación.

Python puro: no importa Django.
"""

from apps.business_rules.funcion_discreta import IRRELEVANTE, combinar_importancias


def calcular_ir(id_decisor: int, is_sugerida: int) -> int:
    """
    Calcula la IR (1 a 4) a partir de ID e IS (ambas entre 1 y 4).

    Ejemplos: ID 4 e IS 3 -> IR 3; ID 1 e IS 2 -> IR 1 (se excluye).
    """
    return combinar_importancias(id_decisor, is_sugerida)


def se_evalua(ir: int) -> bool:
    """Indica si el factor entra a la evaluación: todo IR distinto de 1."""
    return ir != IRRELEVANTE


def seleccionar_relevantes(irs: dict) -> dict:
    """
    Recibe {factor: IR} y devuelve solo los factores con IR distinto de 1,
    conservando el orden original.
    """
    return {factor: ir for factor, ir in irs.items() if se_evalua(ir)}

