from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.data.models import Usuario


class IndicadoresLiteraturaVistaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(
            correo='admin@guios.test', password='Clave-Segura-123',
            nombre='Ana Admin', rol=Usuario.ADMINISTRADOR)
        cls.decisor = Usuario.objects.create_user(
            correo='decisor@guios.test', password='Clave-Segura-123',
            nombre='Dario Decisor', rol=Usuario.DECISOR)
        cls.url = reverse('presentation:admin-indicadores-literatura')

    def test_el_administrador_ve_los_indicadores_de_la_version_activa(self):
        call_command('cargar_catalogo_guios', verbosity=0)
        self.client.force_login(self.admin)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, 'presentation/administracion/indicadores_literatura.html')
        self.assertTemplateUsed(respuesta, 'presentation/includes/indicadores_bibliograficos.html')
        self.assertTemplateNotUsed(respuesta, 'presentation/includes/aviso_datos_simulados.html')
        self.assertEqual(respuesta.context['indicadores'].version, 'v1-2021')
        self.assertContains(respuesta, 'Catálogo v1-2021')

    def test_sin_catalogo_avisa_como_cargarlo(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNone(respuesta.context['indicadores'])
        self.assertContains(respuesta, 'cargar_catalogo_guios')

    def test_el_decisor_no_puede_verlos(self):
        self.client.force_login(self.decisor)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_sin_sesion_pide_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
