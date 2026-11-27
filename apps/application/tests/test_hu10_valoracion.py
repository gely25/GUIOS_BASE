from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.application.services.ai import AIService
from apps.application.services.lotes_hu09 import LotesHU09Service
from apps.application.services.pm_foda import PmFodaService
from apps.application.services.preparacion_hu10 import PreparacionHU10Service
from apps.application.services.preguntas import PreguntasService
from apps.application.services.revision_humana import RevisionHumanaService
from apps.application.services.suficiencia import SuficienciaService
from apps.external_services.tests.fixtures_ia import IAConfiguradaPruebas
from apps.data.models import (
    AnalisisSuficiencia,
    CatalogoVersion,
    Dimension,
    Documento,
    Evaluacion,
    EvaluacionFactor,
    Evidencia,
    Factor,
    FragmentoDocumento,
    Organizacion,
    ResultadoEvaluacion,
    Software,
    Subfactor,
    Usuario,
    ValoracionSubfactor,
)
from apps.external_services.ai_errors import AnalisisNoDisponible


@override_settings(
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    GUIOS_AI_GEMINI_API_KEY='test-gemini-key',
    GUIOS_AI_GEMINI_MODEL='test-gemini-model',
)
class HU10ValoracionTests(IAConfiguradaPruebas, TestCase):
    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre='Organización HU10')
        cls.actor = Usuario.objects.create_user('decisor@hu10.test', 'Clave-test-123', nombre='Jorge', organizacion=org)
        cat = CatalogoVersion.objects.create(version='v1-hu10', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(
            organizacion=org,
            usuario=cls.actor,
            software=Software.objects.create(nombre='LibreOffice'),
            catalogo=cat,
        )
        dim = Dimension.objects.create(nombre='Tecnológica')
        factor = Factor.objects.create(dimension=dim, nombre='Interoperabilidad', alcance=Factor.EXTERNO)
        ef = EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=factor, importancia_relativa=4)
        subfactor = Subfactor.objects.create(factor=factor, descripcion='Soporte de formatos abiertos ODF')
        cls.val = ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=subfactor)

        doc = Documento.objects.create(
            evaluacion=cls.ev,
            usuario=cls.actor,
            nombre='manual_tecnico.pdf',
            tipo='PDF',
            ubicacion='evaluaciones/1/manual_tecnico.pdf',
        )
        frag = FragmentoDocumento.objects.create(
            documento=doc,
            pagina=4,
            contenido='Soporte nativo completo para ISO/IEC 26300 (ODF 1.3).',
        )
        cls.evidencia = Evidencia.objects.create(
            valoracion=cls.val,
            fragmento=frag,
            referencia='Página 4 · Sección 2.1',
        )

    def _habilitar_subfactor(self):
        SuficienciaService.analizar(
            self.actor,
            self.ev.pk,
            self.val.pk,
            lambda _: {
                'estado': 'SUFICIENTE',
                'justificacion': 'El documento acredita soporte nativo ODF 1.3.',
                'referencias': [f'E:{self.evidencia.pk}'],
                'preguntas': [],
            },
            'qwen2.5:1.5b',
        )

    def _proponer_cuatro(self):
        self._habilitar_subfactor()
        return AIService.generar_propuesta_preliminar(self.actor, self.ev.pk, self.val.pk, lambda _: {
            'valor_preliminar': 4, 'justificacion': 'La fuente declara soporte ODF.',
            'referencias': [f'E:{self.evidencia.pk}'],
        })

    def _decidir(self, modo, valor):
        fila = RevisionHumanaService.obtener(self.actor, self.ev.pk, self.val.pk)
        return RevisionHumanaService.resolver(
            self.actor, self.ev.pk, self.val.pk, modo, valor, 'Decisión explícita del piloto.', fila['version'],
        )

    def _resultado(self):
        factor = EvaluacionFactor.objects.get(pk=self.val.evaluacion_factor_id)
        texto = ResultadoEvaluacion.objects.filter(evaluacion=self.ev).values_list('recomendacion', flat=True).first()
        return factor.ponderacion_media, factor.clasificacion_foda, texto

    def test_integracion_hu09_hu10_hu11_hu12_y_reapertura(self):
        self.assertEqual(connection.vendor, 'postgresql')
        pregunta, = PreguntasService.registrar_vacios(
            self.actor, self.ev.pk, self.val.pk, ['¿Se exporta a ODF?'],
        )
        PreguntasService.responder(self.actor, self.ev.pk, pregunta.pk, 'Sí, en la edición probada.')
        self.assertFalse(PmFodaService.vista_previa(self.actor, self.ev.pk)['lista'])
        self.assertEqual(self._resultado(), (None, None, None))
        self._proponer_cuatro()
        with self.assertRaisesMessage(ValidationError, 'Faltan valoraciones confirmadas'):
            PmFodaService.calcular_y_guardar(self.actor, self.ev.pk)
        self.assertEqual(self._resultado(), (None, None, None))

        self._decidir('CONFIRMAR', 4)
        PmFodaService.calcular_y_guardar(self.actor, self.ev.pk)
        self.assertEqual(self._resultado(), (Decimal('4.00'), 'Oportunidad', 'Adoptar el FLOSS seleccionado'))
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.estado, Evaluacion.CERRADA)
        self.assertIsNotNone(self.ev.fecha_fin)
        with self.assertRaisesMessage(ValidationError, 'La evaluación no admite cambios'):
            PreguntasService.responder(self.actor, self.ev.pk, pregunta.pk, 'Otra respuesta.')
        with self.assertRaisesMessage(ValidationError, 'La evaluación no admite cambios'):
            self._decidir('MODIFICAR', 1)

        fila = RevisionHumanaService.obtener(self.actor, self.ev.pk, self.val.pk)
        evento = RevisionHumanaService.reabrir(self.actor, self.ev.pk, self.val.pk, 'Corregir decisión.', fila['version'])
        self.assertEqual(evento.resultados_anteriores['factores'][0]['ponderacion_media'], '4.00')
        self.assertEqual(self._resultado(), (None, None, None))
        self._decidir('MODIFICAR', 1)
        self.val.refresh_from_db()
        self.assertEqual((self.val.valor_ia, self.val.valor_confirmado), (4, 1))
        PmFodaService.calcular_y_guardar(self.actor, self.ev.pk)
        self.assertEqual(self._resultado(), (
            Decimal('1.00'), 'Amenaza', 'Se sugiere analizar la adopción y debería ser pospuesta',
        ))

    def test_integracion_cambio_de_evidencia_en_evaluacion_reabierta(self):
        self._proponer_cuatro()
        self._decidir('CONFIRMAR', 4)
        PmFodaService.calcular_y_guardar(self.actor, self.ev.pk)
        fragmento = FragmentoDocumento.objects.create(
            documento=self.evidencia.fragmento.documento, pagina=5,
            contenido='La edición evaluada excluye la exportación a ODF.',
        )
        self.client.force_login(self.actor)
        url = reverse('presentation:decisor-carga-documental')
        cambio = {
            'accion': 'vincular_evidencia', 'fragmento_id': fragmento.pk, 'valoracion_id': self.val.pk,
        }
        self.client.post(f'{url}?evaluacion_id={self.ev.pk}', cambio)
        self.assertFalse(Evidencia.objects.filter(valoracion=self.val, fragmento=fragmento).exists())
        self.assertEqual(self._resultado(), (Decimal('4.00'), 'Oportunidad', 'Adoptar el FLOSS seleccionado'))

        fila = RevisionHumanaService.obtener(self.actor, self.ev.pk, self.val.pk)
        RevisionHumanaService.reabrir(self.actor, self.ev.pk, self.val.pk, 'Revisar evidencia.', fila['version'])
        self.assertEqual(self._resultado(), (None, None, None))
        respuesta = self.client.post(f'{url}?evaluacion_id={self.ev.pk}', cambio)
        self.assertEqual(respuesta.status_code, 302)
        fila, = PreparacionHU10Service.obtener(self.actor, self.ev.pk)['subfactores']
        self.assertEqual(fila['estado'], 'ANALISIS_PENDIENTE')
        self.val.refresh_from_db()
        self.assertIsNone(self.val.valor_ia)
        with self.assertRaises(ValidationError):
            self._decidir('CONFIRMAR', 4)
        self.assertFalse(PmFodaService.vista_previa(self.actor, self.ev.pk)['lista'])
        self.assertEqual(self._resultado(), (None, None, None))

    def test_rechaza_subfactor_no_habilitado(self):
        with self.assertRaises(ValidationError):
            AIService.generar_propuesta_preliminar(
                self.actor,
                self.ev.pk,
                self.val.pk,
                lambda _: {'valor_preliminar': 4, 'justificacion': 'Cumple.', 'referencias': [f'E:{self.evidencia.pk}']},
            )

    def test_rechaza_referencia_inexistente_del_modelo(self):
        self._habilitar_subfactor()
        with self.assertRaises(AnalisisNoDisponible):
            AIService.generar_propuesta_preliminar(
                self.actor,
                self.ev.pk,
                self.val.pk,
                lambda _: {'valor_preliminar': 4, 'justificacion': 'Cumple.', 'referencias': ['E:99999']},
            )
        self.val.refresh_from_db()
        self.assertIsNone(self.val.valor_ia)

    def test_genera_y_guarda_propuesta_para_hu11(self):
        self._habilitar_subfactor()
        resultado = AIService.generar_propuesta_preliminar(
            self.actor,
            self.ev.pk,
            self.val.pk,
            lambda _: {
                'valor_preliminar': 4,
                'justificacion': 'Cumple plenamente con estándares abiertos ISO/IEC 26300.',
                'referencias': [f'E:{self.evidencia.pk}'],
            },
        )
        self.assertEqual(resultado['valor_ia'], 4)
        self.val.refresh_from_db()
        self.assertEqual(self.val.valor_ia, 4)
        self.assertIn(f'E:{self.evidencia.pk}', self.val.justificacion_ia)
        self.assertEqual(self.val.estado_validacion, ValoracionSubfactor.PENDIENTE)
        self.assertIsNone(self.val.valor_confirmado)

        # HU11 recibe la propuesta original intacta
        seleccion_hu11 = RevisionHumanaService.obtener(self.actor, self.ev.pk, self.val.pk)
        self.assertEqual(seleccion_hu11['valor_ia'], 4)
        self.assertIn('ISO/IEC 26300', seleccion_hu11['justificacion_ia'])

    def test_flujo_web_hu10_y_enlace_a_hu11(self):
        self._habilitar_subfactor()
        self.client.force_login(self.actor)
        url = reverse('presentation:decisor-revision-valoraciones')
        with patch('apps.presentation.views.preguntas.obtener_proveedor') as obtener:
            proveedor = obtener.return_value
            proveedor.return_value = {
                'valor_preliminar': 3,
                'justificacion': 'Cumple parcialmente según la evidencia documental.',
                'referencias': [f'E:{self.evidencia.pk}'],
            }
            resp = self.client.post(url, {'evaluacion': self.ev.pk, 'valoracion': self.val.pk, 'accion': 'valorar_hu10'})
            self.assertEqual(resp.status_code, 302)
            obtener.assert_called_once_with('valoracion')
            proveedor.assert_called_once()

        pagina = self.client.get(url, {'evaluacion': self.ev.pk})
        self.assertContains(pagina, 'Propuesta preliminar de IA: 3/4')
        self.assertContains(pagina, 'Ver en documento (comprobar ubicación)')

    def test_repetir_la_misma_propuesta_no_duplica_la_escritura(self):
        self._habilitar_subfactor()

        def proveedor(_):
            return {'valor_preliminar': 4, 'justificacion': 'Cumple.',
                    'referencias': [f'E:{self.evidencia.pk}']}

        with CaptureQueriesContext(connection) as consultas:
            for _ in range(2):
                AIService.generar_propuesta_preliminar(self.actor, self.ev.pk, self.val.pk, proveedor)
        actualizaciones = [q for q in consultas.captured_queries
                           if q['sql'].startswith(f'UPDATE "{ValoracionSubfactor._meta.db_table}"')
                           and '"valor_ia"' in q['sql']]
        self.assertEqual(len(actualizaciones), 1)

    def test_sondeo_habilita_hu10_tras_finalizar_hu09_y_el_doble_envio_no_repite_inferencia(self):
        self.client.force_login(self.actor)
        url = reverse('presentation:decisor-revision-valoraciones')
        lote = LotesHU09Service.encolar(self.actor, self.ev.pk)
        parametros = {'evaluacion': self.ev.pk, 'estado_lote': '1'}
        pagina = self.client.get(url, {'evaluacion': self.ev.pk})
        self.assertContains(pagina, 'id="hu10-lote-form" data-disponible="0"')
        self.assertContains(pagina, 'Esperando a que termine el análisis de suficiencia.')
        self.assertContains(pagina, 'Generar propuestas pendientes')
        with patch.object(PreguntasService, '_contexto', side_effect=AssertionError('No reconstruir en cada sondeo')):
            cola = self.client.get(url, parametros)
        self.assertEqual(cola.json()['lote']['estado'], 'EN_COLA')
        self.assertEqual(cola.json()['lote']['etiqueta_estado'], 'En cola')
        self.assertIsNone(cola.json()['hu10'])

        LotesHU09Service.procesar(LotesHU09Service.tomar(), lambda _: {
            'estado': 'SUFICIENTE', 'justificacion': 'El documento acredita ODF 1.3.',
            'referencias': [f'E:{self.evidencia.pk}'], 'preguntas': [],
        }, 'mock')
        final = self.client.get(url, parametros)
        self.assertEqual(final['Cache-Control'], 'no-store')
        self.assertEqual(final.json()['lote']['estado'], 'FINALIZADO')
        self.assertEqual(final.json()['lote']['etiqueta_estado'], 'Finalizado')
        self.assertEqual(final.json()['lote']['id'], lote.pk)
        self.assertEqual(final.json()['hu10'], {
            'habilitados': 1, 'pendientes': 1, 'generadas': 0, 'disponible': True,
            'filas': {str(self.val.pk): {'etiqueta': 'Contexto disponible para propuesta preliminar',
                                        'disponible': True}},
        })

        with patch('apps.presentation.views.preguntas.obtener_proveedor') as obtener:
            obtener.return_value.return_value = {
                'valor_preliminar': 4, 'justificacion': 'ODF confirmado.',
                'referencias': [f'E:{self.evidencia.pk}'],
            }
            datos = {'evaluacion': self.ev.pk, 'accion': 'valorar_hu10_lote'}
            self.assertEqual(self.client.post(url, datos).status_code, 302)
            self.assertEqual(self.client.post(url, datos).status_code, 302)
            obtener.return_value.assert_called_once()

        cerrado = self.client.get(url, parametros)
        self.assertEqual(cerrado.json()['hu10']['pendientes'], 0)
        self.assertEqual(cerrado.json()['hu10']['generadas'], 1)
        self.assertFalse(cerrado.json()['hu10']['disponible'])
        self.val.refresh_from_db()
        self.assertIsNone(self.val.valor_confirmado)
        self.assertEqual(self.val.estado_validacion, ValoracionSubfactor.PENDIENTE)

    def test_contexto_obsoleto_no_habilita_lote_ni_envia_solicitud(self):
        self._habilitar_subfactor()
        self.client.force_login(self.actor)
        url = reverse('presentation:decisor-revision-valoraciones')
        FragmentoDocumento.objects.filter(pk=self.evidencia.fragmento_id).update(contenido='Evidencia modificada.')
        r = self.client.get(url, {'evaluacion': self.ev.pk, 'estado_lote': 1})
        self.assertFalse(r.json()['hu10']['disponible'])
        with patch('apps.presentation.views.preguntas.obtener_proveedor') as obtener:
            self.assertEqual(self.client.post(url, {
                'evaluacion': self.ev.pk, 'accion': 'valorar_hu10_lote',
            }).status_code, 302)
        obtener.return_value.assert_not_called()

    def test_cambio_de_suficiencia_sin_cambiar_evidencia_no_persiste_hu10(self):
        self._habilitar_subfactor()

        def proveedor(_):
            AnalisisSuficiencia.objects.filter(valoracion=self.val).update(justificacion='Conclusión revisada.')
            return {'valor_preliminar': 4, 'justificacion': 'Cumple.',
                    'referencias': [f'E:{self.evidencia.pk}']}

        with self.assertRaisesMessage(ValidationError, 'La suficiencia o las fuentes cambiaron'):
            AIService.generar_propuesta_preliminar(self.actor, self.ev.pk, self.val.pk, proveedor)
        self.val.refresh_from_db()
        self.assertIsNone(self.val.valor_ia)

    def test_detecta_cambio_de_contexto_antes_de_guardar(self):
        self._habilitar_subfactor()

        def proveedor_que_muta_contexto(_):
            PreguntasService.registrar_vacios(self.actor, self.ev.pk, self.val.pk, ['¿Se soporta ODF 1.4?'])
            return {
                'valor_preliminar': 4,
                'justificacion': 'Cumple.',
                'referencias': [f'E:{self.evidencia.pk}'],
            }

        with self.assertRaises(ValidationError):
            AIService.generar_propuesta_preliminar(self.actor, self.ev.pk, self.val.pk, proveedor_que_muta_contexto)
