from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class IndicadoresLiteraturaVistaTests(SimpleTestCase):

    def setUp(self):
        self.url = reverse('presentation:admin-indicadores-literatura')

    @override_settings(DEBUG=True)
    def test_en_desarrollo_muestra_la_vista_previa(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, 'presentation/administracion/indicadores_literatura_preview.html')
        self.assertTemplateUsed(respuesta, 'presentation/includes/indicadores_bibliograficos.html')
        self.assertTemplateUsed(respuesta, 'presentation/includes/aviso_datos_simulados.html')
        self.assertIn('indicadores', respuesta.context)

    @override_settings(DEBUG=False)
    def test_en_produccion_la_vista_previa_no_existe(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
