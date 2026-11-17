"""
Función discreta de GUIOS para combinar dos importancias (escala 1 a 4).

Es la misma regla de `assigment_function` del prototipo original
(Guios-Floss/guiosad.py): se suman las posiciones de ambos niveles y se divide
entre 2 redondeando hacia abajo.

    Irrelevante = 1, Opcional = 2, Importante = 3, Fundamental = 4

Con posiciones 0 a 3, floor((pos_a + pos_b) / 2) es lo mismo que
(a + b) // 2 con valores 1 a 4, porque el desplazamiento se compensa.

Se reutiliza para IS = f(IE, IL) y para IR = f(IS, ID).

Python puro: no importa Django.
"""

IRRELEVANTE = 1
OPCIONAL = 2
IMPORTANTE = 3
FUNDAMENTAL = 4

ETIQUETAS = {
    IRRELEVANTE: "Irrelevante",
    OPCIONAL: "Opcional",
    IMPORTANTE: "Importante",
    FUNDAMENTAL: "Fundamental",
}


def _validar_nivel(valor, nombre):
    """Comprueba que el nivel sea un entero entre 1 y 4 (sin booleanos)."""
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError(f"{nombre} debe ser un entero, se recibió {valor!r}.")
    if valor not in ETIQUETAS:
        raise ValueError(f"{nombre} debe estar entre 1 y 4, se recibió {valor}.")


def combinar_importancias(a: int, b: int) -> int:
    """Combina dos importancias (1 a 4) y devuelve el nivel resultante (1 a 4)."""
    _validar_nivel(a, "Importancia")
    _validar_nivel(b, "Importancia")
    return (a + b) // 2
