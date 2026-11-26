"""Pruebas del enrutamiento por turnos con respaldo, sin llamadas a proveedores reales."""
import io
import json
from concurrent.futures import ThreadPoolExecutor
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError

from django.test import override_settings

from apps.external_services import proveedor_ia
from apps.external_services.ai_errors import AnalisisNoDisponible
from apps.external_services.proveedor_ia import ProveedoresRespaldo, configurado, modelo_activo

SIN_PROVEEDORES = dict(
    GUIOS_AI_GEMINI_API_KEY='', GUIOS_AI_GEMINI_MODEL='',
    GUIOS_AI_OPENAI_API_KEY='', GUIOS_AI_OPENAI_MODEL='',
    GUIOS_AI_GROQ_API_KEY='', GUIOS_AI_GROQ_MODEL='',
)
GEMINI_Y_GROQ = dict(
    SIN_PROVEEDORES,
    GUIOS_AI_GEMINI_API_KEY='gemini-test', GUIOS_AI_GEMINI_MODEL='gemini-test-model',
    GUIOS_AI_GROQ_API_KEY='groq-test', GUIOS_AI_GROQ_MODEL='groq-test-model',
)
SOLO_GROQ = dict(SIN_PROVEEDORES, GUIOS_AI_GROQ_API_KEY='groq-test', GUIOS_AI_GROQ_MODEL='groq-test-model')


class _RespuestaHTTP(io.BytesIO):
    """Respuesta simulada de Chat Completions, usable como context manager."""

    def __init__(self, contenido):
        cuerpo = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(contenido)}}]}
        super().__init__(json.dumps(cuerpo).encode('utf-8'))


def _api_simulada(comportamiento, llamadas):
    """Sustituye urlopen: `comportamiento` mapea fragmento de URL -> respuesta o excepción."""
    def urlopen(peticion, timeout=None):
        url = peticion.full_url
        llamadas.append(url)
        for fragmento, resultado in comportamiento.items():
            if fragmento in url:
                if isinstance(resultado, Exception):
                    raise resultado
                return _RespuestaHTTP(resultado)
        raise AssertionError(f'URL inesperada: {url}')
    return urlopen


def _http_429(url):
    return HTTPError(url, 429, 'Too Many Requests', {}, None)


PREGUNTA_VALIDA = {'preguntas': ['¿Existe un acuerdo formal?']}


