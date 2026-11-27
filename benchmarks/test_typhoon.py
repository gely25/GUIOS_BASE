import json
from dataclasses import replace
from datetime import date
from io import BytesIO
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from apps.external_services.clientes_ia import PROVEEDORES as OPERATIVOS
from benchmarks.casos_ia import CASOS
from benchmarks.clientes_ia import TYPHOON_MODELO
from benchmarks.ia import configurar, ejecutar


class TyphoonTests(TestCase):
    def test_solo_registro_y_constancia_exclusivos_del_benchmark(self):
        self.assertNotIn('typhoon', OPERATIVOS)
        hoy = date.today().isoformat()
        entrada = dict(proveedor='typhoon', modelo=TYPHOON_MODELO, plan='typhoon-free-benchmark',
                       fuente_oficial='https://docs.opentyphoon.ai/en/faq/',
                       verificado=hoy, vence=hoy, sin_cargos_ni_excedentes=True)
        variables = {'GUIOS_AI_TYPHOON_API_KEY': 'ficticia', 'GUIOS_AI_TYPHOON_MODEL': TYPHOON_MODELO}
        with self.assertRaises(ValueError):
            configurar(['typhoon'], 'real', [entrada], variables)
        entrada['uso'] = 'benchmark'
        self.assertEqual(configurar(['typhoon'], 'real', [entrada], variables)['typhoon'][0], TYPHOON_MODELO)

    def test_ejecuta_ocho_casos_con_transporte_compatible_y_metricas(self):
        modelo = configurar(['typhoon'], 'mock', [])
        casos = iter(CASOS)

        def enviar(url, carga, clave, timeout):
            caso = next(casos)
            self.assertEqual(url, 'https://api.opentyphoon.ai/v1/chat/completions')
            self.assertEqual(carga['model'], TYPHOON_MODELO)
            self.assertEqual(carga['max_tokens'], 1024)
            self.assertNotIn('response_format', carga)
            if caso.id == 'P2':
                self.assertIn('evidencias', json.loads(carga['messages'][1]['content']))
            return {'choices': [{'message': {'content': json.dumps(caso.esperado)}}],
                    'usage': {'prompt_tokens': 50, 'completion_tokens': 54, 'total_tokens': 104}}

        filas = ejecutar(modelo, 'mock', enviar)
        self.assertEqual(len(filas), 8)
        self.assertTrue(all(f['contrato_valido'] and f['calidad_ok'] and f['tokens_totales'] == 104 for f in filas))
        self.assertTrue(all(f['referencias_validas'] for f in filas if f['operacion'] != 'preguntas'))

    def test_bloquea_casos_fuera_del_conjunto_sintetico_y_no_reintenta_429(self):
        modelo = configurar(['typhoon'], 'mock', [])
        transporte = Mock(side_effect=HTTPError('https://ejemplo.test', 429, '', {}, BytesIO()))
        with self.assertRaises(ValueError):
            ejecutar(modelo, 'mock', transporte, casos=(replace(CASOS[0]),))
        transporte.assert_not_called()
        with patch('benchmarks.ia.sleep', side_effect=AssertionError('No debe esperar para reintentar')):
            filas = ejecutar(modelo, 'real', transporte)
        transporte.assert_called_once()
        self.assertEqual(filas[0]['http_status'], 429)
        self.assertTrue(all(f['error'] == 'omitido_por_429' for f in filas[1:]))
