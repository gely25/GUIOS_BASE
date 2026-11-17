"""
Pruebas de las vistas de la capa de presentación.
"""

from django.test import SimpleTestCase
from django.urls import reverse


class PantallaAccesoTests(SimpleTestCase):

    def setUp(self):
        self.respuesta = self.client.get(reverse('presentation:home'))

    def test_responde_200(self):
        self.assertEqual(self.respuesta.status_code, 200)

    def test_usa_la_plantilla_de_acceso_y_el_layout_base(self):
        self.assertTemplateUsed(self.respuesta, 'presentation/acceso/home.html')
        self.assertTemplateUsed(self.respuesta, 'presentation/layouts/base.html')

    def test_muestra_el_titulo(self):
        self.assertContains(self.respuesta, 'GUIOS PRO')
