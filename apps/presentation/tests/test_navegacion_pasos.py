"""Los pasos de la evaluación tienen Anterior / Siguiente y conservan la evaluación activa."""
from datetime import date

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.data.models import CatalogoVersion, Evaluacion, Organizacion, Software, Usuario


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class NavegacionPasosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        org = Organizacion.objects.create(nombre='Universidad Demo')
        cls.actor = Usuario.objects.create_user('nav@test.local', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cat = CatalogoVersion.objects.create(version='nav', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor, catalogo=cat,
                                           software=Software.objects.create(nombre='LibreGestión', version='3.2'))

    def cliente(self):
        c = Client()
        c.force_login(self.actor)
        return c

    def test_ficha_tiene_anterior_y_siguiente_que_envia_el_formulario(self):
        r = self.cliente().get(reverse('presentation:decisor-ficha-inicial'))
        self.assertContains(r, 'paso-nav')
        self.assertContains(r, 'form="form-ficha"')
        self.assertContains(r, 'de 50 a 199 personas')

    def test_revision_de_evidencia_ahora_tiene_pasos_y_navegacion(self):
        url = reverse('presentation:decisor-revision-valoraciones')
        r = self.cliente().get(url, {'evaluacion': self.ev.pk})
        self.assertContains(r, 'evaluation-stepper-container')
        self.assertContains(r, f"{reverse('presentation:decisor-carga-documental')}?evaluacion_id={self.ev.pk}")
        self.assertContains(r, f"{reverse('presentation:decisor-resultados')}?evaluacion={self.ev.pk}")

    def test_validacion_humana_tambien_tiene_navegacion(self):
        url = reverse('presentation:decisor-revision-valoraciones')
        r = self.cliente().get(url, {'etapa': 'validacion', 'evaluacion': self.ev.pk})
        self.assertContains(r, 'paso-nav')
        self.assertContains(r, 'Siguiente')
    def test_carga_documental_tiene_pasos_con_la_evaluacion_y_navegacion(self):
        r = self.cliente().get(reverse('presentation:decisor-carga-documental'), {'evaluacion_id': self.ev.pk})
        self.assertContains(r, 'paso-nav')
        self.assertContains(r, f"{reverse('presentation:decisor-importancia-factores')}?evaluacion_id={self.ev.pk}")
        self.assertContains(r, f"{reverse('presentation:decisor-revision-valoraciones')}?evaluacion={self.ev.pk}")
        self.assertContains(r, 'Documentos de la evaluación')
        self.assertContains(r, 'Sin documentos')