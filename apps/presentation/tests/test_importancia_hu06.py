"""HU06 - Pantalla de valoración de factores (paso 2 de la evaluación)."""

from django.test import TestCase
from django.urls import reverse

from apps.application.tests.test_importancia_hu06 import (
    crear_catalogo_con_factores, crear_decisor, registrar_evaluacion,
)
from apps.application.services.importancia import ImportanciaFactoresService
from apps.data.models import EvaluacionFactor, Usuario

URL = reverse('presentation:decisor-importancia-factores')


class ImportanciaFactoresVistaTests(TestCase):

    def setUp(self):
        crear_catalogo_con_factores({'Compatibilidad': 3, 'Documentación': 2})
        self.decisor = crear_decisor()
        self.evaluacion = registrar_evaluacion(self.decisor)
        self.filas = {f.nombre: f for f in ImportanciaFactoresService().filas(self.evaluacion)}

    def datos(self, **por_nombre):
        datos = {'evaluacion_id': self.evaluacion.pk}
        for nombre, fila in self.filas.items():
            datos[f'id_{fila.factor_id}'] = por_nombre.get(nombre, fila.is_)
        return datos

    def test_exige_iniciar_sesion(self):
        respuesta = self.client.get(URL)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/', respuesta['Location'])

    def test_un_administrador_no_entra(self):
        admin = Usuario.objects.create_user(
            correo='admin.hu06@guios.test', password='Clave-Segura-123',
            nombre='Admin', rol=Usuario.ADMINISTRADOR)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_sin_evaluacion_invita_a_registrar_la_ficha(self):
        otro = crear_decisor('sin.evaluacion@guios.test')
        self.client.force_login(otro)
        respuesta = self.client.get(URL)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'No hay una evaluación en curso')
        self.assertContains(respuesta, reverse('presentation:decisor-ficha-inicial'))
        self.assertNotContains(respuesta, 'id="importancia-form"')

    def test_no_abre_la_evaluacion_de_otro_decisor(self):
        otro = crear_decisor('otro.decisor@guios.test')
        self.client.force_login(otro)
        respuesta = self.client.get(URL, {'evaluacion_id': self.evaluacion.pk})
        self.assertContains(respuesta, 'No hay una evaluación en curso')
        self.assertNotContains(respuesta, 'Compatibilidad')

    def test_identificador_invalido_no_rompe_ni_adivina(self):
        self.client.force_login(self.decisor)
        for crudo in ('abc', '-1', '0', '99999999999999999999999'):
            respuesta = self.client.get(URL, {'evaluacion_id': crudo})
            self.assertEqual(respuesta.status_code, 200, crudo)
            self.assertContains(respuesta, 'No hay una evaluación en curso')

    def test_muestra_los_factores_con_su_importancia_sugerida(self):
        self.client.force_login(self.decisor)
        respuesta = self.client.get(URL, {'evaluacion_id': self.evaluacion.pk})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Valoración de factores')
        self.assertContains(respuesta, 'Compatibilidad')
        self.assertContains(respuesta, 'Documentación')
        self.assertContains(respuesta, 'Sugerida: 3')
        self.assertContains(respuesta, f'Evaluación #{self.evaluacion.pk}')

    def test_sin_parametro_usa_la_evaluacion_mas_reciente(self):
        self.client.force_login(self.decisor)
        reciente = registrar_evaluacion(self.decisor, 'Firefox')
        respuesta = self.client.get(URL)
        self.assertContains(respuesta, f'Evaluación #{reciente.pk}')
        self.assertContains(respuesta, 'Firefox')

    def test_guarda_y_continua_a_la_carga_documental(self):
        self.client.force_login(self.decisor)
        respuesta = self.client.post(URL, self.datos(Compatibilidad=4, Documentación=1))
        destino = reverse('presentation:decisor-carga-documental') + f'?evaluacion_id={self.evaluacion.pk}'
        self.assertRedirects(respuesta, destino, fetch_redirect_response=False)
        guardados = {ef.factor.nombre: ef for ef in EvaluacionFactor.objects.filter(evaluacion=self.evaluacion)}
        self.assertEqual(guardados['Compatibilidad'].importancia_relativa, 3)
        self.assertFalse(guardados['Documentación'].relevante)

    def test_valor_invalido_muestra_error_y_no_guarda(self):
        self.client.force_login(self.decisor)
        datos = self.datos()
        datos[f"id_{self.filas['Compatibilidad'].factor_id}"] = '9'
        respuesta = self.client.post(URL, datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Falta valorar el factor')
        self.assertFalse(EvaluacionFactor.objects.filter(evaluacion=self.evaluacion).exists())

    def test_el_error_conserva_lo_que_el_decisor_habia_elegido(self):
        # Un solo factor posible de excluir y el decisor lo excluye todo: debe volver con su elección.
        crear_catalogo_con_factores({'Único': 2})
        evaluacion = registrar_evaluacion(self.decisor, 'Otro')
        fila = ImportanciaFactoresService().filas(evaluacion)[0]
        self.client.force_login(self.decisor)
        respuesta = self.client.post(
            URL, {'evaluacion_id': evaluacion.pk, f'id_{fila.factor_id}': 1})
        self.assertContains(respuesta, 'Al menos un factor debe quedar relevante')
        self.assertContains(respuesta, 'Se excluye')

    def test_no_guarda_en_la_evaluacion_de_otro(self):
        otro = crear_decisor('otro.decisor@guios.test')
        self.client.force_login(otro)
        respuesta = self.client.post(URL, self.datos(Compatibilidad=4))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'No hay una evaluación en curso')
        self.assertFalse(EvaluacionFactor.objects.filter(evaluacion=self.evaluacion).exists())

    def test_la_ficha_inicial_lleva_a_esta_pantalla(self):
        self.client.force_login(self.decisor)
        respuesta = self.client.post(reverse('presentation:decisor-ficha-inicial'), {
            'nombre_organizacion': 'Instituto QA', 'nombre_software': 'GIMP'})
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta['Location'].startswith(URL))
        self.assertIn('evaluacion_id=', respuesta['Location'])

    def test_catalogo_sin_indicadores_avisa_y_no_ofrece_guardar(self):
        crear_catalogo_con_factores({})
        evaluacion = registrar_evaluacion(self.decisor, 'Vacío')
        self.client.force_login(self.decisor)
        respuesta = self.client.get(URL, {'evaluacion_id': evaluacion.pk})
        self.assertContains(respuesta, 'Sin factores para valorar')
        self.assertNotContains(respuesta, 'id="importancia-form"')
