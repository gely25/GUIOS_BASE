"""
Reproduce la Tabla 5.3 de la tesis (Cap. 5, sección 5.2.3): dadas las citas
(TC) y el número de subfactores (NS) de los 18 factores, la IL y la IS deben
salir idénticas a las de la tesis.

NS viene del catálogo original (Guios-Floss/guiosad_data.csv).

TABLA_5_3 recoge las columnas TC, IL e IS de la tesis (Tabla 5.3, p. 88), una
fila por factor: (factor, TC, IL esperada, IS esperada). "TCO" de la tesis es
"Coste total de propiedad" en el catálogo.
"""

import unittest
from fractions import Fraction

from apps.business_rules.il import calcular_il_factores
from apps.business_rules.is_ import calcular_is

IE_ORIGINAL = 3  # Tabla 5.3: IE = 3 en los 18 factores

# Número de subfactores por factor, del catálogo original (61 en total).
NS_POR_FACTOR = {
    "Compatibilidad": 8,
    "Personalización": 6,
    "Prueba": 1,
    "Fiabilidad": 5,
    "Reusabilidad": 2,
    "Usabilidad": 4,
    "Mantenibilidad": 1,
    "Portabilidad": 2,
    "Documentación": 11,
    "Formación": 4,
    "Tiempo de adopción": 2,
    "Casos de estudio de adopción FLOSS": 1,
    "Centralidad de la tecnología de la información": 2,
    "Apoyo de la alta dirección": 1,
    "Bloqueo de proveedores": 1,
    "Soporte": 6,
    "Actitud hacia el cambio": 2,
    "Coste total de propiedad": 2,
}

# (factor, TC, IL esperada, IS esperada) -- Tabla 5.3 de la tesis.
TABLA_5_3 = [
    ("Compatibilidad", 33, 3, 3),
    ("Fiabilidad", 19, 3, 3),
    ("Mantenibilidad", 4, 3, 3),
    ("Personalización", 30, 4, 3),
    ("Prueba", 4, 3, 3),
    ("Documentación", 20, 1, 2),
    ("Portabilidad", 4, 2, 2),
    ("Reusabilidad", 5, 2, 2),
    ("Usabilidad", 14, 2, 2),
    ("Apoyo de la alta dirección", 5, 4, 3),
    ("Formación", 27, 4, 3),
    ("Soporte", 43, 4, 3),
    ("Actitud hacia el cambio", 3, 1, 2),
    ("Bloqueo de proveedores", 3, 2, 2),
    ("Casos de estudio de adopción FLOSS", 1, 1, 2),
    ("Centralidad de la tecnología de la información", 2, 1, 2),
    ("Tiempo de adopción", 2, 1, 2),
    ("Coste total de propiedad", 24, 4, 3),
]


class CatalogoTests(unittest.TestCase):

    def test_el_catalogo_tiene_18_factores_y_61_subfactores(self):
        self.assertEqual(len(NS_POR_FACTOR), 18)
        self.assertEqual(sum(NS_POR_FACTOR.values()), 61)


class Tabla53Tests(unittest.TestCase):

    @unittest.skipUnless(TABLA_5_3, "Falta completar TABLA_5_3 con las citas (TC) de la tesis.")
    def test_reproduce_il_e_is_de_los_18_factores(self):
        self.assertEqual({fila[0] for fila in TABLA_5_3}, set(NS_POR_FACTOR))

        entrada = {factor: (tc, NS_POR_FACTOR[factor]) for factor, tc, _, _ in TABLA_5_3}
        cuartiles, resultados = calcular_il_factores(entrada)

        for factor, tc, il_esperada, is_esperada in TABLA_5_3:
            with self.subTest(factor=factor):
                self.assertEqual(resultados[factor].r, Fraction(tc, NS_POR_FACTOR[factor]))
                self.assertEqual(resultados[factor].il, il_esperada)
                self.assertEqual(calcular_is(IE_ORIGINAL, resultados[factor].il), is_esperada)
