"""Pruebas de las pantallas de actualización bibliográfica (HU02)."""

from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.data.models import BusquedaBibliografica, CatalogoVersion, Factor, PublicacionFactor, Usuario
from apps.external_services.bibliografia import ResultadoPublicacion

RUTAS = ['admin-actualizacion-bibliografica', 'admin-bibliografia-busquedas',
         'admin-bibliografia-estado', 'admin-bibliografia-version']


class FuenteFalsa:
    nombre = 'Fuente falsa'

    def buscar(self, consulta, anio_inicio, anio_fin, maximo):
        return [ResultadoPublicacion('Vendor lock-in and open source adoption', 2023, '10.1/x', None, None)]


def url(nombre):
    return reverse('presentation:' + nombre)


class VistasBibliografiaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        call_command('cargar_catalogo_guios', verbosity=0)
        cls.admin = Usuario.objects.create_user(
            correo='admin@guios.test', password='Clave-Segura-123', nombre='Ana Admin', rol=Usuario.ADMINISTRADOR)
        cls.decisor = Usuario.objects.create_user(
            correo='decisor@guios.test', password='Clave-Segura-123', nombre='Dario Decisor', rol=Usuario.DECISOR)

    def test_el_decisor_no_entra_a_ninguna(self):
        self.client.force_login(self.decisor)
        for ruta in RUTAS:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(url(ruta)).status_code, 403)
                self.assertEqual(self.client.post(url(ruta), {'accion': 'lanzar'}).status_code, 403)
        self.assertFalse(BusquedaBibliografica.objects.exists())

    def test_el_panel_ya_no_es_un_modulo_pendiente(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(url('admin-actualizacion-bibliografica'))
        self.assertNotContains(respuesta, 'Módulo no disponible')
        self.assertContains(respuesta, 'v1-2021')

    def test_lanzar_procesar_revisar_y_publicar(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(url('admin-actualizacion-bibliografica'), {'accion': 'lanzar'})
        self.assertRedirects(respuesta, url('admin-actualizacion-bibliografica'))
        self.assertEqual(BusquedaBibliografica.objects.count(), 18)

        datos = self.client.get(url('admin-bibliografia-estado')).json()
        self.assertEqual((datos['total'], datos['terminado']), (18, False))

        with mock.patch('apps.application.services.actualizacion_bibliografica.busquedas.fuente_configurada',
                        return_value=FuenteFalsa()):
            call_command('procesar_busquedas', '--una-vez', verbosity=0, stdout=mock.MagicMock())
        self.assertTrue(self.client.get(url('admin-bibliografia-estado')).json()['terminado'])

        bloqueo = Factor.objects.get(nombre='Bloqueo de proveedores')
        busqueda = BusquedaBibliografica.objects.get(factor=bloqueo)
        detalle = url('admin-bibliografia-busquedas') + f'?id={busqueda.pk}'
        self.assertContains(self.client.get(detalle), 'Vendor lock-in and open source adoption')

        vinculo = PublicacionFactor.objects.get(factor=bloqueo)
        self.client.post(detalle, {'accion': 'revisar', 'vinculo': vinculo.pk, 'decision': 'aprobar'})
        vinculo.refresh_from_db()
        self.assertEqual(vinculo.estado, PublicacionFactor.APROBADA)

        self.client.post(url('admin-bibliografia-version'), {'accion': 'recalcular'})
        respuesta = self.client.get(url('admin-bibliografia-version'))
        self.assertContains(respuesta, 'Publicar')
        self.client.post(url('admin-bibliografia-version'), {'accion': 'publicar'})
        activa = CatalogoVersion.objects.get(estado=CatalogoVersion.ACTIVO)
        self.assertNotEqual(activa.version, 'v1-2021')
        self.assertEqual(activa.indicadores.get(factor=bloqueo).total_citas, 4)

    def test_historial_y_errores_de_entrada(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(url('admin-bibliografia-busquedas')), 'Historial de búsquedas')
        self.assertEqual(self.client.get(url('admin-bibliografia-busquedas') + '?id=abc').status_code, 404)
        self.assertEqual(self.client.get(url('admin-bibliografia-busquedas') + '?id=999').status_code, 404)
        self.assertEqual(self.client.post(url('admin-bibliografia-version'), {'accion': 'x'}).status_code, 400)
        self.assertEqual(self.client.post(url('admin-actualizacion-bibliografica'), {}).status_code, 400)

    def test_publicar_sin_borrador_muestra_el_error(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(url('admin-bibliografia-version'), {'accion': 'publicar'}, follow=True)
        self.assertContains(respuesta, 'No hay un borrador para publicar')
