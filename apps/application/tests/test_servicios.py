"""
Comprueba la convención de la capa de aplicación: cada servicio del apartado 7.1
expone una clase como punto de entrada.
"""

import importlib
import unittest

SERVICIOS = {
    "ai": "AIService",
    "bibliographic": "BibliographicService",
    "catalog": "CatalogService",
    "document": "DocumentService",
    "evaluation": "EvaluationService",
    "report": "ReportService",
    "retrieval": "RetrievalService",
}


class ServiciosTests(unittest.TestCase):

    def test_cada_modulo_expone_su_clase_de_servicio(self):
        for modulo, clase in SERVICIOS.items():
            with self.subTest(modulo=modulo):
                importado = importlib.import_module(f"apps.application.services.{modulo}")
                self.assertTrue(hasattr(importado, clase))
