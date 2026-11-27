import json
from datetime import date
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError

from apps.external_services.api_ia import APIPreguntas
from apps.external_services.clientes_ia import ClienteProveedor, MODELOS_GOOGLE_CANDIDATOS, autorizar
from apps.external_services.ai_errors import RespuestaInvalida
from benchmarks.casos_ia import CASOS
from benchmarks.cuotas_google import PresupuestoGoogle
from benchmarks.ia import configurar, ejecutar


class GoogleBenchmarkTests(TestCase):
    def test_gemma_usa_generatecontent_y_descarta_pensamiento(self):
        def responder(url, carga, clave, timeout):
            self.assertEqual(url, 'https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent')
            self.assertIn('CONTRATO OBLIGATORIO', carga['systemInstruction']['parts'][0]['text'])
            self.assertEqual(json.loads(carga['contents'][0]['parts'][0]['text']), {'max_preguntas': 1})
            self.assertEqual(carga['generationConfig'], {'temperature': 0, 'maxOutputTokens': 2048})
            return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
                {'text': 'razonamiento', 'thought': True}, {'text': '{"preguntas":[]}'},
            ]}}], 'usageMetadata': {'promptTokenCount': 500, 'candidatesTokenCount': 10, 'totalTokenCount': 540}}

        cliente = ClienteProveedor('gemini', 'gemma-4-31b-it', 'ficticia', 15, transporte=responder)
        cliente.max_tokens_salida = 2048
        cliente.tokens_reservados = 16000
        cliente.margen_tokens_entrada = 256
        self.assertEqual(APIPreguntas(cliente)({'max_preguntas': 1}), [])
        self.assertEqual(cliente.uso['tokens_totales'], 540)

    def test_gemma_mantiene_validacion_estricta_y_no_acepta_truncado(self):
        for motivo, texto in [('STOP', '{"preguntas":[3]}'), ('MAX_TOKENS', '{"preguntas":[]}')]:
            with self.subTest(motivo=motivo):
                paquete = {'candidates': [{'finishReason': motivo, 'content': {'parts': [{'text': texto}]}}]}
                cliente = ClienteProveedor('gemini', 'gemma-4-26b-a4b-it', 'ficticia', 15,
                                           transporte=lambda *_: paquete)
                with self.assertRaises(RespuestaInvalida):
                    APIPreguntas(cliente)({})

    def test_flash_lite_31_solicita_mime_json_en_generatecontent(self):
        def responder(url, carga, *_):
            self.assertTrue(url.endswith('/models/gemini-3.1-flash-lite:generateContent'))
            self.assertEqual(carga['generationConfig']['responseMimeType'], 'application/json')
            return {'candidates': [{'finishReason': 'STOP',
                                    'content': {'parts': [{'text': '{"preguntas":[]}' }]}}]}

        cliente = ClienteProveedor('gemini', 'gemini-3.1-flash-lite', 'ficticia', 15, transporte=responder)
        self.assertEqual(APIPreguntas(cliente)({}), [])

    def test_configuracion_explicita_reutiliza_la_clave_sin_cambiar_modelo_principal(self):
        hoy = date.today().isoformat()
        variables = {'GUIOS_AI_GEMINI_API_KEY': 'ficticia', 'GUIOS_AI_GEMINI_MODEL': 'gemini-3.5-flash-lite'}
        entrada = dict(proveedor='gemini', modelo='gemma-4-31b-it', plan='gemini-free-tier',
                       fuente_oficial='https://ai.google.dev/gemini-api/docs/pricing#gemma-4',
                       verificado=hoy, vence=hoy, sin_cargos_ni_excedentes=True, uso='benchmark')
        cfg = configurar(['gemini'], 'real', [entrada], variables, 'gemma-4-31b-it')
        self.assertEqual(cfg['gemini'][:2], ('gemma-4-31b-it', 'ficticia'))
        self.assertEqual(variables['GUIOS_AI_GEMINI_MODEL'], 'gemini-3.5-flash-lite')
        with self.assertRaises(ValueError):
            autorizar('gemini', 'gemma-4-31b-it', [entrada], date.today())
        with self.assertRaises(ValueError):
            configurar(['gemini'], 'real', [], variables, 'gemma-4-31b-it')

    def test_ocho_casos_por_modelo_incluyen_p2_y_no_hacen_red(self):
        config = {('gemini', m): configurar(['gemini'], 'mock', [], modelo_explicito=m)['gemini']
                  for m in MODELOS_GOOGLE_CANDIDATOS}
        with patch('apps.external_services.clientes_ia.build_opener', side_effect=AssertionError('Red')):
            filas = ejecutar(config, 'mock')
        self.assertEqual(len(filas), 24)
        self.assertEqual(sum(r['caso'] == 'P2' for r in filas), 3)
        self.assertTrue(all(r['contrato_valido'] and r['calidad_ok'] for r in filas))

    def test_cuota_google_se_comparte_y_un_429_detiene_los_tres_modelos(self):
        config = {('gemini', m): configurar(['gemini'], 'mock', [], modelo_explicito=m)['gemini']
                  for m in MODELOS_GOOGLE_CANDIDATOS}

        def responder(*_):
            raise HTTPError('https://ejemplo.test', 429, 'cuota', {}, None)

        filas = ejecutar(config, 'mock', responder, casos=CASOS[:2], presupuesto_google=PresupuestoGoogle(6))
        self.assertEqual(filas[0]['http_status'], 429)
        self.assertTrue(all(f['error'] == 'omitido_por_429' for f in filas[1:]))

    def test_ventana_de_tokens_no_suma_modelos(self):
        ahora = 0
        esperas = []

        def esperar(segundos):
            nonlocal ahora
            esperas.append(segundos)
            ahora += segundos

        presupuesto = PresupuestoGoogle(3, reloj=lambda: ahora, esperar=esperar)
        self.assertFalse(presupuesto.admitir(16001))
        for _ in range(3):
            self.assertTrue(presupuesto.admitir(6000))
            presupuesto.cerrar(6000)
        self.assertEqual(esperas, [60])
        self.assertFalse(presupuesto.admitir(1))
