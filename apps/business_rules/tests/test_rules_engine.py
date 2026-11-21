"""Pruebas del RulesEngine de la actualización bibliográfica (HU02)."""

import unittest
from decimal import Decimal
from fractions import Fraction

from apps.business_rules.rules_engine import (
    EntradaFactor,
    anio_en_periodo,
    recalcular_indicadores,
    redondear_ri,
    tc_actualizado,
)
from apps.business_rules.tests.test_caso_referencia_il_is import (
    CASO_REFERENCIA_IL_IS,
    IE_ORIGINAL,
    NS_POR_FACTOR,
)


class TcActualizadoTests(unittest.TestCase):

    def test_suma_las_publicaciones_nuevas_al_tc_de_2021(self):
        self.assertEqual(tc_actualizado(33, 4), 37)
        self.assertEqual(tc_actualizado(0, 0), 0)

    def test_rechaza_negativos_y_no_enteros(self):
        with self.assertRaises(ValueError):
            tc_actualizado(-1, 0)
        with self.assertRaises(ValueError):
            tc_actualizado(1, -2)
        with self.assertRaises(TypeError):
            tc_actualizado(1.5, 0)
        with self.assertRaises(TypeError):
            tc_actualizado(True, 0)


class RedondeoTests(unittest.TestCase):

    def test_cuatro_decimales_con_redondeo_comercial(self):
        self.assertEqual(redondear_ri(Fraction(33, 8)), Decimal('4.1250'))
        self.assertEqual(redondear_ri(Fraction(1, 3)), Decimal('0.3333'))
        self.assertEqual(redondear_ri(Fraction(2, 3)), Decimal('0.6667'))
        self.assertEqual(redondear_ri(Fraction(0)), Decimal('0.0000'))


class RecalcularIndicadoresTests(unittest.TestCase):

    def test_reproduce_el_caso_de_referencia_guios(self):
        entradas = [EntradaFactor(f, NS_POR_FACTOR[f], tc, IE_ORIGINAL) for f, tc, _, _ in CASO_REFERENCIA_IL_IS]
        _, resultado = recalcular_indicadores(entradas)
        for factor, tc, il, is_ in CASO_REFERENCIA_IL_IS:
            with self.subTest(factor=factor):
                self.assertEqual(resultado[factor].tc, tc)
                self.assertEqual(resultado[factor].il, il)
                self.assertEqual(resultado[factor].is_, is_)
                self.assertEqual(resultado[factor].r, Fraction(tc, NS_POR_FACTOR[factor]))

    def test_el_cuartil_usa_la_fraccion_exacta_no_el_redondeo(self):
        # r = 1/3, 1/3, 2/3, 1: rq1 = 1/3 exacto; 0.3333 redondeado no debe cambiar el tramo.
        entradas = [EntradaFactor('A', 3, 1, 3), EntradaFactor('B', 3, 1, 3),
                    EntradaFactor('C', 3, 2, 3), EntradaFactor('D', 1, 1, 3)]
        _, r = recalcular_indicadores(entradas)
        self.assertEqual((r['A'].il, r['B'].il), (1, 1))
        self.assertEqual(r['A'].relacion_ri, Decimal('0.3333'))

    def test_todos_los_tc_en_cero_dan_il_1(self):
        _, r = recalcular_indicadores([EntradaFactor('A', 2, 0, 3), EntradaFactor('B', 4, 0, 4)])
        self.assertEqual((r['A'].il, r['B'].il), (1, 1))
        self.assertEqual((r['A'].is_, r['B'].is_), (2, 2))

    def test_rechaza_ns_cero_repetidos_y_catalogos_de_un_factor(self):
        with self.assertRaises(ValueError):
            recalcular_indicadores([EntradaFactor('A', 0, 1, 3), EntradaFactor('B', 1, 1, 3)])
        with self.assertRaises(ValueError):
            recalcular_indicadores([EntradaFactor('A', 1, 1, 3), EntradaFactor('A', 2, 1, 3)])
        with self.assertRaises(ValueError):
            recalcular_indicadores([EntradaFactor('A', 1, 1, 3)])

    def test_es_determinista(self):
        entradas = [EntradaFactor(f, NS_POR_FACTOR[f], tc, 3) for f, tc, _, _ in CASO_REFERENCIA_IL_IS]
        self.assertEqual(recalcular_indicadores(entradas), recalcular_indicadores(list(entradas)))


class PeriodoTests(unittest.TestCase):

    def test_solo_2020_a_2025(self):
        self.assertTrue(anio_en_periodo(2020))
        self.assertTrue(anio_en_periodo(2025))
        self.assertFalse(anio_en_periodo(2019))
        self.assertFalse(anio_en_periodo(2026))
        self.assertFalse(anio_en_periodo(None))
