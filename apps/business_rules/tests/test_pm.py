"""
Pruebas de la Ponderación Media (PM).

Usan unittest estándar: esta capa no depende de Django.
"""

import unittest
from fractions import Fraction

from apps.business_rules.pm import calcular_pm


class PonderacionMediaTests(unittest.TestCase):

    def test_es_la_media_aritmetica(self):
        self.assertEqual(calcular_pm([4, 4, 3]), Fraction(11, 3))
        self.assertEqual(calcular_pm([1, 2, 3, 4]), Fraction(5, 2))

    def test_un_solo_subfactor(self):
        for valor in (1, 2, 3, 4):
            self.assertEqual(calcular_pm([valor]), valor)

    def test_no_se_cuenta_como_2(self):
        """'No sé' (2) entra al promedio como cualquier otra valoración."""
        self.assertEqual(calcular_pm([4, 2]), 3)

    def test_resultado_dentro_del_rango_1_a_4(self):
        self.assertEqual(calcular_pm([1, 1, 1]), 1)
        self.assertEqual(calcular_pm([4, 4, 4]), 4)

    def test_es_exacta_en_el_borde_del_umbral(self):
        self.assertEqual(calcular_pm([3, 3, 3]), 3)
        self.assertLess(calcular_pm([3, 3, 2]), 3)

    def test_acepta_cualquier_iterable(self):
        self.assertEqual(calcular_pm(v for v in (4, 2)), 3)
        self.assertEqual(calcular_pm((3, 3)), 3)

    def test_sin_valoraciones_falla(self):
        with self.assertRaises(ValueError):
            calcular_pm([])

    def test_rechaza_valoraciones_fuera_de_rango(self):
        for lista in ([0, 3], [3, 5], [-1]):
            with self.subTest(lista=lista):
                with self.assertRaises(ValueError):
                    calcular_pm(lista)

    def test_rechaza_valoraciones_que_no_son_enteros(self):
        for lista in ([3.0, 2], [3, "2"], [True, 2], [None]):
            with self.subTest(lista=lista):
                with self.assertRaises(TypeError):
                    calcular_pm(lista)


if __name__ == "__main__":
    unittest.main()
