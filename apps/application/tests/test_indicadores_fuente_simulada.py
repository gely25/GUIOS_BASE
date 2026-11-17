"""
Pruebas de indicadores_literatura/fuente_simulada.py (HU-03).

Los datos simulados deben reproducir el catálogo original de 2021.
"""

import unittest

from apps.application.services.indicadores_literatura import FactorCatalogo
from apps.application.services.indicadores_literatura.fuente_simulada import cargar_datos_catalogo


class FuenteSimuladaTests(unittest.TestCase):

    def test_tiene_18_factores_61_subfactores_e_ie_3(self):
        factores = cargar_datos_catalogo()
        self.assertEqual(len(factores), 18)
        self.assertEqual(sum(f.ns for f in factores), 61)
        self.assertEqual({f.ie for f in factores}, {3})

    def test_entrega_factores_catalogo_con_nombres_unicos(self):
        factores = cargar_datos_catalogo()
        self.assertTrue(all(isinstance(f, FactorCatalogo) for f in factores))
        self.assertEqual(len({f.nombre for f in factores}), len(factores))

    def test_cubre_las_tres_dimensiones_del_modelo_original(self):
        dimensiones = {f.dimension for f in cargar_datos_catalogo()}
        self.assertEqual(dimensiones, {"Tecnológica", "Organizacional", "Económica"})
