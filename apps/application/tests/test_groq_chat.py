"""Proveedor opcional Groq para HU09/HU10: formato, errores y que Ollama siga siendo el predeterminado."""
import json
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.external_services import groq_chat
from apps.external_services.ollama_preguntas import AnalisisNoDisponible, consultar_json, modelo_admitido
from apps.external_services.ollama_valoracion import OllamaValoracion

ESQUEMA = {'type': 'object', 'additionalProperties': False, 'required': ['preguntas'],
           'properties': {'preguntas': {'type': 'array', 'items': {'type': 'string'}}}}
GROQ = dict(LLM_PROVIDER='groq', GROQ_API_KEY='gsk_clave_de_prueba', GROQ_MODEL='openai/gpt-oss-20b')


def _resp(estado, cuerpo):
    return estado, (cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode())


def _ok(contenido, razon='stop'):
    return _resp(200, {'choices': [{'finish_reason': razon, 'message': {'content': json.dumps(contenido)}}]})


class GroqChatTests(SimpleTestCase):
    @override_settings(LLM_PROVIDER='ollama', GROQ_API_KEY='x')
    def test_por_defecto_sigue_siendo_ollama(self):
        self.assertFalse(groq_chat.activo())
        self.assertTrue(modelo_admitido('qwen3:4b-instruct'))
        self.assertFalse(modelo_admitido('openai/gpt-oss-20b'))

    @override_settings(LLM_PROVIDER='groq', GROQ_API_KEY='')
    def test_sin_clave_no_se_activa(self):
        self.assertFalse(groq_chat.activo())

    @override_settings(**GROQ)
    def test_con_groq_se_admite_solo_el_modelo_configurado(self):
        self.assertTrue(modelo_admitido('openai/gpt-oss-20b'))
        self.assertFalse(modelo_admitido('otro/modelo'))
        OllamaValoracion('openai/gpt-oss-20b')
        with self.assertRaises(AnalisisNoDisponible):
            OllamaValoracion('otro/modelo')

    @override_settings(**GROQ)
    def test_usa_json_schema_en_modelos_compatibles_y_devuelve_el_objeto(self):
        with mock.patch.object(groq_chat, '_peticion', return_value=_ok({'preguntas': ['¿Existe?']})) as p:
            r = consultar_json('openai/gpt-oss-20b', {'subfactor': 'x'}, ESQUEMA, 'Instrucción.')
        self.assertEqual(r, {'preguntas': ['¿Existe?']})
        cuerpo = p.call_args[0][0]
        self.assertEqual(cuerpo['response_format']['type'], 'json_schema')
        self.assertEqual(cuerpo['temperature'], 0)
        self.assertEqual(cuerpo['messages'][0]['content'], 'Instrucción.')

    @override_settings(**GROQ)
    def test_si_el_esquema_falla_reintenta_con_json_object(self):
        with mock.patch.object(groq_chat, '_peticion', side_effect=[_resp(400, {'error': 'schema'}), _ok({'preguntas': []})]) as p:
            r = consultar_json('openai/gpt-oss-20b', {}, ESQUEMA, 'Instrucción.')
        self.assertEqual(r, {'preguntas': []})
        self.assertEqual(p.call_count, 2)
        segundo = p.call_args_list[1][0][0]
        self.assertEqual(segundo['response_format']['type'], 'json_object')
        self.assertIn('JSON', segundo['messages'][0]['content'])

    @override_settings(**dict(GROQ, GROQ_MODEL='llama-3.3-70b-versatile'))
    def test_modelo_sin_soporte_de_esquema_usa_json_object_directo(self):
        with mock.patch.object(groq_chat, '_peticion', return_value=_ok({'preguntas': []})) as p:
            consultar_json('llama-3.3-70b-versatile', {}, ESQUEMA, 'I.')
        self.assertEqual(p.call_count, 1)
        self.assertEqual(p.call_args[0][0]['response_format']['type'], 'json_object')

    @override_settings(**GROQ)
    def test_errores_claros_y_sin_filtrar_la_clave(self):
        casos = [(401, 'clave de Groq'), (429, 'límite de uso'), (500, 'código 500')]
        for estado, texto in casos:
            with mock.patch.object(groq_chat, '_peticion', return_value=_resp(estado, {'error': 'x'})):
                with self.assertRaises(AnalisisNoDisponible) as cm:
                    consultar_json('openai/gpt-oss-20b', {}, ESQUEMA, 'I.')
            self.assertIn(texto, str(cm.exception))
            self.assertNotIn('gsk_clave_de_prueba', str(cm.exception))

    @override_settings(**GROQ)
    def test_respuesta_cortada_o_invalida_se_rechaza(self):
        for respuesta in (_ok({'preguntas': []}, razon='length'), _resp(200, b'no es json'),
                          _resp(200, {'choices': [{'finish_reason': 'stop', 'message': {'content': 'texto'}}]})):
            with mock.patch.object(groq_chat, '_peticion', return_value=respuesta):
                with self.assertRaises(AnalisisNoDisponible):
                    consultar_json('openai/gpt-oss-20b', {}, ESQUEMA, 'I.')

    @override_settings(**GROQ)
    def test_falla_de_red_se_informa_sin_detalles_sensibles(self):
        with mock.patch.object(groq_chat, '_peticion', side_effect=OSError('timeout')):
            with self.assertRaises(AnalisisNoDisponible) as cm:
                consultar_json('openai/gpt-oss-20b', {}, ESQUEMA, 'I.')
        self.assertIn('Groq', str(cm.exception))