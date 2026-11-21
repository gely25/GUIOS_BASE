import json
from unittest import TestCase
from unittest.mock import patch

from apps.external_services.ollama_preguntas import AnalisisNoDisponible, OllamaPreguntas


class OllamaPreguntasTests(TestCase):
    def setUp(self):
        self.proveedor = OllamaPreguntas('qwen3:4b-instruct')

    @patch('apps.external_services.ollama_preguntas.http.client.HTTPConnection')
    def test_solicitud_local_y_formato(self, conectar):
        conexion = conectar.return_value
        respuesta = conexion.getresponse.return_value
        respuesta.status = 200
        respuesta.read.return_value = json.dumps({'done': True, 'message': {'content': '{"preguntas":["¿Qué versiones de ODF admite?"]}'}}).encode()
        self.assertEqual(self.proveedor({'subfactor': 'Formatos', 'evidencias': ['ODF']}), ['¿Qué versiones de ODF admite?'])
        conectar.assert_called_once_with('127.0.0.1', 11434, timeout=120)
        args, kwargs = conexion.request.call_args
        self.assertEqual(args, ('POST', '/api/chat'))
        cuerpo = json.loads(kwargs['body'])
        self.assertFalse(cuerpo['stream'])
        self.assertEqual(cuerpo['format']['type'], 'object')
        self.assertIn('ODF', cuerpo['messages'][1]['content'])
        conexion.close.assert_called_once()

    @patch('apps.external_services.ollama_preguntas.http.client.HTTPConnection')
    def test_fallo_conexion(self, conectar):
        conectar.return_value.request.side_effect = TimeoutError()
        with self.assertRaises(AnalisisNoDisponible):
            self.proveedor({})
        conectar.return_value.close.assert_called_once()

    @patch('apps.external_services.ollama_preguntas.http.client.HTTPConnection')
    def test_rechaza_respuestas_invalidas(self, conectar):
        respuesta = conectar.return_value.getresponse.return_value
        respuesta.status = 200
        for contenido in ('no json', '{"preguntas":[3]}', '{"preguntas":["texto sin pregunta"]}', '{"preguntas":[],"valor":4}'):
            respuesta.read.return_value = json.dumps({'done': True, 'message': {'content': contenido}}).encode()
            with self.subTest(contenido=contenido), self.assertRaises(AnalisisNoDisponible):
                self.proveedor({})

    @patch('apps.external_services.ollama_preguntas.http.client.HTTPConnection')
    def test_contexto_excesivo_no_envia(self, conectar):
        with self.assertRaises(AnalisisNoDisponible):
            self.proveedor({'evidencia': 'a' * 16001})
        conectar.assert_not_called()

    def test_modelo_no_permitido(self):
        with self.assertRaises(AnalisisNoDisponible):
            OllamaPreguntas('modelo-cloud')

    @patch('apps.external_services.ollama_preguntas.http.client.HTTPConnection')
    def test_lista_vacia_valida(self, conectar):
        respuesta = conectar.return_value.getresponse.return_value
        respuesta.status = 200
        respuesta.read.return_value = b'{"done":true,"message":{"content":"{\\"preguntas\\":[]}"}}'
        self.assertEqual(self.proveedor({}), [])

    @patch('apps.external_services.ollama_preguntas.http.client.HTTPConnection')
    def test_esquema_dinamico_y_priorizacion(self, conectar):
        conexion = conectar.return_value
        respuesta = conexion.getresponse.return_value
        respuesta.status = 200
        respuesta.read.return_value = b'{"done":true,"message":{"content":"{\\"preguntas\\":[]}"}}'
        self.proveedor({'max_preguntas': 1})
        cuerpo = json.loads(conexion.request.call_args.kwargs['body'])
        self.assertEqual(cuerpo['format']['properties']['preguntas']['maxItems'], 1)
        self.assertIn('No debes llenar el cupo', cuerpo['messages'][0]['content'])

    @patch('apps.external_services.ollama_preguntas.http.client.HTTPConnection')
    def test_respuesta_supera_cupo(self, conectar):
        respuesta = conectar.return_value.getresponse.return_value
        respuesta.status = 200
        respuesta.read.return_value = json.dumps({'done': True, 'message': {'content': json.dumps({'preguntas': ['¿Una?', '¿Otra?']})}}).encode()
        with self.assertRaises(AnalisisNoDisponible):
            self.proveedor({'max_preguntas': 1})

    @patch('apps.external_services.ollama_preguntas.http.client.HTTPConnection')
    def test_proveedor_suficiencia_usa_esquema_estructurado(self, conectar):
        from apps.external_services.ollama_suficiencia import OllamaSuficiencia
        respuesta = conectar.return_value.getresponse.return_value
        respuesta.status = 200
        resultado = {'estado': 'INSUFICIENTE', 'justificacion': 'Falta versión', 'referencias': [], 'preguntas': ['¿Qué versión?']}
        respuesta.read.return_value = json.dumps({'done': True, 'message': {'content': json.dumps(resultado)}}).encode()
        self.assertEqual(OllamaSuficiencia('qwen3:4b-instruct')({'fuentes': []}), resultado)
        cuerpo = json.loads(conectar.return_value.request.call_args.kwargs['body'])
        self.assertEqual(set(cuerpo['format']['required']), set(resultado))
