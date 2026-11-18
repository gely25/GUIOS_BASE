"""
Pruebas de la Importancia Relativa (IR) y de la exclusión de factores con IR = 1.

Usan unittest estándar: esta capa no depende de Django.
"""

import unittest

from apps.business_rules.funcion_discreta import combinar_importancias
from apps.business_rules.ir import calcular_ir, se_evalua, seleccionar_relevantes


class ImportanciaRelativaTests(unittest.TestCase):

    def test_usa_la_funcion_discreta_en_las_16_combinaciones(self):
        for id_ in range(1, 5):
            for is_ in range(1, 5):
                with self.subTest(id=id_, is_=is_):
                    self.assertEqual(calcular_ir(id_, is_), combinar_importancias(id_, is_))

    def test_ejemplos(self):
        self.assertEqual(calcular_ir(4, 3), 3)
        self.assertEqual(calcular_ir(3, 3), 3)
        self.assertEqual(calcular_ir(2, 2), 2)
        self.assertEqual(calcular_ir(1, 2), 1)

    def test_es_simetrica(self):
        for id_ in range(1, 5):
            for is_ in range(1, 5):
                self.assertEqual(calcular_ir(id_, is_), calcular_ir(is_, id_))

    def test_rechaza_niveles_invalidos(self):
        with self.assertRaises(ValueError):
            calcular_ir(0, 3)
        with self.assertRaises(ValueError):
            calcular_ir(3, 5)
        with self.assertRaises(TypeError):
            calcular_ir(3.0, 2)


class ExclusionIrUnoTests(unittest.TestCase):

    def test_ir_1_no_se_evalua(self):
        self.assertFalse(se_evalua(1))

    def test_ir_2_3_4_si_se_evaluan(self):
        for ir in (2, 3, 4):
            self.assertTrue(se_evalua(ir))

    def test_seleccionar_relevantes_quita_solo_ir_1_y_conserva_el_orden(self):
        irs = {"Compatibilidad": 2, "Prueba": 1, "Fiabilidad": 3, "Soporte": 4, "Otro": 1}
        self.assertEqual(
            list(seleccionar_relevantes(irs).items()),
            [("Compatibilidad", 2), ("Fiabilidad", 3), ("Soporte", 4)],
        )

    def test_seleccionar_relevantes_con_todo_irrelevante_devuelve_vacio(self):
        self.assertEqual(seleccionar_relevantes({"A": 1, "B": 1}), {})

    def test_no_modifica_el_diccionario_original(self):
        irs = {"A": 1, "B": 3}
        seleccionar_relevantes(irs)
        self.assertEqual(irs, {"A": 1, "B": 3})


if __name__ == "__main__":
    unittest.main()
