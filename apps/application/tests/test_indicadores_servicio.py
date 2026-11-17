"""
Pruebas de indicadores_literatura/servicio.py (HU-03).

Se inyectan fuentes pequeñas para comprobar que el servicio no depende de un
catálogo fijo.
"""

import unittest
from fractions import Fraction

from apps.application.services.indicadores_literatura import (
    FactorCatalogo,
    calcular_indicadores_literatura,
    obtener_indicadores_literatura,
)


def _fuente_pequena():
    # r = 0, 1, 2 y 4 -> cuartiles 0.75 / 1.5 / 2.5 / 4 -> IL 1, 2, 3, 4
    return [
        FactorCatalogo("A", "Dim 1", ns=5, tc=0, ie=3),
        FactorCatalogo("B", "Dim 1", ns=4, tc=4, ie=3),
        FactorCatalogo("C", "Dim 2", ns=3, tc=6, ie=3),
        FactorCatalogo("D", "Dim 3", ns=4, tc=16, ie=3),
    ]


class CalcularIndicadoresTests(unittest.TestCase):

    def test_calcula_r_il_e_is_por_factor(self):
        resultado = calcular_indicadores_literatura(_fuente_pequena())
        por_nombre = {f.nombre: f for f in resultado.filas}

        self.assertEqual([por_nombre[n].il for n in "ABCD"], [1, 2, 3, 4])
        self.assertEqual([por_nombre[n].ie for n in "ABCD"], [3, 3, 3, 3])
        self.assertEqual([por_nombre[n].is_ for n in "ABCD"], [2, 2, 3, 3])  # IE = 3
        self.assertEqual([por_nombre[n].r for n in "ABCD"], [0.0, 1.0, 2.0, 4.0])
        self.assertEqual(resultado.cuartiles.rq1, Fraction(3, 4))

    def test_fila_indicadores_expone_ie_del_catalogo(self):
        fuente = [
            FactorCatalogo("Fact1", "Dim 1", ns=2, tc=4, ie=2),
            FactorCatalogo("Fact2", "Dim 2", ns=4, tc=8, ie=4),
        ]
        por_nombre = {f.nombre: f for f in calcular_indicadores_literatura(fuente).filas}
        self.assertEqual(por_nombre["Fact1"].ie, 2)
        self.assertEqual(por_nombre["Fact2"].ie, 4)

    def test_conserva_el_orden_y_la_dimension_recibidos(self):
        resultado = calcular_indicadores_literatura(_fuente_pequena())
        self.assertEqual([f.nombre for f in resultado.filas], ["A", "B", "C", "D"])
        self.assertEqual([f.dimension for f in resultado.filas], ["Dim 1", "Dim 1", "Dim 2", "Dim 3"])

    def test_funciona_con_cualquier_cantidad_de_factores_y_dimensiones(self):
        """Agregar un factor o una dimensión nueva no requiere cambiar código."""
        extendida = _fuente_pequena() + [FactorCatalogo("E", "Dimensión nueva", ns=2, tc=10, ie=3)]
        resultado = calcular_indicadores_literatura(extendida)
        self.assertEqual(len(resultado.filas), 5)
        self.assertIn("Dimensión nueva", {f.dimension for f in resultado.filas})

    def test_rechaza_factores_repetidos(self):
        with self.assertRaises(ValueError):
            calcular_indicadores_literatura(_fuente_pequena() + [FactorCatalogo("A", "Dim 1", 5, 1, 3)])

    def test_propaga_los_errores_de_las_reglas_de_negocio(self):
        with self.assertRaises(ValueError):
            calcular_indicadores_literatura([
                FactorCatalogo("A", "Dim 1", ns=0, tc=1, ie=3),  # NS = 0
                FactorCatalogo("B", "Dim 1", ns=2, tc=1, ie=3),
            ])


class ObtenerIndicadoresTests(unittest.TestCase):

    def test_una_fuente_propia_no_se_marca_como_simulada(self):
        self.assertFalse(obtener_indicadores_literatura(_fuente_pequena).simulado)

    def test_la_fuente_por_defecto_se_marca_como_simulada(self):
        self.assertTrue(obtener_indicadores_literatura().simulado)

    def test_compatibilidad_simulada_con_3_citas_da_0_375(self):
        filas = obtener_indicadores_literatura().filas
        compatibilidad = next(f for f in filas if f.nombre == "Compatibilidad")
        self.assertEqual((compatibilidad.tc, compatibilidad.ns, compatibilidad.r), (3, 8, 0.375))

    def test_todas_las_il_e_is_estan_en_la_escala_1_a_4(self):
        for fila in obtener_indicadores_literatura().filas:
            with self.subTest(factor=fila.nombre):
                self.assertIn(fila.il, (1, 2, 3, 4))
                self.assertIn(fila.is_, (1, 2, 3, 4))
