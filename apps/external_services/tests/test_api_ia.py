"""Pruebas del adaptador HTTP sin llamar a servicios externos."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from apps.external_services.api_ia import APIBibliografia, APIJSON, APIPreguntas, APISuficiencia, APIValoracion
from apps.external_services.ai_errors import AnalisisNoDisponible


class _Respuesta:
    def __init__(self, body):
        self.body = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self, cantidad):
        return self.body.read(cantidad)


class APIIATests(unittest.TestCase):
    def setUp(self):
        self.cliente = APIJSON('clave-de-prueba', 'gemini-2.5-flash',
                               'https://generativelanguage.googleapis.com/v1beta/openai')

    def test_url_insegura_rechazada(self):
        for url in ('http://localhost:8000/v1', 'file:///tmp', 'https://ejemplo.test/?x=1',
                    'https://usuario:clave@ejemplo.test/v1'):
            with self.subTest(url=url), self.assertRaises(AnalisisNoDisponible):
                APIJSON('clave', 'modelo', url)

    @patch('apps.external_services.api_ia.urlopen')
    def test_preguntas_validas(self, abrir):
        salida = {'preguntas': ['¿Hay documentación verificable?']}
        abrir.return_value = _Respuesta(json.dumps({
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(salida)}}]
        }).encode('utf-8'))
        self.assertEqual(APIPreguntas(self.cliente)({'max_preguntas': 2}), salida['preguntas'])
        llamada = abrir.call_args.args[0]
        self.assertEqual(llamada.get_method(), 'POST')
        self.assertIn(b'gemini-2.5-flash', llamada.data)
        self.assertNotIn(b'clave-de-prueba', llamada.data)
        self.assertEqual(json.loads(llamada.data)['response_format']['type'], 'json_object')

    @patch('apps.external_services.api_ia.urlopen')
    def test_esquema_suficiencia_enviado_sin_cambiar_formato_http(self, abrir):
        salida = {'estado': 'INSUFICIENTE', 'justificacion': 'Faltan datos.',
                  'referencias': [], 'preguntas': []}
        abrir.return_value = _Respuesta(json.dumps({
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(salida)}}]
        }).encode('utf-8'))
        self.assertEqual(APISuficiencia(self.cliente)({'fuentes': []}), salida)
        peticion = json.loads(abrir.call_args.args[0].data)
        texto = peticion['messages'][0]['content']
        self.assertIn('estado, justificacion, referencias, preguntas', texto)
        self.assertIn('SUFICIENTE', texto)
        self.assertEqual(peticion['response_format'], {'type': 'json_object'})

    @patch('apps.external_services.api_ia.urlopen')
    def test_sugerencias_bibliograficas_usan_json_y_contexto_no_confiable(self, abrir):
        salida = {'sugerencias': [{
            'publicacion_id': 7,
            'pertinencia': 85,
            'justificacion': 'El resumen estudia la adopción de software libre.',
        }]}
        abrir.return_value = _Respuesta(json.dumps({
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(salida)}}]
        }).encode('utf-8'))
        entrada = {'factor': {'id': 2, 'nombre': 'Adopción'}, 'publicaciones': [{'id': 7, 'titulo': 'Estudio', 'resumen': ''}]}

        self.assertEqual(APIBibliografia(self.cliente)(entrada), salida)

        peticion = json.loads(abrir.call_args.args[0].data)
        instruccion = peticion['messages'][0]['content']
        self.assertIn('datos no confiables', instruccion)
        for campo in ('publicacion_id', 'pertinencia', 'justificacion'):
            self.assertIn(f'"{campo}"', instruccion)
        self.assertEqual(peticion['response_format'], {'type': 'json_object'})

    @patch('apps.external_services.api_ia.urlopen')
    def test_json_incorrecto_rechazado(self, abrir):
        abrir.return_value = _Respuesta(b'{"choices":[{"finish_reason":"stop","message":{"content":"no-json"}}]}')
        with self.assertRaises(AnalisisNoDisponible):
            APIPreguntas(self.cliente)({'max_preguntas': 1})

    @patch('apps.external_services.api_ia.urlopen')
    def test_respuesta_fuera_del_esquema_rechazada(self, abrir):
        salida = {'preguntas': [42]}
        abrir.return_value = _Respuesta(json.dumps({
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(salida)}}]
        }).encode('utf-8'))
        with self.assertRaisesRegex(AnalisisNoDisponible, 'fuera del esquema'):
            APIPreguntas(self.cliente)({'max_preguntas': 1})

    @patch('apps.external_services.api_ia.urlopen')
    def test_suficiencia_no_valida_sin_referencias(self, abrir):
        salida = {'estado': 'SUFICIENTE', 'justificacion': 'Contexto suficiente.',
                  'referencias': [], 'preguntas': []}
        abrir.return_value = _Respuesta(json.dumps({
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(salida)}}]
        }).encode('utf-8'))
        with self.assertRaisesRegex(AnalisisNoDisponible, 'sin fuentes válidas'):
            APISuficiencia(self.cliente)({'fuentes': []})

    @patch('apps.external_services.api_ia.urlopen')
    def test_bibliografia_rechaza_ids_ajenos_al_contexto(self, abrir):
        salida = {'sugerencias': [{
            'publicacion_id': 8,
            'pertinencia': 85,
            'justificacion': 'Justificación de prueba.',
        }]}
        abrir.return_value = _Respuesta(json.dumps({
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(salida)}}]
        }).encode('utf-8'))
        entrada = {'publicaciones': [{'id': 7}]}
        with self.assertRaisesRegex(AnalisisNoDisponible, 'fuera del esquema'):
            APIBibliografia(self.cliente)(entrada)

    @patch('apps.external_services.api_ia.urlopen')
    def test_sin_respuesta_completa(self, abrir):
        abrir.return_value = _Respuesta(b'{"choices":[{"finish_reason":"length","message":{"content":"{}"}}]}')
        with self.assertRaises(AnalisisNoDisponible):
            APIValoracion(self.cliente)({'fuentes': []})

    @patch('apps.external_services.api_ia.urlopen')
    def test_error_429_sin_filtrar_cuerpo(self, abrir):
        abrir.side_effect = HTTPError('https://ejemplo.test', 429, 'error', {}, io.BytesIO(b'clave-secreta'))
        with self.assertRaisesRegex(AnalisisNoDisponible, 'límite de solicitudes') as ctx:
            APIValoracion(self.cliente)({'fuentes': []})
        self.assertNotIn('clave-secreta', str(ctx.exception))

    def test_contexto_excesivo_rechazado_antes_de_solicitar(self):
        with self.assertRaisesRegex(AnalisisNoDisponible, 'contexto supera'):
            self.cliente.consultar({'fuentes': ['a' * 17000]}, {}, 'test')


if __name__ == '__main__':
    unittest.main()
