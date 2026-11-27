"""Pruebas del administrador secuencial sin solicitudes reales."""
import json
from dataclasses import replace
from datetime import date, timedelta
from http.client import IncompleteRead
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.db import connection, connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.application.services.tareas_ia import en_orden
from apps.data.models import CredencialBloqueadaIA, IntentoIA, TareaIA, UnidadCuotaIA
from apps.external_services.planificador_ia import PlanificadorIA, PoliticaCuota, TareaEnCurso, TareaIncierta

from apps.external_services import proveedor_ia
from apps.external_services.ai_errors import AnalisisNoDisponible, ErrorProveedor, Motivo
from apps.external_services.api_ia import APIJSON


def candidato(nombre, operaciones=('preguntas',), unidad=None):
    return proveedor_ia.ProveedorConfigurado(
        nombre, 'modelo', 'clave-de-prueba', frozenset(operaciones), unidad or nombre, '', '',
    )


def en_hilo(funcion, *args):
    try:
        return funcion(*args)
    finally:
        connections.close_all()


@override_settings(GUIOS_AI_ESPERA_SEGUNDOS=0)
class AdministradorTests(TransactionTestCase):
    def setUp(self):
        self.gemini = candidato('gemini')
        self.cohere = candidato('cohere')
        self.configuracion = self.enterContext(patch.object(
            proveedor_ia, '_leer_proveedores', return_value=[self.gemini, self.cohere],
        ))
        self.politicas = {
            'gemini': PoliticaCuota(2, {'rpm': 10}, 6000, 200, 0),
            'cohere': PoliticaCuota(2, {'rpm': 10}, 6000, 200, 0),
        }
        self.enterContext(patch.object(proveedor_ia, 'leer_politicas', return_value=self.politicas))
        self.perfiles = self.enterContext(patch.object(proveedor_ia, 'leer_perfiles', return_value={}))
        self.cliente = self.enterContext(patch.object(proveedor_ia, 'ClienteProveedor'))
        self.inferencia = self.cliente.return_value.consultar
        self.consulta = proveedor_ia.obtener_proveedor('preguntas')

    def test_exito_se_reutiliza_y_no_envia_respaldo(self):
        self.inferencia.return_value = {'preguntas': ['Hay CSV?']}
        self.assertEqual(self.consulta({}), ['Hay CSV?'])
        self.assertEqual(self.consulta({}), ['Hay CSV?'])
        self.assertEqual(self.consulta.ultimo_identificador, 'Gemini/modelo')
        self.cliente.assert_called_once()
        self.assertEqual(IntentoIA.objects.count(), 1)

    def test_reuso_aislado_por_actor_y_ambito_sin_duplicar_el_intento(self):
        self.inferencia.side_effect = [{'preguntas': ['Pregunta A?']}, {'preguntas': ['Pregunta B?']}]
        self.assertEqual(self.consulta.con_ambito({}, ['evaluacion', 10], 1), ['Pregunta A?'])
        with self.assertRaisesRegex(AnalisisNoDisponible, 'no se puede reutilizar'):
            self.consulta.con_ambito({}, ['evaluacion', 10], 2)
        self.assertEqual(self.consulta.con_ambito({}, ['evaluacion', 11], 2), ['Pregunta B?'])
        self.assertEqual(self.consulta.con_ambito({}, ['evaluacion', 10], 1), ['Pregunta A?'])
        self.assertEqual(self.cliente.call_count, 2)

    def test_sin_autorizacion_no_se_construye_el_cliente(self):
        self.configuracion.return_value = []
        with self.assertRaises(AnalisisNoDisponible):
            self.consulta({})
        self.cliente.assert_not_called()

    def test_el_coste_dinamico_reserva_contexto_y_reconcilia_neurons(self):
        self.configuracion.return_value = [candidato('cloudflare')]
        politica = PoliticaCuota(2, {'rpm': 30, 'unidades_diarias': 10000}, 65536, 2048, 0,
                                 256, 26668, 204805, reconciliar_uso=True)
        self.politicas['cloudflare'] = politica
        from apps.external_services.clientes_ia import ClienteProveedor

        def transporte(url, carga, clave, timeout):
            bytes_enviados = sum(len(m['content'].encode('utf-8')) for m in carga['messages'])
            intento = IntentoIA.objects.latest('pk')
            self.assertEqual(intento.tokens_reservados, bytes_enviados + 256 + 2048)
            self.assertEqual(intento.unidades_reservadas, politica.calcular_neurons(bytes_enviados + 256, 2048))
            return {'choices': [{'message': {'content': '{"preguntas":[]}'}}],
                    'usage': {'prompt_tokens': 100, 'completion_tokens': 12, 'total_tokens': 112}}

        self.cliente.side_effect = lambda *datos: ClienteProveedor(*datos, transporte=transporte)
        self.assertEqual(self.consulta({'subfactor': 'Lectura'}), [])
        self.assertEqual(self.consulta({'subfactor': 'Texto citado: "acceso"\n' * 100}), [])
        pequeno, grande = IntentoIA.objects.order_by('pk')
        self.assertGreater(grande.unidades_reservadas, pequeno.unidades_reservadas)
        self.assertEqual(grande.tokens_observados, 112)
        self.assertEqual(grande.tokens_cuota, 112)
        self.assertEqual(grande.unidades_cuota, 6)

    def test_neurons_cubre_el_redondeo_de_ambas_categorias_al_reservar(self):
        politica = PoliticaCuota(1, {'unidades_diarias': 2}, 10, 1, 0, 1, 26668, 204805)
        self.assertEqual(politica.para_peticion(0).unidades_por_intento, 2)
        self.assertEqual(proveedor_ia._neurons_observados({'tokens_totales': 2}, politica, 2), 2)

    def test_reconciliar_libera_capacidad_sin_reducir_el_cargo_de_intentos_anteriores(self):
        self.configuracion.return_value = [self.gemini]
        self.politicas['gemini'] = PoliticaCuota(2, {'tpm': 120}, 100, 10, 0, reconciliar_uso=True)
        self.inferencia.return_value = {'preguntas': []}
        cliente = self.cliente.return_value
        cliente.uso = {'tokens_entrada': 10, 'tokens_salida': 10, 'tokens_totales': 20}
        self.consulta.con_ambito({}, 'primero')
        self.consulta.con_ambito({}, 'segundo')
        self.assertEqual(list(IntentoIA.objects.order_by('pk').values_list('tokens_cuota', flat=True)), [20, 20])
        with self.assertRaises(AnalisisNoDisponible):
            self.consulta.con_ambito({}, 'tercero')
        IntentoIA.objects.filter(pk=IntentoIA.objects.order_by('pk').first().pk).update(tokens_cuota=None)
        # Un intento histórico sin cargo conciliado cuenta por su reserva original.
        with self.assertRaises(AnalisisNoDisponible):
            self.consulta.con_ambito({}, 'legado')
        self.assertEqual(self.cliente.call_count, 2)

    def test_uso_incompleto_o_timeout_conserva_reserva(self):
        self.configuracion.return_value = [self.gemini]
        self.politicas['gemini'] = PoliticaCuota(2, {'tpm': 1000}, 100, 10, 0, reconciliar_uso=True)
        self.cliente.return_value.uso = {'tokens_totales': 12}
        self.inferencia.return_value = {'preguntas': []}
        self.consulta.con_ambito({}, 'incompleto')
        self.cliente.return_value.uso = {'tokens_entrada': 10, 'tokens_salida': 10, 'tokens_totales': 20}
        self.inferencia.side_effect = ErrorProveedor(Motivo.TIMEOUT, 'timeout')
        with self.assertRaises(TareaIncierta):
            self.consulta.con_ambito({}, 'incierto')
        self.assertEqual(list(IntentoIA.objects.order_by('pk').values_list('tokens_cuota', flat=True)), [None, None])

    def test_fallback_secuencial_tras_respuesta_invalida(self):
        def responder(*args):
            self.assertFalse(connection.in_atomic_block)
            intentos = list(IntentoIA.objects.order_by('pk'))
            if len(intentos) == 1:
                self.assertIsNone(intentos[0].fin)
                return {'preguntas': ['Sin interrogacion']}
            self.assertIsNotNone(intentos[0].fin)
            self.assertIsNone(intentos[1].fin)
            return {'preguntas': []}

        self.inferencia.side_effect = responder
        self.assertEqual(self.consulta({}), [])
        self.assertEqual(self.consulta.ultimo_identificador, 'Cohere/modelo')
        self.assertEqual(list(IntentoIA.objects.values_list('fallback', flat=True)), [False, True])

    def test_fallback_secuencial_y_cache_compartidos_entre_modelos_del_mismo_proyecto(self):
        alterno = replace(self.gemini, modelo='segundo', adicional=True)
        self.configuracion.return_value = [self.gemini, alterno]
        self.politicas[alterno.identificador_config] = PoliticaCuota(1, {'rpm': 10}, 6000, 200, 0)

        def responder(*_):
            intentos = list(IntentoIA.objects.order_by('pk'))
            if len(intentos) == 1:
                return {'preguntas': ['Sin signo']}
            self.assertFalse(connection.in_atomic_block)
            self.assertIsNotNone(intentos[0].fin)
            return {'preguntas': []}

        self.inferencia.side_effect = responder
        self.assertEqual(self.consulta({}), [])
        self.assertEqual(self.consulta({}), [])
        self.assertEqual(self.consulta.ultimo_identificador, 'Gemini/segundo')
        self.assertEqual(self.gemini.credencial, alterno.credencial)
        self.assertEqual(list(IntentoIA.objects.order_by('pk').values_list('modelo', 'fallback')),
                         [('modelo', False), ('segundo', True)])

    def test_distribuye_modelos_sin_superar_la_concurrencia_local_ni_la_cuota_del_proyecto(self):
        alterno = replace(self.gemini, modelo='segundo', adicional=True)
        self.configuracion.return_value = [self.gemini, alterno]
        self.politicas['gemini'] = PoliticaCuota(3, {'tpm': 100}, 40, 10, 0)
        self.politicas[self.gemini.identificador_config] = PoliticaCuota(1, {'tpm': 70}, 40, 10, 0)
        self.politicas[alterno.identificador_config] = PoliticaCuota(1, {'tpm': 80}, 30, 10, 0)
        primera_en_curso = Event()
        liberar = Event()

        def responder(entrada, *_):
            if entrada.get('subfactor') == 'Primero':
                primera_en_curso.set()
                self.assertTrue(liberar.wait(10))
            return {'preguntas': []}

        self.inferencia.side_effect = responder
        with ThreadPoolExecutor(max_workers=1) as executor:
            primero = executor.submit(en_hilo, self.consulta, {'subfactor': 'Primero'})
            try:
                self.assertTrue(primera_en_curso.wait(10))
                with self.assertRaises(TareaEnCurso):
                    self.consulta({'subfactor': 'Primero'})
                self.assertEqual(self.consulta({'subfactor': 'Segundo'}), [])
                self.assertEqual(self.consulta.ultimo_identificador, 'Gemini/segundo')
                with self.assertRaises(AnalisisNoDisponible):
                    self.consulta({'subfactor': 'Tercero'})
            finally:
                liberar.set()
            self.assertEqual(primero.result(timeout=10), [])
        self.assertEqual(self.cliente.call_count, 2)
        self.assertEqual(IntentoIA.objects.count(), 2)

    def test_429_del_primer_modelo_bloquea_temporalmente_el_proyecto(self):
        alterno = replace(self.gemini, modelo='segundo', adicional=True)
        self.configuracion.return_value = [self.gemini, alterno]
        self.politicas[alterno.identificador_config] = PoliticaCuota(1, {'rpm': 10}, 6000, 200, 0)
        self.inferencia.side_effect = ErrorProveedor(Motivo.CUOTA, 'cuota compartida', 429, 120)
        with self.assertRaises(AnalisisNoDisponible):
            self.consulta({})
        self.cliente.assert_called_once()
        self.assertIsNotNone(UnidadCuotaIA.objects.get(pk='gemini').cooldown_hasta)

    def test_cooldown_compartido_respeta_retry_after(self):
        self.configuracion.return_value.insert(1, candidato('groq', unidad='gemini'))
        self.inferencia.side_effect = [
            ErrorProveedor(Motivo.CUOTA, 'cuota', 429, 300),
            {'preguntas': []}, {'preguntas': []},
        ]
        self.consulta.con_ambito({}, 1)
        self.consulta.con_ambito({}, 2)
        self.assertGreater(UnidadCuotaIA.objects.get(pk='gemini').cooldown_hasta,
                           timezone.now() + timedelta(seconds=280))
        self.assertEqual([c.args[0] for c in self.cliente.call_args_list], ['gemini', 'cohere', 'cohere'])

    def test_timeout_bloquea_la_tarea_sin_fallback_ni_reintento(self):
        self.inferencia.side_effect = ErrorProveedor(Motivo.TIMEOUT, 'timeout')
        for _ in range(2):
            with self.assertRaises(TareaIncierta):
                self.consulta({})
        self.cliente.assert_called_once()
        tarea = TareaIA.objects.get()
        self.assertEqual(tarea.estado, TareaIA.Estado.INCIERTA)
        self.assertEqual(tarea.intentos.get().error, 'timeout')
        self.assertTrue(PlanificadorIA.reabrir_confirmada(tarea.pk))

    def test_rechazos_de_credencial_y_agotamiento(self):
        self.inferencia.side_effect = [
            ErrorProveedor(Motivo.NO_AUTENTICADO, 'rechazo', 401),
            ErrorProveedor(Motivo.PROHIBIDO, 'rechazo', 403),
        ]
        for ambito in range(2):
            with self.assertRaises(AnalisisNoDisponible):
                self.consulta.con_ambito({}, ambito)
        self.assertEqual(self.cliente.call_count, 2)
        self.assertEqual(CredencialBloqueadaIA.objects.count(), 2)

    def test_calidad_por_operacion_y_latencia_desempatan(self):
        self.perfiles.return_value = {
            'gemini/modelo': {'preguntas': {'calidad': 0.9, 'latencia_ms': 300}},
            'cohere/modelo': {'preguntas': {'calidad': 0.9, 'latencia_ms': 100}},
        }
        self.inferencia.return_value = {'preguntas': []}
        self.consulta({})
        self.assertEqual(self.consulta.ultimo_identificador, 'Cohere/modelo')

    def test_dos_tareas_simultaneas_en_un_proveedor_y_tercera_rechazada(self):
        self.configuracion.return_value = [self.gemini]
        iniciadas = Barrier(3, timeout=10)
        finalizar = Event()

        def responder(*args):
            self.assertFalse(connection.in_atomic_block)
            iniciadas.wait()
            self.assertTrue(finalizar.wait(10))
            return {'preguntas': []}

        self.inferencia.side_effect = responder
        with ThreadPoolExecutor(max_workers=2) as executor:
            futuros = [executor.submit(en_hilo, self.consulta.con_ambito, {}, i) for i in (1, 2)]
            try:
                iniciadas.wait()
                self.assertEqual(IntentoIA.objects.filter(fin__isnull=True).count(), 2)
                with self.assertRaises(TareaEnCurso):
                    self.consulta.con_ambito({}, 1)
                with self.assertRaises(AnalisisNoDisponible):
                    self.consulta.con_ambito({}, 3)
            finally:
                finalizar.set()
            self.assertEqual([f.result(timeout=10) for f in futuros], [[], []])
        self.assertEqual(self.cliente.call_count, 2)

    def test_lote_distribuye_tareas_independientes_y_devuelve_orden_original(self):
        self.politicas['gemini'] = PoliticaCuota(1, {'rpm': 10}, 6000, 200, 0)
        self.politicas['cohere'] = PoliticaCuota(1, {'rpm': 10}, 6000, 200, 0)
        simultaneas = Barrier(2, timeout=10)

        def responder(entrada, *_):
            simultaneas.wait()
            return {'preguntas': [entrada['etiqueta'] + '?']}

        def analizar(etiqueta):
            return self.consulta.con_ambito({'etiqueta': etiqueta}, etiqueta)

        self.inferencia.side_effect = responder
        with override_settings(GUIOS_AI_TRABAJADORES_LOTE=2):
            self.assertEqual(list(en_orden(self.consulta, analizar, ['B', 'A'])), [['B?'], ['A?']])
        self.assertEqual(set(IntentoIA.objects.values_list('proveedor', 'fallback')),
                         {('gemini', False), ('cohere', False)})

    def test_limites_de_ventana_compartidos_entre_modelos(self):
        self.configuracion.return_value = [self.gemini, candidato('groq', unidad='gemini')]
        self.inferencia.return_value = {'preguntas': []}
        for medida, limite, unidades in (
            ('rpm', 1, 0), ('tpm', 6000, 0), ('rpd', 1, 0), ('rp31d', 1, 0), ('unidades_diarias', 3, 3),
        ):
            with self.subTest(medida=medida):
                self.politicas['gemini'] = PoliticaCuota(2, {medida: limite}, 6000, 200, unidades)
                self.consulta.con_ambito({}, [medida, 1])
                with self.assertRaises(AnalisisNoDisponible):
                    self.consulta.con_ambito({}, [medida, 2])
                IntentoIA.objects.all().delete()
        self.assertEqual(self.cliente.call_count, 5)

    def test_reserva_abandonada_libera_capacidad_y_cerca_respuesta_tardia(self):
        self.configuracion.return_value = [self.gemini]
        self.politicas['gemini'] = PoliticaCuota(1, {'rpm': 10}, 6000, 200, 0)
        clave = proveedor_ia._clave_tarea('preguntas', {}, 'abandonada')
        propietario, _ = PlanificadorIA.tomar(clave)
        reserva, _ = PlanificadorIA.reservar(
            clave, propietario, 'preguntas', [self.gemini], self.politicas, {}, 0, False,
        )
        _, _, intento = reserva
        vencida = timezone.now() - timedelta(seconds=2)
        TareaIA.objects.filter(pk=clave).update(vence=vencida)
        IntentoIA.objects.filter(pk=intento).update(vence=vencida)
        self.assertEqual(PlanificadorIA.mantener(), 1)
        with self.assertRaises(TareaIncierta):
            self.consulta.con_ambito({}, 'abandonada')
        self.assertFalse(PlanificadorIA.finalizar(clave, propietario, intento, self.gemini, 3, 4, resultado=[]))
        self.inferencia.return_value = {'preguntas': []}
        self.assertEqual(self.consulta.con_ambito({}, 'otra'), [])

    def test_cierre_erroneo_no_publica_ni_bloquea_la_credencial(self):
        clave = proveedor_ia._clave_tarea('preguntas', {}, 'cierre')
        propietario, _ = PlanificadorIA.tomar(clave)
        reserva, _ = PlanificadorIA.reservar(
            clave, propietario, 'preguntas', [self.gemini], self.politicas, {}, 0, False,
        )
        _, _, intento = reserva
        rechazo = ErrorProveedor(Motivo.NO_AUTENTICADO, 'credencial rechazada')
        otro_modelo = replace(self.gemini, modelo='otro')
        self.assertFalse(PlanificadorIA.finalizar(clave, propietario, intento, otro_modelo, 3, None, rechazo))
        self.assertFalse(PlanificadorIA.finalizar(clave, propietario, intento + 1, self.gemini, 3, 4, resultado=[]))
        self.assertFalse(CredencialBloqueadaIA.objects.exists())
        self.assertIsNone(TareaIA.objects.get(pk=clave).resultado)
        self.assertIsNone(IntentoIA.objects.get(pk=intento).fin)
        self.assertTrue(PlanificadorIA.finalizar(clave, propietario, intento, self.gemini, 3, 4, resultado=[]))

    def test_deduplicacion_en_otro_proceso_con_conexion_propia(self):
        clave = proveedor_ia._clave_tarea('preguntas', {}, 'interproceso')
        PlanificadorIA.tomar(clave)
        script = '''
import sys
import django
from django.conf import settings
settings.DATABASES['default']['NAME'] = sys.argv[1]
django.setup()
from apps.external_services.planificador_ia import PlanificadorIA, TareaEnCurso
try:
    PlanificadorIA.tomar(sys.argv[2])
except TareaEnCurso:
    sys.exit(0)
sys.exit(1)
'''
        proceso = subprocess.run(
            [sys.executable, '-c', script, connection.settings_dict['NAME'], clave],
            capture_output=True, timeout=45,
        )
        self.assertEqual(proceso.returncode, 0, proceso.stderr.decode(errors='replace'))



