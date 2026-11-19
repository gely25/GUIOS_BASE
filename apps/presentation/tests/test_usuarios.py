"""Pruebas de integración del listado de usuarios (HU01)."""

from django.test import TestCase
from django.urls import reverse

from apps.data.models import Usuario


class ListadoUsuariosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(
            correo='admin@guios.test', nombre='Ana Admin', rol=Usuario.ADMINISTRADOR)
        cls.decisor = Usuario.objects.create_user(
            correo='decisor@guios.test', nombre='Carlos Decisor')
        cls.inactivo = Usuario.objects.create_user(
            correo='inactivo@guios.test', nombre='Lucia Decisor', activo=False)

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse('presentation:admin-usuarios-roles')

    def ids(self, respuesta):
        return {u.pk for u in respuesta.context['usuarios']}

    def test_listado_y_contadores_en_ambas_rutas(self):
        for ruta in ('admin-inicio', 'admin-usuarios-roles'):
            with self.subTest(ruta=ruta):
                r = self.client.get(reverse('presentation:' + ruta))
                self.assertContains(r, self.decisor.correo)
                self.assertContains(r, self.inactivo.correo)
                self.assertNotContains(r, 'Módulo no disponible')
                self.assertEqual(r.context['conteos'], {
                    'total': 3, 'decisores': 2, 'administradores': 1})

    def test_busqueda_por_nombre_o_correo_sin_distinguir_mayusculas(self):
        for termino in ('CARLOS', 'DECISOR@GUIOS.TEST'):
            with self.subTest(termino=termino):
                self.assertEqual(self.ids(self.client.get(self.url, {'buscar': termino})),
                                 {self.decisor.pk})

    def test_filtros_combinados(self):
        r = self.client.get(self.url, {'rol': Usuario.DECISOR, 'estado': 'inactivo'})
        self.assertEqual(self.ids(r), {self.inactivo.pk})
        self.assertEqual(r.context['conteos']['total'], 3)

    def test_filtro_activos(self):
        r = self.client.get(self.url, {'estado': 'activo'})
        self.assertEqual(self.ids(r), {self.admin.pk, self.decisor.pk})

    def test_sin_resultados(self):
        r = self.client.get(self.url, {'buscar': 'no existe'})
        self.assertContains(r, 'No se encontraron usuarios.')
        self.assertEqual(self.ids(r), set())

    def test_filtros_invalidos_se_ignoran(self):
        r = self.client.get(self.url, {'estado': 'otro', 'rol': 'otro'})
        self.assertEqual(len(self.ids(r)), 3)

    def test_el_decisor_no_puede_consultar_usuarios(self):
        self.client.force_login(self.decisor)
        self.assertEqual(self.client.get(self.url).status_code, 403)
