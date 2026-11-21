"""Pruebas de las pantallas de Resultados e Informe (HU14)."""

from django.test import TestCase
from django.urls import reverse

from apps.application.tests.utilidades_informe import crear_decisor, crear_evaluacion
from apps.data.models import Usuario


class ResultadosInformeVistaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.decisor = crear_decisor()
        cls.evaluacion = crear_evaluacion(cls.decisor)
        cls.otro = crear_decisor('otro@guios.test', 'Otra Persona')
        cls.admin = Usuario.objects.create_user(
            correo='admin@guios.test', password='Clave-Segura-123',
            nombre='Ana Admin', rol=Usuario.ADMINISTRADOR)
        cls.url_resultados = reverse('presentation:decisor-resultados')
        cls.url_informe = reverse('presentation:decisor-informe')

    # --- Resultados --------------------------------------------------------
    def test_resultados_muestra_recomendacion_y_factores(self):
        self.client.force_login(self.decisor)
        respuesta = self.client.get(self.url_resultados)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, 'presentation/decisor/resultados.html')
        self.assertContains(respuesta, 'Recomendación B')
        self.assertContains(respuesta, 'Compatibilidad')
        self.assertContains(respuesta, '3,50')
        self.assertContains(respuesta, 'Oportunidad')
        self.assertNotContains(respuesta, 'Módulo no disponible')

    def test_resultados_no_lista_factores_no_relevantes(self):
        self.client.force_login(self.decisor)
        self.assertNotContains(self.client.get(self.url_resultados), 'Soporte')

    def test_resultados_sin_evaluaciones_muestra_estado_vacio(self):
        self.client.force_login(self.otro)
        respuesta = self.client.get(self.url_resultados)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Aún no hay resultados')

    def test_un_decisor_no_ve_la_evaluacion_de_otro(self):
        self.client.force_login(self.otro)
        respuesta = self.client.get(f'{self.url_resultados}?evaluacion={self.evaluacion.evaluacion_id}')
        self.assertEqual(respuesta.status_code, 404)

    def test_evaluacion_con_valor_no_numerico_da_404(self):
        self.client.force_login(self.decisor)
        self.assertEqual(self.client.get(f'{self.url_resultados}?evaluacion=abc').status_code, 404)

    # --- Informe -----------------------------------------------------------
    def test_informe_muestra_evidencias_fuentes_y_trazabilidad(self):
        self.client.force_login(self.decisor)
        respuesta = self.client.get(self.url_informe)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, 'presentation/decisor/informe.html')
        self.assertContains(respuesta, 'Descargar informe PDF')
        self.assertContains(respuesta, 'Abre y guarda formatos de Office')
        self.assertContains(respuesta, 'guia.pdf')
        self.assertContains(respuesta, 'versión 1.0')

    def test_el_boton_de_descarga_apunta_a_la_evaluacion(self):
        self.client.force_login(self.decisor)
        esperado = f'?evaluacion={self.evaluacion.evaluacion_id}&amp;formato=pdf'
        self.assertContains(self.client.get(self.url_informe), esperado)

    def test_descarga_el_pdf(self):
        self.client.force_login(self.decisor)
        respuesta = self.client.get(f'{self.url_informe}?evaluacion={self.evaluacion.evaluacion_id}&formato=pdf')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename="informe-guios-libreoffice-', respuesta['Content-Disposition'])
        self.assertTrue(respuesta.content.startswith(b'%PDF'))

    def test_otro_decisor_no_puede_descargar_el_pdf(self):
        self.client.force_login(self.otro)
        respuesta = self.client.get(f'{self.url_informe}?evaluacion={self.evaluacion.evaluacion_id}&formato=pdf')
        self.assertEqual(respuesta.status_code, 404)

    def test_pdf_sin_evaluaciones_muestra_la_pantalla_vacia(self):
        self.client.force_login(self.otro)
        respuesta = self.client.get(f'{self.url_informe}?formato=pdf')
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Aún no hay un informe')

    # --- Acceso ------------------------------------------------------------
    def test_el_administrador_no_entra(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url_resultados).status_code, 403)
        self.assertEqual(self.client.get(self.url_informe).status_code, 403)

    def test_sin_sesion_pide_login(self):
        self.assertEqual(self.client.get(self.url_resultados).status_code, 302)
        self.assertEqual(self.client.get(self.url_informe).status_code, 302)