class ConfiguracionTests(TestCase):
    def test_cloudflare_requiere_cupo_diario_de_neurons(self):
        cloudflare = candidato('cloudflare')
        politica = PoliticaCuota(1, {'rpm': 1}, 6000, 200, 0)
        with patch.object(proveedor_ia, '_leer_proveedores', return_value=[cloudflare]), patch.object(
            proveedor_ia, 'leer_politicas', side_effect=[{'cloudflare': politica}, {}],
        ):
            self.assertFalse(proveedor_ia.configurado())

    def test_registro_adicional_exige_politica_perfil_y_autorizacion_exactos(self):
        hoy = date.today().isoformat()
        primario = 'gemini-3.5-flash-lite'
        candidato = 'gemma-4-26b-a4b-it'
        entradas = [dict(proveedor='gemini', modelo=modelo, plan='gemini-free-tier',
                         fuente_oficial='https://ai.google.dev/gemini-api/docs/pricing',
                         verificado=hoy, vence=hoy, sin_cargos_ni_excedentes=True)
                    for modelo in (primario, candidato)]
        proyecto = {'rpm': 12, 'tpm': 250000, 'rpd': 30, 'concurrencia': 3,
                    'tokens_por_intento': 65536, 'max_tokens_salida': 2048}
        politica = {**proyecto, 'rpm': 30, 'tpm': 16000, 'rpd': 14400,
                    'concurrencia': 1, 'tokens_por_intento': 8192, 'margen_tokens_entrada': 256}
        with TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'autorizacion.json'
            ruta.write_text(json.dumps(entradas), encoding='utf-8')
            with override_settings(
                GUIOS_AI_AUTORIZACION_GRATUITA=ruta,
                GUIOS_AI_GEMINI_API_KEY='ficticia', GUIOS_AI_GEMINI_MODEL=primario,
                GUIOS_AI_GEMINI_OPERACIONES='preguntas', GUIOS_AI_GEMINI_UNIDAD_CUOTA='gemini',
                GUIOS_AI_MODELOS_ADICIONALES=json.dumps({'gemini': {candidato: 'preguntas,suficiencia'}}),
                GUIOS_AI_PERFILES_OPERACION=json.dumps({
                    f'gemini/{modelo}': {'preguntas': {'validado': True}} for modelo in (primario, candidato)
                }),
                GUIOS_AI_POLITICAS_CUOTA=json.dumps({'gemini': proyecto}),
                GUIOS_AI_POLITICAS_MODELO='{}',
            ):
                proveedores, compartidas, _ = proveedor_ia.leer_admision()
                self.assertEqual([p.modelo for p in proveedores], [primario])
                self.assertEqual(compartidas['gemini'].ventanas['tpm'], 250000)
                with override_settings(GUIOS_AI_POLITICAS_MODELO=json.dumps({f'gemini/{candidato}': politica})):
                    proveedores, compartidas, _ = proveedor_ia.leer_admision()
                    self.assertEqual([p.modelo for p in proveedores], [primario, candidato])
                    self.assertEqual(proveedores[0].credencial, proveedores[1].credencial)
                    self.assertEqual(proveedores[1].operaciones, {'preguntas'})
                    self.assertEqual(compartidas['gemini'].ventanas, {'rpm': 12, 'tpm': 16000, 'rpd': 30})
                    ruta.write_text(json.dumps(entradas[:1]), encoding='utf-8')
                    self.assertEqual([p.modelo for p in proveedor_ia.leer_admision()[0]], [primario])

    def test_requiere_modelo_exacto_y_autorizacion_vigente(self):
        hoy = date.today().isoformat()
        entrada = dict(proveedor='gemini', modelo='modelo-gratuito', plan='gemini-free-tier',
                       fuente_oficial='https://ai.google.dev/gemini-api/docs/pricing',
                       verificado=hoy, vence=hoy, sin_cargos_ni_excedentes=True)
        with TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'autorizacion.json'
            ruta.write_text(json.dumps([entrada]), encoding='utf-8')
            with override_settings(GUIOS_AI_AUTORIZACION_GRATUITA=ruta,
                                   GUIOS_AI_GEMINI_API_KEY='ficticia',
                                   GUIOS_AI_GEMINI_MODEL='modelo-gratuito',
                                   GUIOS_AI_GEMINI_OPERACIONES='preguntas',
                                   GUIOS_AI_GROQ_OPERACIONES='',
                                   GUIOS_AI_PERFILES_OPERACION=json.dumps({
                                       'gemini/modelo-gratuito': {'preguntas': {'validado': True}},
                                   }),
                                   GUIOS_AI_POLITICAS_CUOTA=json.dumps({
                                       'gemini': {'rpm': 2, 'rpd': None, 'tpm': None,
                                                  'tokens_por_intento': 6000, 'max_tokens_salida': 200},
                                   })):
                self.assertEqual(proveedor_ia.modelo_activo(), 'Gemini')
                with override_settings(GUIOS_AI_GEMINI_MODEL='modelo-no-autorizado'):
                    self.assertFalse(proveedor_ia.configurado())


class ErroresTests(TestCase):
    def test_transporte_clasifica_http_y_timeout(self):
        cliente = APIJSON('ficticia', 'modelo', 'https://ejemplo.test')
        for fallo, motivo, pausa in (
            (HTTPError('https://ejemplo.test', 401, '', {}, BytesIO()), Motivo.NO_AUTENTICADO, None),
            (HTTPError('https://ejemplo.test', 403, '', {}, BytesIO()), Motivo.PROHIBIDO, None),
            (HTTPError('https://ejemplo.test', 429, '', {'Retry-After': '30'}, BytesIO()), Motivo.CUOTA, 30),
            (HTTPError('https://ejemplo.test', 503, '', {}, BytesIO()), Motivo.SERVIDOR, None),
            (URLError(TimeoutError()), Motivo.TIMEOUT, None),
            (IncompleteRead(b'parcial'), Motivo.RED, None),
        ):
            with self.subTest(motivo=motivo), patch.object(cliente, '_solicitar', side_effect=fallo):
                with self.assertRaises(ErrorProveedor) as ctx:
                    cliente.consultar({}, {}, '')
                self.assertEqual(ctx.exception.motivo, motivo)
                self.assertEqual(ctx.exception.retry_after, pausa)
