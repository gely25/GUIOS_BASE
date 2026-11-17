"""
Pruebas de la función discreta de GUIOS y de la Importancia Sugerida (IS).

Usan unittest estándar: esta capa no depende de Django.
"""

import math
import unittest

from apps.business_rules.funcion_discreta import combinar_importancias
from apps.business_rules.is_ import calcular_is


class FuncionDiscretaTests(unittest.TestCase):

    def test_matriz_completa_coincide_con_la_formula_del_prototipo(self):
        """
        Las 16 celdas de la matriz 4x4 (Figura 5.10 de la tesis) equivalen a
        floor((posicion_a + posicion_b) / 2) con posiciones 0 a 3, que es la
        assigment_function de Guios-Floss/guiosad.py.
        """
        for a in range(1, 5):
            for b in range(1, 5):
                esperado = math.floor(((a - 1) + (b - 1)) / 2) + 1
                with self.subTest(a=a, b=b):
                    self.assertEqual(combinar_importancias(a, b), esperado)

    def test_es_simetrica(self):
        for a in range(1, 5):
            for b in range(1, 5):
                self.assertEqual(combinar_importancias(a, b), combinar_importancias(b, a))

    def test_redondea_hacia_abajo(self):
        self.assertEqual(combinar_importancias(1, 2), 1)  # 1.5 -> 1
        self.assertEqual(combinar_importancias(2, 3), 2)  # 2.5 -> 2
        self.assertEqual(combinar_importancias(3, 4), 3)  # 3.5 -> 3

    def test_rechaza_niveles_fuera_de_rango(self):
        for a, b in [(0, 3), (3, 5), (-1, 2)]:
            with self.subTest(a=a, b=b):
                with self.assertRaises(ValueError):
                    combinar_importancias(a, b)

    def test_rechaza_valores_que_no_son_enteros(self):
        for a, b in [(3.0, 2), (3, "2"), (True, 2), (None, 2)]:
            with self.subTest(a=a, b=b):
                with self.assertRaises(TypeError):
                    combinar_importancias(a, b)


class ImportanciaSugeridaTests(unittest.TestCase):

    def test_ejemplos_de_la_tesis_con_ie_3(self):
        """IE = 3 en los 18 factores: IL 4 -> IS 3 e IL 1 -> IS 2."""
        self.assertEqual(calcular_is(3, 4), 3)
        self.assertEqual(calcular_is(3, 1), 2)

    def test_ie_3_para_todas_las_il(self):
        esperado = {1: 2, 2: 2, 3: 3, 4: 3}
        for il, es in esperado.items():
            with self.subTest(il=il):
                self.assertEqual(calcular_is(3, il), es)
