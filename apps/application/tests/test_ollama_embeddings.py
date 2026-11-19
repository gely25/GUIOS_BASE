import json
import unittest
from unittest.mock import patch

from apps.external_services.ollama_embeddings import OllamaEmbeddings
from apps.external_services.ollama_preguntas import AnalisisNoDisponible


class OllamaEmbeddingsTests(unittest.TestCase):
    @patch('apps.external_services.ollama_embeddings.http.client.HTTPConnection')
    def test_lote_local_y_dimensiones(self, conexion):
        respuesta = conexion.return_value.getresponse.return_value
        respuesta.status = 200
        vector = [1.0] + [0.0] * 1023
        respuesta.read.return_value = json.dumps({'embeddings': [vector, vector]}).encode()
        self.assertEqual(OllamaEmbeddings('bge-m3')(['¿Qué versión?', '¿Qué edición?']), [vector, vector])
        conexion.assert_called_once_with('127.0.0.1', 11434, timeout=120)
        llamada = conexion.return_value.request.call_args
        self.assertEqual(llamada.args, ('POST', '/api/embed'))
        self.assertFalse(json.loads(llamada.kwargs['body'])['truncate'])
        conexion.return_value.close.assert_called_once()

    @patch('apps.external_services.ollama_embeddings.http.client.HTTPConnection')
    def test_rechaza_vectores_invalidos(self, conexion):
        respuesta = conexion.return_value.getresponse.return_value
        respuesta.status = 200
        for vectores in ([], [[1]], [[0.0]*1024], [[float('nan')]*1024], [[True]*1024]):
            with self.subTest(vectores=str(vectores)[:40]):
                respuesta.read.return_value = json.dumps({'embeddings': vectores}).encode()
                with self.assertRaises(AnalisisNoDisponible):
                    OllamaEmbeddings('bge-m3')(['Pregunta'])

    @patch('apps.external_services.ollama_embeddings.http.client.HTTPConnection')
    def test_falla_sin_modelo_o_conexion(self, conexion):
        respuesta = conexion.return_value.getresponse.return_value
        respuesta.status = 404
        with self.assertRaises(AnalisisNoDisponible):
            OllamaEmbeddings('bge-m3')(['Pregunta'])
        conexion.return_value.request.side_effect = OSError('sin servicio')
        with self.assertRaises(AnalisisNoDisponible):
            OllamaEmbeddings('bge-m3')(['Pregunta'])

    @patch('apps.external_services.ollama_embeddings.http.client.HTTPConnection')
    def test_limites_y_modelo_permitido(self, conexion):
        with self.assertRaises(AnalisisNoDisponible):
            OllamaEmbeddings('modelo-cloud')
        with self.assertRaises(AnalisisNoDisponible):
            OllamaEmbeddings('bge-m3')(['Pregunta']*129)
        self.assertEqual(OllamaEmbeddings('bge-m3')([]), [])
        conexion.assert_not_called()
