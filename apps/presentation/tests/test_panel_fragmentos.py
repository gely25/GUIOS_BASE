"""Panel lateral de fragmentos de la Carga documental: solo cambia cómo se muestran y se filtran."""
from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.data.models import (CatalogoVersion, Dimension, Documento, Evaluacion, EvaluacionFactor, Evidencia, Factor,
    FragmentoDocumento, Organizacion, Software, Subfactor, Usuario, ValoracionSubfactor)

URL = reverse('presentation:decisor-carga-documental')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PanelFragmentosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        org = Organizacion.objects.create(nombre='Org panel')
        cls.actor = Usuario.objects.create_user('panel@test.local', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cat = CatalogoVersion.objects.create(version='panel', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor, catalogo=cat,
                                           software=Software.objects.create(nombre='Panel SW'))
        dim = Dimension.objects.create(nombre='Tecnológica')
        f = Factor.objects.create(dimension=dim, nombre='Costos', alcance=Factor.EXTERNO)
        ef = EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=f, importancia_relativa=3)
        sf = Subfactor.objects.create(factor=f, descripcion='Costo de licencia')
        cls.val = ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=sf)
        cls.doc = Documento.objects.create(evaluacion=cls.ev, usuario=cls.actor, nombre='Guía larga.pdf', tipo='PDF', ubicacion='g.pdf')
        cls.frags = [FragmentoDocumento.objects.create(documento=cls.doc, pagina=n, contenido=f'Texto de la página {n}.')
                     for n in range(1, 26)]
        Evidencia.objects.create(valoracion=cls.val, fragmento=cls.frags[2])

    def setUp(self):
        self.client.force_login(self.actor)

    def abrir(self, **extra):
        return self.client.get(URL, {'evaluacion_id': self.ev.pk, 'doc_id': self.doc.pk, 'panel': 1, **extra})

    def test_el_panel_no_se_abre_solo(self):
        r = self.client.get(URL, {'evaluacion_id': self.ev.pk, 'doc_id': self.doc.pk})
        self.assertNotContains(r, 'id="panel-fragmentos"')
        self.assertContains(r, 'panel=1')

    def test_pagina_los_fragmentos_de_diez_en_diez(self):
        r = self.abrir()
        self.assertContains(r, 'id="panel-fragmentos"')
        self.assertContains(r, 'Texto de la página 10.')
        self.assertNotContains(r, 'Texto de la página 11.')
        self.assertContains(r, '1 de 3')
        r2 = self.abrir(pagina=3)
        self.assertContains(r2, 'Texto de la página 25.')
        self.assertNotContains(r2, 'Texto de la página 10.')

    def test_chips_de_paginas_filtran_por_ubicacion(self):
        r = self.abrir(ubic='p:11-20')
        self.assertContains(r, 'Texto de la página 11.')
        self.assertNotContains(r, 'Texto de la página 21.')
        self.assertNotContains(r, 'Texto de la página 3.')

    def test_estado_de_vinculo_y_etiqueta_en_el_fragmento_vinculado(self):
        todos = self.abrir()
        self.assertContains(todos, 'Costo de licencia')
        vinc = self.abrir(estado='vinculados')
        self.assertContains(vinc, 'Texto de la página 3.')
        self.assertNotContains(vinc, 'Texto de la página 4.')
        sin = self.abrir(estado='sin')
        self.assertNotContains(sin, 'Texto de la página 3.')
        self.assertContains(sin, 'Texto de la página 4.')

    def test_abrir_ubicacion_lleva_a_la_pagina_del_fragmento_destacado(self):
        r = self.client.get(URL, {'evaluacion_id': self.ev.pk, 'doc_id': self.doc.pk, 'fragmento_id': self.frags[14].pk})
        self.assertContains(r, 'Texto de la página 15.')
        self.assertContains(r, 'destacado')

    def test_no_muestra_documentos_de_otra_evaluacion(self):
        otro = Usuario.objects.create_user('otro@panel.test', 'Clave-test-123', nombre='Otro', organizacion=self.ev.organizacion)
        self.client.force_login(otro)
        r = self.client.get(URL, {'evaluacion_id': self.ev.pk, 'doc_id': self.doc.pk, 'panel': 1})
        self.assertNotContains(r, 'Guía larga.pdf')