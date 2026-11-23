"""Resumen antes de «Siguiente», asociación automática de evidencia y selector agrupado de la Carga documental."""
from datetime import date
from unittest import mock

from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.application.services.retrieval import RetrievalService
from apps.presentation.views import evidencia_carga
from apps.data.models import (CatalogoVersion, Dimension, Documento, Evaluacion, EvaluacionFactor, Evidencia, Factor,
    FragmentoDocumento, Organizacion, Software, Subfactor, Usuario, ValoracionSubfactor)

URL = reverse('presentation:decisor-carga-documental')
BUSCAR = 'apps.application.services.retrieval.RetrievalService.buscar_por_subfactor'


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class EvidenciaCargaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        org = Organizacion.objects.create(nombre='Org sug')
        cls.actor = Usuario.objects.create_user('sug@test.local', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cat = CatalogoVersion.objects.create(version='sug', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor, catalogo=cat,
                                           software=Software.objects.create(nombre='Sug SW'))
        dim = Dimension.objects.create(nombre='Tecnológica')
        f = Factor.objects.create(dimension=dim, nombre='Costos', alcance=Factor.EXTERNO)
        ef = EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=f, importancia_relativa=3)
        cls.sf1 = Subfactor.objects.create(factor=f, descripcion='Costo de licencia')
        cls.sf2 = Subfactor.objects.create(factor=f, descripcion='Costo de soporte')
        cls.v1 = ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=cls.sf1)
        cls.v2 = ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=cls.sf2)
        cls.doc = Documento.objects.create(evaluacion=cls.ev, usuario=cls.actor, nombre='Guía.pdf', tipo='PDF', ubicacion='g.pdf')
        cls.f1 = FragmentoDocumento.objects.create(documento=cls.doc, pagina=1, contenido='La licencia cuesta 100 dólares.',
                                                   embedding=[0.1] * 1536)
        cls.f2 = FragmentoDocumento.objects.create(documento=cls.doc, pagina=2, contenido='Soporte incluido.',
                                                   embedding=[0.2] * 1536)

    def setUp(self):
        self.client.force_login(self.actor)

    def get(self, **extra):
        return self.client.get(URL, {'evaluacion_id': self.ev.pk, **extra})

    def item(self, frag, sim):
        return {'fragmento_id': frag.pk, 'documento_id': frag.documento_id, 'documento_nombre': 'Guía.pdf', 'ubicacion_referencia': f'Página {frag.pagina}',
                'contenido': frag.contenido, 'similitud': sim}

    def test_resumen_antes_de_siguiente_prepara_la_evidencia(self):
        Evidencia.objects.create(valoracion=self.v1, fragmento=self.f1)
        r = self.get()
        self.assertContains(r, 'id="cd-resumen"')
        self.assertContains(r, 'data-confirmar="cd-resumen"')
        self.assertContains(r, 'value="preparar_evidencia"')
        self.assertContains(r, 'subfactores por respaldar')
        self.assertEqual(r.context['cobertura']['con_evidencia'], 1)

    def test_el_paso_3_no_pide_vincular_ni_sugerir_nada(self):
        r = self.get(doc_id=self.doc.pk, panel=1)
        for texto in ('Sugerir evidencia', 'revisar=1', 'Vincular a subfactor', 'vincular_evidencia', 'Ninguna sirve'):
            self.assertNotContains(r, texto)

    def test_selector_agrupa_por_factor_y_cuenta_evidencias(self):
        Evidencia.objects.create(valoracion=self.v1, fragmento=self.f1)
        r = self.get(doc_id=self.doc.pk, panel=1)
        self.assertContains(r, '<optgroup label="Costos">')
        self.assertContains(r, '✓ 1 · Costo de licencia')
        self.assertContains(r, '○ Costo de soporte')
        items = r.context['opciones'][0]['items']
        self.assertEqual(items[0]['subfactor_id'], self.sf2.pk)  # sin evidencia primero

    def preparar(self):
        return self.client.post(URL, {'evaluacion_id': self.ev.pk, 'accion': 'preparar_evidencia'})

    def test_preparar_asocia_los_mejores_pasajes_y_avanza_al_paso_4(self):
        def buscar(**k):
            if k['subfactor_id'] == self.sf1.pk:
                return [self.item(self.f1, 0.8), self.item(self.f2, 0.5), self.item(self.f1, 0.2)]
            return []
        with mock.patch(BUSCAR, side_effect=buscar) as m:
            r = self.preparar()
        self.assertEqual(m.call_args.kwargs['umbral_similitud'], 0.15)
        self.assertEqual(Evidencia.objects.filter(valoracion=self.v1).count(), 2)   # máximo 2 por subfactor
        self.assertEqual(Evidencia.objects.filter(valoracion=self.v2).count(), 0)
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('presentation:decisor-revision-valoraciones'), r['Location'])
        self.assertTrue(any('Se asociaron 2 pasajes de sus documentos a 1 subfactor' in str(x) for x in get_messages(r.wsgi_request)))
        with mock.patch(BUSCAR, side_effect=buscar):
            self.preparar()
        self.assertEqual(Evidencia.objects.count(), 2)                               # no duplica

    def test_preparar_no_toca_subfactores_que_ya_tienen_evidencia(self):
        Evidencia.objects.create(valoracion=self.v1, fragmento=self.f1)
        with mock.patch(BUSCAR, return_value=[self.item(self.f2, 0.9)]) as m:
            self.preparar()
        self.assertEqual(m.call_count, 1)
        self.assertEqual(Evidencia.objects.filter(valoracion=self.v1).count(), 1)

    def test_preparar_sin_documentos_solo_avanza(self):
        self.doc.delete()
        with mock.patch(BUSCAR) as m:
            r = self.preparar()
        self.assertEqual(m.call_count, 0)
        self.assertIn(reverse('presentation:decisor-revision-valoraciones'), r['Location'])

    def test_vincular_en_lote_ignora_valores_ajenos_o_mal_formados(self):
        otra = Evaluacion.objects.create(organizacion=self.ev.organizacion, usuario=self.actor, catalogo=self.ev.catalogo,
                                         software=Software.objects.create(nombre='Otra'))
        doc2 = Documento.objects.create(evaluacion=otra, usuario=self.actor, nombre='x.pdf', tipo='PDF', ubicacion='x')
        ajeno = FragmentoDocumento.objects.create(documento=doc2, pagina=1, contenido='ajeno')
        creadas, _ = evidencia_carga.vincular_en_lote(
            RetrievalService(), self.ev, [self.v1, self.v2],
            [f'{self.v1.pk}:{ajeno.pk}:0.5', 'basura', '99999:1:0.5', f'{self.v1.pk}:{self.f1.pk}:abc'])
        self.assertEqual(creadas, 1)
        self.assertIsNone(Evidencia.objects.get().relevancia)