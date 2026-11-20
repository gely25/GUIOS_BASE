"""Pruebas del cliente OpenAlex sin red: se inyecta una función que simula urlopen."""

import io
import json
import unittest
import urllib.error
import urllib.parse
from unittest import mock

from apps.external_services.bibliografia.base import ErrorFuenteCientifica
from apps.external_services.bibliografia.openalex import OpenAlexFuente, reconstruir_resumen


def obra(n, doi=True):
    return {
        'id': f'https://openalex.org/W{n}',
        'doi': f'https://doi.org/10.1/{n}' if doi else None,
        'title': f'Open source adoption {n}',
        'publication_year': 2022,
        'abstract_inverted_index': {'Open': [0], 'source': [1], 'adoption': [2]},
        'primary_location': {'landing_page_url': f'https://ejemplo.org/{n}'},
    }


class AbridorFalso:
    def __init__(self, paginas=None, errores=()):
        self.paginas = list(paginas or [])
        self.errores = list(errores)
        self.urls = []

    def __call__(self, peticion, timeout):
        self.urls.append(peticion.full_url)
        if self.errores:
            raise self.errores.pop(0)
        return io.BytesIO(json.dumps({'results': self.paginas.pop(0)}).encode())


class OpenAlexTests(unittest.TestCase):

    def test_reconstruye_el_resumen(self):
        self.assertEqual(reconstruir_resumen({'b': [1], 'a': [0], 'c': [2, 3]}), 'a b c c')
        self.assertIsNone(reconstruir_resumen(None))

    def test_filtra_periodo_y_convierte_resultados(self):
        abridor = AbridorFalso([[obra(1), obra(2, doi=False), {'title': None}]])
        fuente = OpenAlexFuente(abrir=abridor, reintentos=0)
        resultados = fuente.buscar('"open source"', 2020, 2025, 50)

        self.assertEqual(len(resultados), 2)
        self.assertEqual(resultados[0].doi, 'https://doi.org/10.1/1')
        self.assertEqual(resultados[0].resumen, 'Open source adoption')
        self.assertEqual(resultados[0].url, 'https://ejemplo.org/1')
        self.assertIsNone(resultados[1].doi)
        consulta = urllib.parse.parse_qs(urllib.parse.urlparse(abridor.urls[0]).query)
        self.assertEqual(consulta['filter'], ['from_publication_date:2020-01-01,to_publication_date:2025-12-31'])
        self.assertNotIn('api_key', consulta)

    def test_pagina_hasta_el_maximo(self):
        abridor = AbridorFalso([[obra(1), obra(2)], [obra(3), obra(4)], [obra(5)]])
        with mock.patch('apps.external_services.bibliografia.openalex._POR_PAGINA_MAX', 2):
            resultados = OpenAlexFuente(abrir=abridor, reintentos=0).buscar('x', 2020, 2025, 3)
        self.assertEqual(len(resultados), 3)
        self.assertEqual(len(abridor.urls), 2)

    def test_se_detiene_cuando_la_pagina_viene_incompleta(self):
        abridor = AbridorFalso([[obra(1)]])
        resultados = OpenAlexFuente(abrir=abridor, reintentos=0).buscar('x', 2020, 2025, 50)
        self.assertEqual((len(resultados), len(abridor.urls)), (1, 1))

    def test_envia_la_api_key_si_esta_configurada(self):
        abridor = AbridorFalso([[]])
        OpenAlexFuente(api_key='clave', abrir=abridor, reintentos=0).buscar('x', 2020, 2025, 5)
        self.assertIn('api_key=clave', abridor.urls[0])

    def test_un_error_de_red_se_convierte_en_error_de_fuente(self):
        abridor = AbridorFalso(errores=[urllib.error.URLError('sin red')])
        with self.assertRaises(ErrorFuenteCientifica):
            OpenAlexFuente(abrir=abridor, reintentos=0).buscar('x', 2020, 2025, 5)

    def test_reintenta_ante_un_429(self):
        error = urllib.error.HTTPError('u', 429, 'Too Many Requests', {}, None)
        abridor = AbridorFalso([[obra(1)]], errores=[error])
        with mock.patch('apps.external_services.bibliografia.openalex.time.sleep'):
            resultados = OpenAlexFuente(abrir=abridor, reintentos=1).buscar('x', 2020, 2025, 5)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(len(abridor.urls), 2)

    def test_no_reintenta_un_400(self):
        abridor = AbridorFalso(errores=[urllib.error.HTTPError('u', 400, 'Bad', {}, None)])
        with self.assertRaises(ErrorFuenteCientifica):
            OpenAlexFuente(abrir=abridor, reintentos=3).buscar('x', 2020, 2025, 5)
        self.assertEqual(len(abridor.urls), 1)
