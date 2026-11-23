"""Carga documental: se pueden seleccionar varios archivos a la vez."""
from datetime import date
from unittest import mock

from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.data.models import CatalogoVersion, Documento, Evaluacion, Organizacion, Software, Usuario

URL = reverse('presentation:decisor-carga-documental')
PROCESAR = 'apps.presentation.views.documentos.DocumentService.procesar_carga'


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CargaMultipleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        org = Organizacion.objects.create(nombre='Org multi')
        cls.actor = Usuario.objects.create_user('multi@test.local', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cat = CatalogoVersion.objects.create(version='multi', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor, catalogo=cat,
                                           software=Software.objects.create(nombre='Multi SW'))
        Evaluacion.objects.create(organizacion=org, usuario=cls.actor, catalogo=cat,
                                  software=Software.objects.create(nombre='Otra SW'))

    def setUp(self):
        self.client.force_login(self.actor)

    def falso(self, **kw):
        archivo = kw['archivo']
        if archivo.name == 'malo.pdf':
            raise ValidationError('El documento no contiene texto extraíble.')
        return Documento.objects.create(evaluacion=self.ev, usuario=self.actor, nombre=archivo.name, tipo='PDF',
                                        ubicacion=archivo.name, hash_sha256=archivo.name.ljust(64, '0'))

    def subir(self, *nombres):
        archivos = [SimpleUploadedFile(n, b'%PDF-1.4 x', content_type='application/pdf') for n in nombres]
        return self.client.post(URL, {'evaluacion_id': self.ev.pk, 'accion': 'subir', 'archivo': archivos})

    def mensajes(self, r):
        return [str(m) for m in get_messages(r.wsgi_request)]

    def test_el_formulario_acepta_varios_archivos_y_ya_no_ofrece_cambiar_de_evaluacion(self):
        r = self.client.get(URL, {'evaluacion_id': self.ev.pk})
        self.assertContains(r, 'type="file" name="archivo"')
        self.assertContains(r, ' multiple ')
        self.assertNotContains(r, 'Evaluación activa')

    def test_varios_archivos_se_procesan_todos(self):
        with mock.patch(PROCESAR, side_effect=self.falso) as m:
            r = self.subir('a.pdf', 'b.pdf', 'c.pdf')
        self.assertEqual(m.call_count, 3)
        self.assertEqual(Documento.objects.filter(evaluacion=self.ev).count(), 3)
        self.assertNotIn('doc_id', r['Location'])
        self.assertTrue(any('3 documentos procesados' in t for t in self.mensajes(r)))

    def test_si_uno_falla_los_demas_se_cargan_y_se_avisa_cual(self):
        with mock.patch(PROCESAR, side_effect=self.falso):
            r = self.subir('a.pdf', 'malo.pdf', 'c.pdf')
        self.assertEqual(Documento.objects.filter(evaluacion=self.ev).count(), 2)
        textos = self.mensajes(r)
        self.assertTrue(any('«malo.pdf»' in t for t in textos))
        self.assertTrue(any('2 documentos procesados' in t for t in textos))

    def test_un_solo_archivo_sigue_abriendo_su_contenido(self):
        with mock.patch(PROCESAR, side_effect=self.falso):
            r = self.subir('a.pdf')
        self.assertIn('doc_id=', r['Location'])
