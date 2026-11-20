"""Pruebas del cliente de OpenAlex. No usan internet: la red se reemplaza por una simulada."""

import json
import unittest
import urllib.error
import urllib.parse

from apps.external_services.openalex import (
    OpenAlexClient,
    OpenAlexError,
    normalizar_doi,
)

CLAVE_FALSA = "clave-de-prueba-123"


class _Respuesta:
    def __init__(self, datos):
        self._cuerpo = json.dumps(datos).encode("utf-8")

    def read(self):
        return self._cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _cliente(datos=None, error=None, capturar=None):
    """Cliente con red simulada: devuelve `datos`, lanza `error` y guarda la petición en `capturar`."""
    def abrir(peticion, timeout=None):
        if capturar is not None:
            capturar.append(peticion)
        if error is not None:
            raise error
        return _Respuesta(datos)
    return OpenAlexClient(api_key=CLAVE_FALSA, base_url="https://api.openalex.org", abrir=abrir)


OBRA = {
    "id": "https://openalex.org/W111",
    "doi": "https://doi.org/10.1000/ABC.1",
    "display_name": "Adopción de software libre en organizaciones",
    "publication_year": 2022,
}


class NormalizarDoiTests(unittest.TestCase):
    def test_quita_prefijo_y_pasa_a_minusculas(self):
        self.assertEqual(normalizar_doi("https://doi.org/10.1000/ABC.1"), "10.1000/abc.1")

    def test_vacio_o_none_devuelve_none(self):
        self.assertIsNone(normalizar_doi(None))
        self.assertIsNone(normalizar_doi("   "))


class BuscarTests(unittest.TestCase):
    def test_arma_la_consulta_con_el_rango_de_anios(self):
        enviadas = []
        _cliente({"results": []}, capturar=enviadas).buscar("software libre", 2020, 2025, 10)
        url = urllib.parse.unquote(enviadas[0].full_url)
        self.assertIn("from_publication_date:2020-01-01", url)
        self.assertIn("to_publication_date:2025-12-31", url)
        self.assertIn("per_page=10", url)

    def test_busca_solo_en_titulo_y_resumen(self):
        enviadas = []
        _cliente({"results": []}, capturar=enviadas).buscar('("a" OR "b") AND c')
        url = urllib.parse.unquote_plus(enviadas[0].full_url)
        self.assertIn('search.title_and_abstract=("a" OR "b") AND c', url)

    def test_normaliza_la_publicacion(self):
        resultado = _cliente({"results": [OBRA]}).buscar("software libre")
        self.assertEqual(len(resultado), 1)
        publicacion = resultado[0]
        self.assertEqual(publicacion.doi, "10.1000/abc.1")
        self.assertEqual(publicacion.url, "https://doi.org/10.1000/abc.1")
        self.assertEqual(publicacion.anio, 2022)
        self.assertEqual(publicacion.fuente, "OpenAlex")

    def test_sin_doi_usa_el_identificador_de_openalex(self):
        obra = dict(OBRA, doi=None)
        publicacion = _cliente({"results": [obra]}).buscar("software libre")[0]
        self.assertIsNone(publicacion.doi)
        self.assertEqual(publicacion.url, "https://openalex.org/W111")

    def test_sin_resultados_devuelve_lista_vacia(self):
        self.assertEqual(_cliente({"results": []}).buscar("tema inexistente"), [])

    def test_ignora_obras_sin_titulo(self):
        sin_titulo = dict(OBRA, display_name=None)
        self.assertEqual(_cliente({"results": [sin_titulo]}).buscar("software libre"), [])

    def test_limita_los_resultados_por_pagina_a_100(self):
        enviadas = []
        _cliente({"results": []}, capturar=enviadas).buscar("software libre", max_resultados=500)
        self.assertIn("per_page=100", enviadas[0].full_url)


class ContarTests(unittest.TestCase):
    def test_devuelve_el_total_de_meta_count(self):
        self.assertEqual(_cliente({"meta": {"count": 1234}, "results": []}).contar("software libre"), 1234)

    def test_pide_una_sola_obra_y_el_rango_de_anios(self):
        enviadas = []
        _cliente({"meta": {"count": 7}, "results": []}, capturar=enviadas).contar("software libre", 2021, 2024)
        url = urllib.parse.unquote(enviadas[0].full_url)
        self.assertIn("per_page=1", url)
        self.assertIn("from_publication_date:2021-01-01", url)
        self.assertIn("to_publication_date:2024-12-31", url)

    def test_cero_resultados_es_valido(self):
        self.assertEqual(_cliente({"meta": {"count": 0}, "results": []}).contar("nada"), 0)

    def test_sin_meta_falla_con_mensaje_claro(self):
        with self.assertRaises(OpenAlexError) as contexto:
            _cliente({"results": []}).contar("software libre")
        self.assertIn("total", str(contexto.exception))

    def test_valida_igual_que_buscar(self):
        with self.assertRaises(ValueError):
            _cliente({"meta": {"count": 1}}).contar("  ")
        with self.assertRaises(ValueError):
            _cliente({"meta": {"count": 1}}).contar("software libre", 2025, 2020)
        with self.assertRaises(OpenAlexError):
            OpenAlexClient(api_key="", abrir=lambda *a, **k: None).contar("software libre")


class ValidacionTests(unittest.TestCase):
    def test_consulta_vacia_falla(self):
        with self.assertRaises(ValueError):
            _cliente({"results": []}).buscar("   ")

    def test_rango_invertido_falla(self):
        with self.assertRaises(ValueError):
            _cliente({"results": []}).buscar("software libre", 2025, 2020)

    def test_sin_clave_falla_con_mensaje_claro(self):
        cliente = OpenAlexClient(api_key="", abrir=lambda *a, **k: None)
        with self.assertRaises(OpenAlexError) as contexto:
            cliente.buscar("software libre")
        self.assertIn("BIBLIOGRAPHIC_API_KEY", str(contexto.exception))


class ErroresTests(unittest.TestCase):
    def _http(self, codigo):
        return urllib.error.HTTPError("https://api.openalex.org/works?api_key=" + CLAVE_FALSA,
                                      codigo, "error", {}, None)

    def test_clave_rechazada(self):
        with self.assertRaises(OpenAlexError) as contexto:
            _cliente(error=self._http(403)).buscar("software libre")
        self.assertIn("clave", str(contexto.exception))

    def test_limite_de_consultas(self):
        with self.assertRaises(OpenAlexError) as contexto:
            _cliente(error=self._http(429)).buscar("software libre")
        self.assertIn("limit", str(contexto.exception))

    def test_error_de_red(self):
        with self.assertRaises(OpenAlexError):
            _cliente(error=urllib.error.URLError("sin internet")).buscar("software libre")

    def test_los_mensajes_no_exponen_la_clave(self):
        for error in (self._http(403), self._http(500), urllib.error.URLError("fallo")):
            with self.assertRaises(OpenAlexError) as contexto:
                _cliente(error=error).buscar("software libre")
            self.assertNotIn(CLAVE_FALSA, str(contexto.exception))
            with self.assertRaises(OpenAlexError) as contexto:
                _cliente(error=error).contar("software libre")
            self.assertNotIn(CLAVE_FALSA, str(contexto.exception))
