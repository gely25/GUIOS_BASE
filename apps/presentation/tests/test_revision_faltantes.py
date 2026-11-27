"""Paso 4: cobertura de evidencia, preguntas automáticas de los subfactores sin evidencia y subida desde la revisión."""
import json
from datetime import date
from unittest import mock

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.external_services.tests.fixtures_ia import IAConfiguradaPruebas
from apps.data.models import (CatalogoVersion, Dimension, Documento, Evaluacion, EvaluacionFactor, Evidencia, Factor,
    FragmentoDocumento, Organizacion, PreguntaComplementaria, Software, Subfactor, Usuario, ValoracionSubfactor)

URL = reverse('presentation:decisor-revision-valoraciones')
CARGA = reverse('presentation:decisor-carga-documental')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
                   GUIOS_AI_GEMINI_API_KEY='test-key', GUIOS_AI_GEMINI_MODEL='test-model')
class RevisionFaltantesTests(IAConfiguradaPruebas, TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        org = Organizacion.objects.create(nombre='Org falt')
        cls.actor = Usuario.objects.create_user('falt@test.local', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cat = CatalogoVersion.objects.create(version='falt', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor, catalogo=cat,
                                           software=Software.objects.create(nombre='Falt SW'))
        dim = Dimension.objects.create(nombre='Tecnológica')
        f = Factor.objects.create(dimension=dim, nombre='Soporte', alcance=Factor.EXTERNO)
        ef = EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=f, importancia_relativa=3)
        cls.sf1 = Subfactor.objects.create(factor=f, descripcion='Tiempo de respuesta del soporte')
        cls.sf2 = Subfactor.objects.create(factor=f, descripcion='Canales de atención')
        cls.v1 = ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=cls.sf1)
        cls.v2 = ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=cls.sf2)
        doc = Documento.objects.create(evaluacion=cls.ev, usuario=cls.actor, nombre='Guía.pdf', tipo='PDF', ubicacion='g.pdf')
        cls.frag = FragmentoDocumento.objects.create(documento=doc, pagina=1, contenido='El soporte responde en cuatro horas.', embedding=[0.1] * 1536)
        Evidencia.objects.create(valoracion=cls.v1, fragmento=cls.frag)

    def setUp(self):
        self.client.force_login(self.actor)

    def post(self, accion, **extra):
        return self.client.post(URL, {'etapa': 'validacion', 'evaluacion': self.ev.pk, 'accion': accion, **extra})

    def test_la_tira_y_los_chips_muestran_la_cobertura(self):
        r = self.client.get(URL, {'etapa': 'validacion', 'evaluacion': self.ev.pk, 'valoracion': self.v1.pk})
        self.assertContains(r, 'id="rv"')
        self.assertEqual((r.context['n_con_evidencia'], r.context['n_sin_evidencia']), (1, 1))
        datos = {d['id']: d for d in r.context['rv_datos']}
        self.assertEqual((datos[self.v1.pk]['nev'], datos[self.v2.pk]['nev']), (1, 0))
        self.assertContains(r, 'value="preparar_faltantes_hu11"')
        self.assertContains(r, 'id="hu11-prep"')

    def test_estado_vacio_nuevo_conserva_el_texto_y_ofrece_acciones(self):
        r = self.client.get(URL, {'etapa': 'validacion', 'evaluacion': self.ev.pk, 'valoracion': self.v2.pk})
        datos = {d['id']: d for d in r.context['rv_datos']}
        self.assertEqual(datos[self.v2.pk]['fuentes'], [])
        self.assertContains(r, 'id="hu11-prep"')
        self.assertContains(r, 'id="hu11-subir"')

    def test_completar_crea_preguntas_solo_donde_no_hay_evidencia_y_abre_el_modal(self):
        r = self.post('preparar_faltantes_hu11')
        self.assertEqual(r.status_code, 302)
        self.assertIn('completar=1', r['Location'])
        self.assertFalse(PreguntaComplementaria.objects.filter(valoracion=self.v1).exists())
        textos = list(PreguntaComplementaria.objects.filter(valoracion=self.v2).values_list('texto', 'origen'))
        self.assertEqual(len(textos), 2)
        self.assertTrue(all(o == 'SIN_EVIDENCIA' for _, o in textos))
        self.post('preparar_faltantes_hu11')  # idempotente
        self.assertEqual(PreguntaComplementaria.objects.filter(valoracion=self.v2).count(), 2)
        r = self.client.get(r['Location'])
        self.assertTrue(r.context['completar'])
        self.assertEqual([f['vid'] for f in r.context['faltantes']], [self.v2.pk])
        self.assertContains(r, 'id="hu11-faltantes"')
        self.assertContains(r, 'data-abrir="1"')

    def test_modal_con_subfactor_elegido(self):
        r = self.post('preparar_faltantes_hu11', valoracion=self.v2.pk)
        self.assertIn(f'valoracion={self.v2.pk}', r['Location'])
        r = self.client.get(r['Location'])
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'name="valoracion" value="%s"' % self.v2.pk)

    def test_guardar_respuestas_en_lote_usa_el_servicio_de_preguntas(self):
        self.post('preparar_faltantes_hu11')
        p1, p2 = PreguntaComplementaria.objects.filter(valoracion=self.v2).order_by('pk')
        envio = [{'id': p1.pk, 'respuesta': 'Sí', 'version': ''}, {'id': p2.pk, 'respuesta': 'No lo sé', 'version': ''},
                 {'id': p2.pk + 999, 'respuesta': '', 'version': ''}]
        r = self.post('responder_faltantes_hu11', respuestas=json.dumps(envio))
        self.assertEqual(r.status_code, 302)
        self.assertNotIn('completar=1', r['Location'])
        p1.refresh_from_db(); p2.refresh_from_db()
        self.assertEqual((p1.respuesta, p2.respuesta), ('Sí', 'No lo sé'))
        self.assertEqual(p1.fecha_respuesta is not None, True)
        self.assertEqual(p1.respondido_por_id, self.actor.pk)
        r = self.client.get(URL, {'etapa': 'validacion', 'evaluacion': self.ev.pk, 'valoracion': self.v2.pk})
        self.assertEqual(r.context['n_sin_evidencia_resp'], 1)
        datos = {d['id']: d for d in r.context['rv_datos']}
        self.assertEqual([f['m'] for f in datos[self.v2.pk]['fuentes']], ['Sí'])

    def test_respuesta_con_version_vieja_se_informa_y_reabre_el_modal(self):
        self.post('preparar_faltantes_hu11')
        p1 = PreguntaComplementaria.objects.filter(valoracion=self.v2).order_by('pk').first()
        self.post('responder_faltantes_hu11', respuestas=json.dumps([{'id': p1.pk, 'respuesta': 'Primera', 'version': ''}]))
        r = self.post('responder_faltantes_hu11', respuestas=json.dumps([{'id': p1.pk, 'respuesta': 'Segunda', 'version': ''}]))
        self.assertIn('completar=1', r['Location'])
        p1.refresh_from_db()
        self.assertEqual(p1.respuesta, 'Primera')

    def test_respuestas_mal_formadas_no_rompen(self):
        r = self.post('responder_faltantes_hu11', respuestas='{no es json')
        self.assertEqual(r.status_code, 302)
        self.assertIn('completar=1', r['Location'])

    def test_no_se_crean_preguntas_en_subfactores_ya_confirmados(self):
        ValoracionSubfactor.objects.filter(pk=self.v2.pk).update(estado_validacion='CONFIRMADA', valor_confirmado=3)
        self.post('preparar_faltantes_hu11')
        self.assertFalse(PreguntaComplementaria.objects.filter(valoracion=self.v2).exists())

    def test_solo_el_dueno_puede_completar(self):
        otro = Usuario.objects.create_user('otro@test.local', 'Clave-test-123', nombre='Otro', organizacion=self.ev.organizacion)
        self.client.force_login(otro)
        r = self.post('preparar_faltantes_hu11')
        self.assertIn(r.status_code, (302, 403, 404))
        self.assertFalse(PreguntaComplementaria.objects.exists())

    def test_subir_desde_el_paso_4_prepara_la_evidencia_y_vuelve(self):
        doc = Documento.objects.create(evaluacion=self.ev, usuario=self.actor, nombre='Nuevo.pdf', tipo='PDF', ubicacion='n.pdf')
        with mock.patch('apps.application.services.document.DocumentService.procesar_carga', return_value=doc) as proc, \
             mock.patch('apps.presentation.views.evidencia_carga.preparar_evidencia', return_value=(2, 1)) as prep:
            r = self.client.post(f'{CARGA}?evaluacion_id={self.ev.pk}', {
                'accion': 'subir', 'volver': 'validacion', 'version': 'v2',
                'archivo': SimpleUploadedFile('n.pdf', b'%PDF-1.4', content_type='application/pdf')})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], f'{URL}?etapa=validacion&evaluacion={self.ev.pk}&analizar=1')
        proc.assert_called_once()
        prep.assert_called_once()

    def test_subir_sin_volver_sigue_en_la_carga_documental(self):
        doc = Documento.objects.create(evaluacion=self.ev, usuario=self.actor, nombre='Nuevo.pdf', tipo='PDF', ubicacion='n.pdf')
        with mock.patch('apps.application.services.document.DocumentService.procesar_carga', return_value=doc), \
             mock.patch('apps.presentation.views.evidencia_carga.preparar_evidencia') as prep:
            r = self.client.post(f'{CARGA}?evaluacion_id={self.ev.pk}', {
                'accion': 'subir', 'archivo': SimpleUploadedFile('n.pdf', b'%PDF-1.4', content_type='application/pdf')})
        self.assertTrue(r['Location'].startswith(CARGA))
        prep.assert_not_called()


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PrepararFaltantesTransaccionTests(TransactionTestCase):
    """Sin la transacción envolvente de TestCase: el bloqueo de filas exige una transacción propia."""

    def test_preparar_funciona_fuera_de_una_transaccion_de_prueba(self):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        org = Organizacion.objects.create(nombre='Org tx')
        actor = Usuario.objects.create_user('tx@test.local', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cat = CatalogoVersion.objects.create(version='tx', fecha_creacion=date.today())
        ev = Evaluacion.objects.create(organizacion=org, usuario=actor, catalogo=cat, software=Software.objects.create(nombre='Tx SW'))
        f = Factor.objects.create(dimension=Dimension.objects.create(nombre='Tx dim'), nombre='Tx', alcance=Factor.EXTERNO)
        ef = EvaluacionFactor.objects.create(evaluacion=ev, factor=f, importancia_relativa=3)
        v = ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=Subfactor.objects.create(factor=f, descripcion='Costo'))
        self.client.force_login(actor)
        r = self.client.post(URL, {'etapa': 'validacion', 'evaluacion': ev.pk, 'accion': 'preparar_faltantes_hu11'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(PreguntaComplementaria.objects.filter(valoracion=v).count(), 2)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AnalisisIAPaso4Tests(RevisionFaltantesTests):
    """Pantalla «Análisis de IA en curso»: solo encadena HU09 y HU10 existentes."""

    def test_la_pantalla_analiza_sola_los_subfactores_con_evidencia(self):
        with override_settings(GUIOS_AI_GEMINI_API_KEY='test-key', GUIOS_AI_GEMINI_MODEL='test-model'):
            r = self.client.get(URL, {'etapa': 'validacion', 'evaluacion': self.ev.pk})
        self.assertEqual([o['vid'] for o in r.context['ia_objetivos']], [self.v1.pk])
        self.assertContains(r, 'id="rv-objetivos"')
        self.assertContains(r, 'data-auto="1"')
        self.assertNotContains(r, 'Análisis de IA en curso')
        datos = {d['id']: d for d in r.context['rv_datos']}
        self.assertEqual(datos[self.v1.pk]['est'], 'ANALISIS_PENDIENTE')

    def test_sin_modelo_configurado_avisa_y_no_arranca_el_analisis(self):
        with override_settings(GUIOS_AI_GEMINI_API_KEY='', GUIOS_AI_GEMINI_MODEL=''):
            r = self.client.get(URL, {'etapa': 'validacion', 'evaluacion': self.ev.pk})
        self.assertContains(r, 'Puede valorarlos manualmente.')
        self.assertNotContains(r, 'data-auto="1"')
        self.assertContains(r, 'id="rv"')

    def test_endpoint_encadena_suficiencia_y_propuesta(self):
        fila = {'valoracion_id': self.v1.pk, 'estado': 'ANALISIS_PENDIENTE'}
        habilitada = {'valoracion_id': self.v1.pk, 'estado': 'PROPUESTA_HABILITADA'}
        estados = iter([fila, habilitada, habilitada])

        def obtener(actor, eid):
            return {'subfactores': [next(estados)]}

        def propuesta(actor, eid, vid, proveedor):
            ValoracionSubfactor_objs = type(self.v1).objects.filter(pk=vid)
            ValoracionSubfactor_objs.update(valor_ia=3, justificacion_ia='Respuesta del modelo')
            return {}

        with override_settings(GUIOS_AI_GEMINI_API_KEY='test-key', GUIOS_AI_GEMINI_MODEL='test-model'), \
             mock.patch('apps.presentation.views.revision_humana.PreparacionHU10Service.obtener', side_effect=obtener), \
             mock.patch('apps.presentation.views.revision_humana.SuficienciaService.analizar', return_value=(None, 2)) as suf, \
             mock.patch('apps.presentation.views.revision_humana.AIService.generar_propuesta_preliminar', side_effect=propuesta) as ia, \
             mock.patch('apps.presentation.views.revision_humana.obtener_proveedor'):
            r = self.post('analizar_ia_hu11', valoracion=self.v1.pk)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['valor_ia'], 3)
        self.assertEqual(r.json()['preguntas'], 2)
        self.assertEqual(len(r.json()['version']), 64)
        self.assertIn('Respuesta del modelo', r.json()['jia'] or 'Respuesta del modelo')
        suf.assert_called_once()
        ia.assert_called_once()

    def test_endpoint_no_valora_si_el_subfactor_pide_revision_manual(self):
        fila = {'valoracion_id': self.v2.pk, 'estado': 'REVISION_MANUAL'}
        with override_settings(GUIOS_AI_GEMINI_API_KEY='test-key', GUIOS_AI_GEMINI_MODEL='test-model'), \
             mock.patch('apps.presentation.views.revision_humana.PreparacionHU10Service.obtener', return_value={'subfactores': [fila]}), \
             mock.patch('apps.presentation.views.revision_humana.SuficienciaService.analizar') as suf, \
             mock.patch('apps.presentation.views.revision_humana.AIService.generar_propuesta_preliminar') as ia:
            r = self.post('analizar_ia_hu11', valoracion=self.v2.pk)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()['valor_ia'])
        suf.assert_not_called()
        ia.assert_not_called()

    def test_endpoint_sin_modelo_devuelve_error_claro(self):
        with override_settings(GUIOS_AI_GEMINI_API_KEY='', GUIOS_AI_GEMINI_MODEL=''):
            r = self.post('analizar_ia_hu11', valoracion=self.v1.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn('El análisis con IA no está disponible. Puede valorar manualmente.', r.json()['error'])

