"""Resumen de cobertura, selector agrupado y «Sugerir evidencia» de la Carga documental."""
from datetime import date
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

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

    def test_resumen_muestra_cobertura_y_avisa_de_subfactores_sin_evidencia(self):
        Evidencia.objects.create(valoracion=self.v1, fragmento=self.f1)
        r = self.get()
        self.assertContains(r, 'id="cd-resumen"')
        self.assertContains(r, 'data-confirmar="cd-resumen"')
        self.assertContains(r, '1 subfactor sin evidencia')
        self.assertContains(r, 'Costo de soporte')
        self.assertEqual(r.context['cobertura']['con_evidencia'], 1)

    def test_selector_agrupa_por_factor_y_cuenta_evidencias(self):
        Evidencia.objects.create(valoracion=self.v1, fragmento=self.f1)
        r = self.get(doc_id=self.doc.pk, panel=1)
        self.assertContains(r, '<optgroup label="Costos">')
        self.assertContains(r, '✓ 1 · Costo de licencia')
        self.assertContains(r, '○ Costo de soporte')
        items = r.context['opciones'][0]['items']
        self.assertEqual(items[0]['subfactor_id'], self.sf2.pk)  # sin evidencia primero

    def test_boton_sugerir_lleva_a_la_pantalla_de_respaldo(self):
        r = self.get()
        self.assertContains(r, 'revisar=1')
        self.assertNotContains(r, 'id="cd-sugerencias"')

    def test_pantalla_respaldo_no_crea_nada_y_clasifica_relevancia(self):
        def buscar(**k):
            if k['subfactor_id'] == self.sf1.pk:
                return [self.item(self.f1, 0.8)]
            return [self.item(self.f2, 0.2), self.item(self.f1, 0.07)]
        with mock.patch(BUSCAR, side_effect=buscar):
            r = self.get(revisar=1)
        self.assertTemplateUsed(r, 'presentation/decisor/respaldo_subfactores.html')
        self.assertContains(r, 'Respaldo de los subfactores')
        self.assertEqual(Evidencia.objects.count(), 0)
        datos = {d['id']: d for d in r.context['datos']}
        self.assertEqual(datos[self.v1.pk]['candidatos'][0]['nivel'], 'alta')
        self.assertEqual([c['nivel'] for c in datos[self.v2.pk]['candidatos']], ['media', 'baja'])
        self.assertEqual(r.context['n_altas'], 1)

    def test_pantalla_respaldo_no_sugiere_donde_ya_hay_evidencia(self):
        Evidencia.objects.create(valoracion=self.v1, fragmento=self.f1)
        with mock.patch(BUSCAR, return_value=[self.item(self.f2, 0.5)]) as m:
            r = self.get(revisar=1)
        datos = {d['id']: d for d in r.context['datos']}
        self.assertEqual(datos[self.v1.pk]['candidatos'], [])
        self.assertEqual(len(datos[self.v1.pk]['guardados']), 1)
        self.assertEqual(m.call_count, 1)  # solo el subfactor pendiente

    def test_pantalla_respaldo_sin_embeddings_no_busca(self):
        FragmentoDocumento.objects.filter(documento=self.doc).update(embedding=None)
        with mock.patch(BUSCAR) as m:
            r = self.get(revisar=1)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(m.call_count, 0)

    def test_vincular_sugeridas_crea_solo_lo_confirmado_y_no_duplica(self):
        datos = {'evaluacion_id': self.ev.pk, 'accion': 'vincular_sugeridas',
                 'sel': [f'{self.v1.pk}:{self.f1.pk}:0.81', f'{self.v2.pk}:{self.f2.pk}:0.40']}
        self.client.post(URL, datos)
        self.assertEqual(Evidencia.objects.count(), 2)
        e = Evidencia.objects.get(valoracion=self.v1)
        self.assertEqual(e.fragmento_id, self.f1.pk)
        self.assertTrue(e.referencia)
        self.client.post(URL, datos)
        self.assertEqual(Evidencia.objects.count(), 2)

    def test_vincular_sugeridas_ignora_valores_ajenos_o_mal_formados(self):
        otra = Evaluacion.objects.create(organizacion=self.ev.organizacion, usuario=self.actor, catalogo=self.ev.catalogo,
                                         software=Software.objects.create(nombre='Otra'))
        doc2 = Documento.objects.create(evaluacion=otra, usuario=self.actor, nombre='x.pdf', tipo='PDF', ubicacion='x')
        ajeno = FragmentoDocumento.objects.create(documento=doc2, pagina=1, contenido='ajeno')
        self.client.post(URL, {'evaluacion_id': self.ev.pk, 'accion': 'vincular_sugeridas',
                               'sel': [f'{self.v1.pk}:{ajeno.pk}:0.5', 'basura', '99999:1:0.5', f'{self.v1.pk}:{self.f1.pk}:abc']})
        self.assertEqual(Evidencia.objects.count(), 1)
        self.assertIsNone(Evidencia.objects.get().relevancia)

    def test_sin_seleccion_no_vincula(self):
        self.client.post(URL, {'evaluacion_id': self.ev.pk, 'accion': 'vincular_sugeridas'})
        self.assertEqual(Evidencia.objects.count(), 0)