class ProveedoresRespaldoTests(TestCase):
    def setUp(self):
        # Turno determinista: cada prueba arranca por el primer proveedor de la lista.
        parche = patch.object(proveedor_ia, '_turno', 0)
        parche.start()
        self.addCleanup(parche.stop)

    def _enrutador_con_registro(self, falla=()):
        enrutador = ProveedoresRespaldo('preguntas')
        usados = []

        def consultar(proveedor, _entrada):
            usados.append(proveedor.nombre)
            if proveedor.nombre in falla:
                raise AnalisisNoDisponible('La API de IA alcanzó su límite de solicitudes.')
            return {'proveedor': proveedor.nombre}

        patch.object(enrutador, '_consultar', side_effect=consultar).start()
        self.addCleanup(patch.stopall)
        return enrutador, usados

    @override_settings(**GEMINI_Y_GROQ)
    def test_reparte_las_peticiones_por_turnos_y_una_sola_llamada_por_peticion(self):
        enrutador, usados = self._enrutador_con_registro()
        respuestas = [enrutador({})['proveedor'] for _ in range(4)]
        self.assertEqual(respuestas, ['Gemini', 'Groq', 'Gemini', 'Groq'])
        self.assertEqual(usados, ['Gemini', 'Groq', 'Gemini', 'Groq'])
        self.assertEqual(enrutador.ultimo_identificador, 'Groq/groq-test-model')

    @override_settings(**GEMINI_Y_GROQ)
    def test_el_turno_es_seguro_entre_hilos(self):
        enrutador, usados = self._enrutador_con_registro()
        with ThreadPoolExecutor(max_workers=8) as hilos:
            list(hilos.map(lambda _: enrutador({}), range(200)))
        self.assertEqual(len(usados), 200)
        self.assertEqual(usados.count('Gemini'), 100)
        self.assertEqual(usados.count('Groq'), 100)
        self.assertEqual(proveedor_ia._turno, 200)

    @override_settings(**GEMINI_Y_GROQ)
    def test_ante_429_reintenta_con_el_siguiente_proveedor(self):
        llamadas = []
        api = _api_simulada({'googleapis.com': _http_429('gemini'), 'groq.com': PREGUNTA_VALIDA}, llamadas)
        enrutador = ProveedoresRespaldo('preguntas')
        with patch('apps.external_services.api_ia.urlopen', side_effect=api):
            self.assertEqual(enrutador({}), PREGUNTA_VALIDA['preguntas'])
        self.assertEqual([('googleapis' in u) for u in llamadas], [True, False])
        self.assertEqual(enrutador.ultimo_proveedor, 'Groq')
        self.assertEqual(enrutador.ultimo_modelo, 'groq-test-model')

    @override_settings(**GEMINI_Y_GROQ)
    def test_ante_timeout_reintenta_con_el_siguiente_proveedor_y_recorre_la_lista_circular(self):
        proveedor_ia._turno = 1  # Este turno empieza por Groq; el respaldo vuelve a Gemini.
        llamadas = []
        api = _api_simulada({'groq.com': TimeoutError('timed out'), 'googleapis.com': PREGUNTA_VALIDA}, llamadas)
        enrutador = ProveedoresRespaldo('preguntas')
        with patch('apps.external_services.api_ia.urlopen', side_effect=api):
            self.assertEqual(enrutador({}), PREGUNTA_VALIDA['preguntas'])
        self.assertEqual([('groq.com' in u) for u in llamadas], [True, False])
        self.assertEqual(enrutador.ultimo_identificador, 'Gemini/gemini-test-model')

    @override_settings(**GEMINI_Y_GROQ)
    def test_si_todos_fallan_informa_cada_error_sin_llamadas_extra(self):
        enrutador, usados = self._enrutador_con_registro(falla=('Gemini', 'Groq'))
        with self.assertRaisesRegex(AnalisisNoDisponible, 'límite de solicitudes'):
            enrutador({})
        self.assertEqual(usados, ['Gemini', 'Groq'])
        self.assertIsNone(enrutador.ultimo_identificador)

    @override_settings(**SOLO_GROQ)
    def test_con_un_solo_proveedor_siempre_usa_ese(self):
        enrutador, usados = self._enrutador_con_registro()
        for _ in range(3):
            self.assertEqual(enrutador({}), {'proveedor': 'Groq'})
        self.assertEqual(usados, ['Groq', 'Groq', 'Groq'])
        self.assertEqual(modelo_activo(), 'Groq')

    @override_settings(**SOLO_GROQ)
    def test_con_un_solo_proveedor_que_falla_no_reintenta(self):
        enrutador, usados = self._enrutador_con_registro(falla=('Groq',))
        with self.assertRaises(AnalisisNoDisponible):
            enrutador({})
        self.assertEqual(usados, ['Groq'])

    @override_settings(**SIN_PROVEEDORES)
    def test_sin_proveedores_configurados_avisa_y_no_hace_llamadas(self):
        self.assertFalse(configurado())
        self.assertEqual(modelo_activo(), '')
        with self.assertRaisesRegex(AnalisisNoDisponible, 'Configure al menos un proveedor'):
            ProveedoresRespaldo('preguntas')({})

    def test_rechaza_un_tipo_de_analisis_desconocido(self):
        with self.assertRaisesRegex(AnalisisNoDisponible, 'Tipo de análisis'):
            ProveedoresRespaldo('invalido')
