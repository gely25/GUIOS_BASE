from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import Mock, patch

from benchmarks.casos_ia import CASOS
from benchmarks.ia import evaluar
from benchmarks.local_ia import destino_local, resumir


class PilotoLocalTests(TestCase):
    def test_p2_usa_la_entrada_hu09_con_la_misma_expectativa(self):
        caso = next(caso for caso in CASOS if caso.id == 'P2')
        self.assertIn('LDAP', caso.entrada['evidencias'][0]['contenido'])
        self.assertEqual(set(caso.entrada), {
            'max_preguntas', 'preguntas_descartadas', 'factor', 'subfactor', 'evidencias', 'preguntas',
        })
        self.assertTrue(evaluar(caso, {'preguntas': []}))
        self.assertFalse(evaluar(caso, {'preguntas': ['¿Se admite LDAP?']}))

    def test_migracion_rechaza_cualquier_otro_destino_antes_de_conectar(self):
        for nombre, host in [('otra_base', 'localhost'), ('guios_pro_ai_dev', '10.0.0.7')]:
            with self.subTest(nombre=nombre, host=host):
                db = Mock(vendor='postgresql', settings_dict={'NAME': nombre, 'HOST': host})
                with patch('django.db.connections', {'default': db}), self.assertRaises(SystemExit):
                    destino_local()
                db.cursor.assert_not_called()

    def test_medicion_distingue_concurrencia_de_cantidad_de_intentos(self):
        inicio = datetime(2026, 1, 1, tzinfo=timezone.utc)

        def fila(proveedor, desde, hasta, tokens, error=''):
            return dict(proveedor=proveedor, inicio=inicio + timedelta(seconds=desde),
                        fin=inicio + timedelta(seconds=hasta), vence=inicio + timedelta(seconds=60),
                        tokens_observados=tokens, tokens_reservados=500, unidades_reservadas=20,
                        fallback=bool(error), error=error)

        filas = [fila('gemini', 0, 4, 90), fila('cloudflare', 1, 2, None, '429'),
                 fila('gemini', 3, 5, 84)]
        resumen = resumir(filas, inicio + timedelta(seconds=10), 6000)
        self.assertEqual(resumen['intentos_reservados'], 3)
        self.assertEqual(resumen['concurrencia_pico'], 2)
        self.assertEqual(resumen['concurrencia_pico_por_proveedor'], {'gemini': 2, 'cloudflare': 1})
        self.assertEqual(resumen['ventana_de_ia_ms'], 5000)
        self.assertEqual(resumen['tiempo_con_reservas_abiertas_ms'], 5000)
        self.assertEqual(resumen['tiempo_fuera_de_ventana_ia_ms'], 1000)
        self.assertEqual(resumen['tokens_observados'], 174)
        self.assertEqual(resumen['errores'], {'429': 1})
