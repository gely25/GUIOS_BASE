"""
Pruebas de indicadores_literatura/modelos.py (HU-03).

Los modelos son estructuras sin lógica: se comprueba su forma, que es el
contrato entre la fuente de datos, el servicio y la presentación.
"""

import unittest

from apps.application.services.indicadores_literatura import (
    FactorCatalogo,
    FilaIndicadores,
    IndicadoresLiteratura,
)


class ModelosTests(unittest.TestCase):

    def test_factor_catalogo_tiene_los_campos_de_entrada(self):
        self.assertEqual(FactorCatalogo._fields, ("nombre", "dimension", "ns", "tc", "ie"))

    def test_fila_indicadores_tiene_los_campos_a_mostrar(self):
        self.assertEqual(
            FilaIndicadores._fields,
            ("nombre", "dimension", "tc", "ns", "r", "il", "ie", "is_"),
        )

    def test_indicadores_literatura_agrupa_filas_cuartiles_y_origen(self):
        self.assertEqual(IndicadoresLiteratura._fields, ("filas", "cuartiles", "simulado"))

    def test_son_inmutables(self):
        factor = FactorCatalogo("A", "Dim", ns=1, tc=1, ie=3)
        with self.assertRaises(AttributeError):
            factor.tc = 2
