"""HU12: panel de PM y FODA dentro de la revisión de evidencia."""
from datetime import date

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.application.services.revision_humana import RevisionHumanaService
from apps.data.models import (CatalogoVersion, Dimension, Evaluacion, EvaluacionFactor, Factor,
                              Organizacion, Software, Subfactor, Usuario, ValoracionSubfactor)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PmFodaVistaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        org = Organizacion.objects.create(nombre='Org vista HU12')
        cls.actor = Usuario.objects.create_user('vista12@test.local', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cls.otro = Usuario.objects.create_user('otro-vista12@test.local', 'Clave-test-123', nombre='Otro', organizacion=org)
        cat = CatalogoVersion.objects.create(version='HU12 vista', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor,
                                           software=Software.objects.create(nombre='Soft vista'), catalogo=cat)
        dim = Dimension.objects.create(nombre='Organizacional')
        cls.soporte = Factor.objects.create(dimension=dim, nombre='Soporte', alcance=Factor.AMBOS)
        ef = EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=cls.soporte, importancia_relativa=3)
        sf = Subfactor.objects.create(factor=cls.soporte, descripcion='Soporte comunitario')
        v = ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=sf)
        version = RevisionHumanaService.obtener(cls.actor, cls.ev.pk, v.pk)['version']
        RevisionHumanaService.resolver(cls.actor, cls.ev.pk, v.pk, 'MANUAL', 4, 'Confirmada.', version)
        cls.ef = ef
        cls.url = reverse('presentation:decisor-revision-valoraciones')

    def cliente(self, usuario=None):
        c = Client()
        c.force_login(usuario or self.actor)
        return c

    def datos(self, **extra):
        base = {'etapa': 'validacion', 'evaluacion': self.ev.pk, 'accion': 'calcular_hu12'}
        base.update(extra)
        return base

    def test_el_panel_pide_elegir_el_alcance_de_soporte(self):
        r = self.cliente().get(self.url, {'etapa': 'validacion', 'evaluacion': self.ev.pk})
        self.assertContains(r, 'PM y clasificación FODA')
        self.assertContains(r, f'name="alcance_{self.soporte.pk}"')
        self.assertContains(r, 'Calcular y guardar PM y FODA')

    def test_post_guarda_pm_y_foda(self):
        r = self.cliente().post(self.url, self.datos(**{f'alcance_{self.soporte.pk}': 'externo'}))
        self.assertEqual(r.status_code, 302)
        self.ef.refresh_from_db()
        self.assertEqual((str(self.ef.ponderacion_media), self.ef.clasificacion_foda), ('4.00', 'Oportunidad'))

    def test_post_sin_elegir_alcance_no_guarda(self):
        r = self.cliente().post(self.url, self.datos(), follow=True)
        self.ef.refresh_from_db()
        self.assertIsNone(self.ef.ponderacion_media)
        self.assertContains(r, 'Elija interno o externo')

    def test_otro_decisor_no_puede_calcular(self):
        r = self.cliente(self.otro).post(self.url, self.datos(**{f'alcance_{self.soporte.pk}': 'interno'}))
        self.assertEqual(r.status_code, 403)
        self.ef.refresh_from_db()
        self.assertIsNone(self.ef.ponderacion_media)

    def test_exige_sesion(self):
        r = Client().post(self.url, self.datos(**{f'alcance_{self.soporte.pk}': 'interno'}))
        self.assertIn(r.status_code, (302, 403))
        self.ef.refresh_from_db()
        self.assertIsNone(self.ef.ponderacion_media)