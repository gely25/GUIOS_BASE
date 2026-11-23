"""Paginación de 5 en 5 de los documentos y versión de la carga elegida entre etiquetas."""
from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.data.models import CatalogoVersion, Documento, Evaluacion, Organizacion, Software, Usuario

URL = reverse('presentation:decisor-carga-documental')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CargaPaginacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        org = Organizacion.objects.create(nombre='Org pag')
        cls.actor = Usuario.objects.create_user('pag@test.local', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cat = CatalogoVersion.objects.create(version='pag', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor, catalogo=cat,
                                           software=Software.objects.create(nombre='Pag SW'))
        for i in range(7):
            Documento.objects.create(evaluacion=cls.ev, usuario=cls.actor, nombre=f'doc{i}.pdf', tipo='PDF',
                                     ubicacion=f'd{i}.pdf', version='v9' if i == 0 else None)

    def setUp(self):
        self.client.force_login(self.actor)

    def get(self, **extra):
        return self.client.get(URL, {'evaluacion_id': self.ev.pk, **extra})

    def test_la_tabla_muestra_5_por_pagina(self):
        r = self.get()
        self.assertEqual(len(r.context['docs_pagina']), 5)
        self.assertContains(r, 'Página 1 de 2 · 7 documentos')
        self.assertEqual(len(self.get(pag=2).context['docs_pagina']), 2)

    def test_hasta_5_documentos_no_hay_paginacion(self):
        Documento.objects.filter(evaluacion=self.ev).exclude(nombre__in=['doc0.pdf', 'doc1.pdf']).delete()
        self.assertNotContains(self.get(), 'cd-pag"')

    def test_la_version_se_elige_entre_etiquetas(self):
        r = self.get()
        for etiqueta in ('Sin versión', 'v1.0', 'v2.0', 'v3.0', 'v9', '+ Nueva'):
            self.assertContains(r, f'<span>{etiqueta}</span>')