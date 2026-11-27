import io
import json
from contextlib import redirect_stdout
from datetime import date
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError

from benchmarks.ia import configurar
from benchmarks.clientes_ia import validar_endpoint_openrouter
from benchmarks.sonda_ia import _resumir_http


class SondasTests(TestCase):
    def test_cloudflare_reconoce_token_legado_y_prefiere_clave_canonica(self):
        modelo = '@cf/meta/llama-3.3-70b-instruct-fp8-fast'
        hoy = date.today().isoformat()
        autorizacion = dict(proveedor='cloudflare', modelo=modelo, plan='workers-free',
                            fuente_oficial='https://developers.cloudflare.com/workers-ai/platform/pricing/',
                            verificado=hoy, vence=hoy, sin_cargos_ni_excedentes=True)
        variables = {'GUIOS_AI_CLOUDFLARE_API_TOKEN': 'ficticio',
                     'GUIOS_AI_CLOUDFLARE_MODEL': modelo,
                     'GUIOS_AI_CLOUDFLARE_ACCOUNT_ID': 'a' * 32}
        self.assertEqual(configurar(['cloudflare'], 'real', [autorizacion], variables)['cloudflare'][1], 'ficticio')
        variables['GUIOS_AI_CLOUDFLARE_API_KEY'] = 'canonica'
        self.assertEqual(configurar(['cloudflare'], 'real', [autorizacion], variables)['cloudflare'][1], 'canonica')

    def test_openrouter_bloquea_coste_positivo_y_tag_distinto(self):
        modelo = 'google/modelo:free'
        endpoint = {'model_id': modelo, 'tag': 'google-ai-studio',
                    'pricing': {'prompt': '0', 'completion': '0'}}
        with patch('benchmarks.clientes_ia.obtener_metadatos', return_value={
            'data': {'id': modelo, 'endpoints': [endpoint]},
        }):
            validar_endpoint_openrouter(modelo, 'google-ai-studio', 5)
            with self.assertRaises(ValueError):
                validar_endpoint_openrouter(modelo, 'otro-tag', 5)
            endpoint['pricing']['request'] = '0.1'
            with self.assertRaises(ValueError):
                validar_endpoint_openrouter(modelo, 'google-ai-studio', 5)

    def test_clasifica_errores_sin_reproducir_el_mensaje_remoto(self):
        casos = (
            ('groq', 403, {'code': 'model_permission_blocked_org'}, {}, 'organización'),
            ('openrouter', 429, {'metadata': {'provider_code': 'privado'}}, {}, 'ascendente'),
            ('openrouter', 429, {}, {'X-RateLimit-Limit': '50', 'X-RateLimit-Reset': '123'}, 'plataforma'),
            ('openrouter', 429, {}, {}, 'indeterminado'),
        )
        for proveedor, status, datos, headers, esperado in casos:
            cuerpo = json.dumps({'error': datos | {'message': 'secreto-simulado'}}).encode()
            salida = io.StringIO()
            with redirect_stdout(salida):
                _resumir_http(proveedor, HTTPError('https://ejemplo.test', status, '', headers, io.BytesIO(cuerpo)))
            self.assertIn(esperado, salida.getvalue())
            self.assertNotIn('secreto-simulado', salida.getvalue())
