"""Carga documental: visor de PDF en la propia pantalla y renombrar documentos."""
import tempfile
from datetime import date
from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.data.models import CatalogoVersion, Documento, Evaluacion, Organizacion, Software, Usuario

URL = reverse('presentation:decisor-carga-documental')
TMP = tempfile.mkdtemp()


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], MEDIA_ROOT=TMP)
class VisorYRenombrarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        org = Organizacion.objects.create(nombre='Org visor')
        cls.actor = Usuario.objects.create_user('visor@test.local', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cat = CatalogoVersion.objects.create(version='visor', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor, catalogo=cat,
                                           software=Software.objects.create(nombre='Visor SW'))
        cls.otra = Evaluacion.objects.create(organizacion=org, usuario=cls.actor, catalogo=cat,
                                             software=Software.objects.create(nombre='Otra SW'))
        Path(TMP, 'guia.pdf').write_bytes(b'%PDF-1.4 prueba')
        cls.pdf = Documento.objects.create(evaluacion=cls.ev, usuario=cls.actor, nombre='Guía.pdf', tipo='PDF', ubicacion='guia.pdf')
        cls.docx = Documento.objects.create(evaluacion=cls.ev, usuario=cls.actor, nombre='Política.docx', tipo='DOCX', ubicacion='p.docx')
        cls.ajeno = Documento.objects.create(evaluacion=cls.otra, usuario=cls.actor, nombre='Ajeno.pdf', tipo='PDF', ubicacion='guia.pdf')

    def setUp(self):
        self.client.force_login(self.actor)

    def post(self, doc, nombre):
        return self.client.post(URL, {'evaluacion_id': self.ev.pk, 'accion': 'renombrar',
                                      'documento_id': doc.pk, 'nombre': nombre})

    def test_la_tabla_ya_no_ofrece_ver_contenido(self):
        r = self.client.get(URL, {'evaluacion_id': self.ev.pk})
        self.assertNotContains(r, 'title="Ver contenido"')
        self.assertNotContains(r, 'id="cd-visor"')
        self.assertContains(r, 'title="Eliminar"', count=2)
        self.assertContains(r, 'js-renombrar')

    def test_renombrar_conserva_la_extension(self):
        self.post(self.pdf, 'Ficha técnica')
        self.pdf.refresh_from_db()
        self.assertEqual(self.pdf.nombre, 'Ficha técnica.pdf')
        self.assertEqual(self.pdf.ubicacion, 'guia.pdf')  # el archivo no se toca

    def test_renombrar_no_duplica_la_extension_ni_acepta_rutas(self):
        self.post(self.pdf, '../Costos.PDF')
        self.pdf.refresh_from_db()
        self.assertEqual(self.pdf.nombre, 'Costos.PDF')

    def test_renombrar_rechaza_vacio_y_ajenos(self):
        self.post(self.pdf, '   ')
        self.pdf.refresh_from_db()
        self.assertEqual(self.pdf.nombre, 'Guía.pdf')
        r = self.post(self.ajeno, 'Hack')
        self.assertEqual(r.status_code, 404)
        self.ajeno.refresh_from_db()
        self.assertEqual(self.ajeno.nombre, 'Ajeno.pdf')