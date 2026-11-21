"""
Pruebas de la API pública de indicadores_literatura/ y de BibliographicService
(HU-03).
"""

import unittest

from django.core.management import call_command
from django.test import TestCase

import apps.application.services.indicadores_literatura as paquete
from apps.application.services.bibliographic import BibliographicService
from apps.application.services.indicadores_literatura import FactorCatalogo, IndicadoresLiteratura

API_PUBLICA = {
    "obtener_indicadores_literatura",
    "calcular_indicadores_literatura",
    "FactorCatalogo",
    "FilaIndicadores",
    "IndicadoresLiteratura",
}


class ApiPublicaTests(unittest.TestCase):

    def test_el_paquete_expone_solo_la_api_publica(self):
        self.assertEqual(set(paquete.__all__), API_PUBLICA)


class BibliographicServiceTests(TestCase):

    def test_indicadores_con_el_catalogo_por_defecto(self):
        call_command('cargar_catalogo_guios', verbosity=0)
        resultado = BibliographicService().indicadores_literatura()
        self.assertIsInstance(resultado, IndicadoresLiteratura)
        self.assertEqual(len(resultado.filas), 18)
        self.assertEqual(resultado.version, 'v1-2021')

    def test_indicadores_con_una_fuente_propia(self):
        def fuente():
            return (
                FactorCatalogo("A", "Tecnológica", 2, 4, 3),
                FactorCatalogo("B", "Tecnológica", 1, 1, 3),
            )

        resultado = BibliographicService().indicadores_literatura(fuente)
        self.assertEqual([fila.nombre for fila in resultado.filas], ["A", "B"])
        self.assertIsNone(resultado.version)
