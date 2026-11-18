"""
Pruebas de la clasificación FODA, incluida la validación contra el caso de
referencia (evaluación de LibreOffice con GUIOS PRO).

Usan unittest estándar: esta capa no depende de Django.
"""

import unittest
from fractions import Fraction

from apps.business_rules.foda import (
    AMENAZA, DEBILIDAD, EXTERNO, FORTALEZA, INTERNO, OPORTUNIDAD, clasificar_foda,
)

# (factor, PM mostrada, alcance, FODA) tal como aparecen en el caso de referencia.
CASO_LIBREOFFICE = [
    ("Compatibilidad", "3.8", EXTERNO, OPORTUNIDAD),
    ("Personalización", "1.7", EXTERNO, AMENAZA),
    ("Prueba", "3.0", EXTERNO, OPORTUNIDAD),
    ("Fiabilidad", "3.2", EXTERNO, OPORTUNIDAD),
    ("Reusabilidad", "3.0", EXTERNO, OPORTUNIDAD),
    ("Usabilidad", "3.5", EXTERNO, OPORTUNIDAD),
    ("Mantenibilidad", "4.0", EXTERNO, OPORTUNIDAD),
    ("Portabilidad", "2.0", EXTERNO, AMENAZA),
    ("Documentación", "2.4", EXTERNO, AMENAZA),
    ("Formación", "2.8", INTERNO, DEBILIDAD),
    ("Tiempo de adopción", "3.5", INTERNO, FORTALEZA),
    ("Casos de estudio de adopción FLOSS", "3.0", EXTERNO, OPORTUNIDAD),
    ("Centralidad de la tecnología de la información", "2.5", INTERNO, DEBILIDAD),
    ("Apoyo de la alta dirección", "4.0", INTERNO, FORTALEZA),
    ("Bloqueo de proveedores", "2.0", EXTERNO, AMENAZA),
    ("Soporte", "2.3", INTERNO, DEBILIDAD),
    ("Actitud hacia el cambio", "3.0", INTERNO, FORTALEZA),
    ("Coste total de propiedad", "3.5", INTERNO, FORTALEZA),
]


class ClasificacionFodaTests(unittest.TestCase):

    def test_las_cuatro_celdas_de_la_regla_foda(self):
        self.assertEqual(clasificar_foda(3.5, INTERNO), FORTALEZA)
        self.assertEqual(clasificar_foda(3.5, EXTERNO), OPORTUNIDAD)
        self.assertEqual(clasificar_foda(2.5, INTERNO), DEBILIDAD)
        self.assertEqual(clasificar_foda(2.5, EXTERNO), AMENAZA)

    def test_pm_igual_a_3_cuenta_como_alta(self):
        self.assertEqual(clasificar_foda(3, INTERNO), FORTALEZA)
        self.assertEqual(clasificar_foda(3, EXTERNO), OPORTUNIDAD)

    def test_pm_justo_por_debajo_de_3_cuenta_como_baja(self):
        self.assertEqual(clasificar_foda(Fraction(299, 100), INTERNO), DEBILIDAD)
        self.assertEqual(clasificar_foda(Fraction(299, 100), EXTERNO), AMENAZA)

    def test_limites_del_rango(self):
        self.assertEqual(clasificar_foda(1, INTERNO), DEBILIDAD)
        self.assertEqual(clasificar_foda(4, EXTERNO), OPORTUNIDAD)

    def test_soporte_cambia_segun_el_alcance_elegido(self):
        self.assertEqual(clasificar_foda(2.3, INTERNO), DEBILIDAD)
        self.assertEqual(clasificar_foda(2.3, EXTERNO), AMENAZA)

    def test_rechaza_alcance_invalido(self):
        for alcance in ("Interno", "otro", "", None):
            with self.subTest(alcance=alcance):
                with self.assertRaises(ValueError):
                    clasificar_foda(3, alcance)

    def test_rechaza_pm_fuera_de_rango(self):
        for pm in (0.9, 4.1, 0, 5):
            with self.subTest(pm=pm):
                with self.assertRaises(ValueError):
                    clasificar_foda(pm, INTERNO)

    def test_rechaza_pm_no_numerica(self):
        for pm in ("3", None, True):
            with self.subTest(pm=pm):
                with self.assertRaises(TypeError):
                    clasificar_foda(pm, INTERNO)


class CasoLibreOfficeTests(unittest.TestCase):

    def test_tiene_los_18_factores(self):
        self.assertEqual(len(CASO_LIBREOFFICE), 18)

    def test_los_18_factores_coinciden_con_el_caso_de_referencia(self):
        for factor, pm, alcance, esperado in CASO_LIBREOFFICE:
            with self.subTest(factor=factor):
                self.assertEqual(clasificar_foda(Fraction(pm), alcance), esperado)

    def test_conteo_por_categoria_segun_el_caso_de_referencia(self):
        """El caso de referencia describe 7 oportunidades, 4 fortalezas, 4 amenazas y 3 debilidades."""
        resultado = [clasificar_foda(Fraction(pm), alcance) for _, pm, alcance, _ in CASO_LIBREOFFICE]
        self.assertEqual(resultado.count(OPORTUNIDAD), 7)
        self.assertEqual(resultado.count(FORTALEZA), 4)
        self.assertEqual(resultado.count(AMENAZA), 4)
        self.assertEqual(resultado.count(DEBILIDAD), 3)


if __name__ == "__main__":
    unittest.main()
