"""Paso 4: cobertura de evidencia, preguntas automáticas de los subfactores sin evidencia y subida desde la revisión."""
import json
from datetime import date
from unittest import mock

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.data.models import (CatalogoVersion, Dimension, Documento, Evaluacion, EvaluacionFactor, Evidencia, Factor,
    FragmentoDocumento, Organizacion, PreguntaComplementaria, Software, Subfactor, Usuario, ValoracionSubfactor)

URL = reverse('presentation:decisor-revision-valoraciones')
CARGA = reverse('presentation:decisor-carga-documental')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RevisionFaltantesTests(TestCase):
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
        self.assertContains(r, 'id="hu11-evstrip"')
        self.assertEqual((r.context['n_con_evidencia'], r.context['n_sin_evidencia']), (1, 1))
        self.assertContains(r, 'Evidencia (1)')
        self.assertContains(r, 'hu11-evc--no')
        self.assertContains(r, 'value="preparar_faltantes_hu11"')
        self.assertContains(r, 'id="hu11-filtro-ev"')

    def test_estado_vacio_nuevo_conserva_el_texto_y_ofrece_acciones(self):
        r = self.client.get(URL, {'etapa': 'validacion', 'evaluacion': self.ev.pk, 'valoracion': self.v2.pk})
        self.assertContains(r, 'Ningún pasaje de sus documentos se relacionó con este subfactor.')
        self.assertContains(r, 'Sus documentos no respaldan este subfactor todavía')
        self.assertContains(r, 'data-hu11-subir')

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
        self.assertContains(r, 'Solo declaración')

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
        self.assertEqual(r['Location'], f'{URL}?etapa=validacion&evaluacion={self.ev.pk}')
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
