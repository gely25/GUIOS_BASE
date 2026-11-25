"""Pruebas de las pantallas de actualización bibliográfica (HU02)."""

from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.data.models import BusquedaBibliografica, BusquedaPublicacion, CatalogoVersion, Factor, Publicacion, PublicacionFactor, Usuario
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

    def test_paginacion_publicaciones_revisar(self):
        self.client.force_login(self.admin)
        factor = Factor.objects.first()
        busqueda = BusquedaBibliografica.objects.create(
            factor=factor,
            fuente='Simulada',
            anio_inicio=2020,
            anio_fin=2025,
            consulta='test paginador',
            estado=BusquedaBibliografica.COMPLETADA
        )
        for i in range(15):
            pub = Publicacion.objects.create(
                titulo=f'Publicación de Prueba #{i+1}',
                anio=2022,
                doi=f'10.1000/test.{i+1}'
            )
            BusquedaPublicacion.objects.create(
                busqueda=busqueda,
                publicacion=pub,
                posicion=i + 1
            )

        # Página 1
        respuesta = self.client.get(url('admin-bibliografia-busquedas') + f'?id={busqueda.pk}')
        self.assertEqual(respuesta.status_code, 200)
        page_obj = respuesta.context['resultados']
        self.assertEqual(len(page_obj), 10)
        self.assertEqual(page_obj.paginator.count, 15)
        self.assertEqual(page_obj.paginator.num_pages, 2)
        self.assertContains(respuesta, 'Página 1 de 2')
        self.assertContains(respuesta, 'Publicación de Prueba #1')

        # Página 2
        respuesta_p2 = self.client.get(url('admin-bibliografia-busquedas') + f'?id={busqueda.pk}&page=2')
        self.assertEqual(respuesta_p2.status_code, 200)
        page_obj_p2 = respuesta_p2.context['resultados']
        self.assertEqual(len(page_obj_p2), 5)
        self.assertContains(respuesta_p2, 'Publicación de Prueba #15')

    def _crear_busquedas(self, total):
        factor = Factor.objects.first()
        for i in range(total):
            BusquedaBibliografica.objects.create(
                factor=factor,
                fuente=f'Fuente {i}',
                anio_inicio=2020,
                anio_fin=2025,
                consulta=f'Consulta {i}',
                estado=BusquedaBibliografica.COMPLETADA,
            )

    def test_paginacion_busquedas_recientes_en_el_panel(self):
        self.client.force_login(self.admin)
        self._crear_busquedas(25)

        respuesta = self.client.get(url('admin-actualizacion-bibliografica'))
        pagina = respuesta.context['busquedas']
        # El panel conserva solo las 20 búsquedas más recientes.
        self.assertEqual(pagina.paginator.count, 20)
        self.assertEqual(pagina.paginator.num_pages, 2)
        self.assertEqual(len(pagina), 10)
        self.assertContains(respuesta, 'Página 1 de 2')
        self.assertContains(respuesta, '?pag_busquedas=2')

        respuesta_p2 = self.client.get(url('admin-actualizacion-bibliografica') + '?pag_busquedas=2')
        self.assertEqual(len(respuesta_p2.context['busquedas']), 10)
        self.assertContains(respuesta_p2, 'Página 2 de 2')

    def test_paginacion_historial_busquedas(self):
        self.client.force_login(self.admin)
        self._crear_busquedas(25)

        # Una búsqueda con resultados y vínculos no debe duplicar filas al contar.
        busqueda = BusquedaBibliografica.objects.order_by('busqueda_id').first()
        publicacion = Publicacion.objects.create(
            titulo='Publicación con vínculo', anio=2022, doi='10.1000/vinculo')
        BusquedaPublicacion.objects.create(busqueda=busqueda, publicacion=publicacion, posicion=1)
        PublicacionFactor.objects.create(
            publicacion=publicacion, factor=Factor.objects.first(),
            estado=PublicacionFactor.SUGERIDA)

        respuesta = self.client.get(url('admin-bibliografia-busquedas'))
        pagina = respuesta.context['busquedas']
        self.assertEqual(pagina.paginator.count, 25)
        self.assertEqual(pagina.paginator.num_pages, 3)
        self.assertEqual(len(pagina), 10)
        self.assertContains(respuesta, 'Página 1 de 3')

        respuesta_p3 = self.client.get(url('admin-bibliografia-busquedas') + '?pag_busquedas=3')
        self.assertEqual(len(respuesta_p3.context['busquedas']), 5)
        self.assertContains(respuesta_p3, 'Página 3 de 3')
        self.assertContains(respuesta_p3, 'Mostrando 5 de 25 búsquedas')

    def test_pagina_invalida_o_fuera_de_rango(self):
        self.client.force_login(self.admin)
        self._crear_busquedas(25)

        respuesta = self.client.get(url('admin-bibliografia-busquedas') + '?pag_busquedas=abc')
        self.assertEqual(respuesta.context['busquedas'].number, 1)

        respuesta = self.client.get(url('admin-bibliografia-busquedas') + '?pag_busquedas=999')
        self.assertEqual(respuesta.context['busquedas'].number, 3)

    def test_la_vista_previa_muestra_la_busqueda_mas_reciente_al_paginar(self):
        self.client.force_login(self.admin)
        self._crear_busquedas(15)
        ultima = BusquedaBibliografica.objects.order_by('-busqueda_id').first()

        respuesta = self.client.get(url('admin-actualizacion-bibliografica') + '?pag_busquedas=2')
        self.assertEqual(respuesta.context['ultima_busqueda'].pk, ultima.pk)
        self.assertContains(respuesta, 'Fuente 14')
        self.assertContains(respuesta, 'Consulta 14')

    def test_sin_busquedas_no_hay_paginador(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(url('admin-actualizacion-bibliografica'))
        self.assertNotContains(respuesta, 'bib-paginador')
