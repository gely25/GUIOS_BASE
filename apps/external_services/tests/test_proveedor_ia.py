"""Pruebas del enrutamiento paralelo sin llamadas a proveedores reales."""
from threading import Barrier, Event
from unittest import TestCase
from unittest.mock import patch

from django.test import override_settings

from apps.external_services.ai_errors import AnalisisNoDisponible
from apps.external_services.proveedor_ia import ProveedoresParalelos, configurado, modelo_activo


class ProveedoresParalelosTests(TestCase):
    @override_settings(
        GUIOS_AI_GEMINI_API_KEY='gemini-test',
        GUIOS_AI_GEMINI_MODEL='gemini-test-model',
        GUIOS_AI_OPENAI_API_KEY='openai-test',
        GUIOS_AI_OPENAI_MODEL='openai-test-model',
    )
    def test_inicia_solicitudes_en_paralelo_y_usa_primera_respuesta_valida(self):
        primero_iniciado = Event()
        liberar_primero = Event()
        enrutador = ProveedoresParalelos('preguntas')

        def consultar(proveedor, _entrada):
            if proveedor.nombre == 'Gemini':
                primero_iniciado.set()
                liberar_primero.wait(timeout=2)
                return {'provider': 'Gemini'}
            self.assertTrue(primero_iniciado.wait(timeout=2))
            return {'provider': 'OpenAI'}

        try:
            with patch.object(enrutador, '_consultar', side_effect=consultar):
                self.assertEqual(enrutador({}), {'provider': 'OpenAI'})
            self.assertEqual(enrutador.ultimo_identificador, 'OpenAI/openai-test-model')
        finally:
            liberar_primero.set()

    @override_settings(
        GUIOS_AI_GEMINI_API_KEY='gemini-test',
        GUIOS_AI_GEMINI_MODEL='gemini-test-model',
        GUIOS_AI_OPENAI_API_KEY='openai-test',
        GUIOS_AI_OPENAI_MODEL='openai-test-model',
    )
    def test_falla_con_un_proveedor_y_acepta_la_respuesta_del_siguiente(self):
        barrera = Barrier(2)
        enrutador = ProveedoresParalelos('preguntas')

        def consultar(proveedor, _entrada):
            barrera.wait(timeout=2)
            if proveedor.nombre == 'Gemini':
                raise AnalisisNoDisponible('respuesta inválida')
            return {'provider': 'OpenAI'}

        with patch.object(enrutador, '_consultar', side_effect=consultar):
            self.assertEqual(enrutador({}), {'provider': 'OpenAI'})
        self.assertEqual(enrutador.ultimo_proveedor, 'OpenAI')

    @override_settings(
        GUIOS_AI_GEMINI_API_KEY='',
        GUIOS_AI_GEMINI_MODEL='',
        GUIOS_AI_OPENAI_API_KEY='',
        GUIOS_AI_OPENAI_MODEL='',
        GUIOS_AI_GROQ_API_KEY='',
        GUIOS_AI_GROQ_MODEL='',
    )
    def test_sin_proveedores_configurados_avisa_y_no_hace_llamadas(self):
        self.assertFalse(configurado())
        self.assertEqual(modelo_activo(), '')
        with self.assertRaisesRegex(AnalisisNoDisponible, 'Configure al menos un proveedor'):
            ProveedoresParalelos('preguntas')({})

    def test_rechaza_un_tipo_de_analisis_desconocido(self):
        with self.assertRaisesRegex(AnalisisNoDisponible, 'Tipo de análisis'):
            ProveedoresParalelos('invalido')
