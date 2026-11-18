"""
Pruebas de permisos por rol sobre las pantallas reales (HU01).

Cubren GET y POST: sin sesión se pide login, con el rol equivocado se da 403,
con el rol correcto se abre.
"""

from django.test import TestCase
from django.urls import reverse

from apps.business_rules import menu
from apps.data.models import Usuario
from apps.presentation import urls_admin, urls_decisor

RUTAS_ADMIN = [m.ruta for m in menu.CATALOGO if menu.ADMINISTRADOR in m.roles]
RUTAS_DECISOR = [m.ruta for m in menu.CATALOGO if menu.DECISOR in m.roles]


def url(ruta):
    return reverse('presentation:' + ruta)


class PermisosBase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(
            correo='admin@guios.test', password='Clave-Segura-123',
            nombre='Ana Admin', rol=Usuario.ADMINISTRADOR)
        cls.decisor = Usuario.objects.create_user(
            correo='decisor@guios.test', password='Clave-Segura-123',
            nombre='Dario Decisor', rol=Usuario.DECISOR)


class SinSesionTests(PermisosBase):

    def test_toda_ruta_protegida_manda_al_login_con_next(self):
        login = url('home')
        for ruta in RUTAS_ADMIN + RUTAS_DECISOR:
            with self.subTest(ruta=ruta):
                destino = url(ruta)
                esperado = '%s?next=%s' % (login, destino)
                self.assertRedirects(self.client.get(destino), esperado,
                                     fetch_redirect_response=False)

    def test_un_post_sin_sesion_tambien_manda_al_login(self):
        for ruta in RUTAS_ADMIN + RUTAS_DECISOR:
            with self.subTest(ruta=ruta):
                respuesta = self.client.post(url(ruta), {})
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn(url('home'), respuesta['Location'])

    def test_el_login_es_publico(self):
        self.assertEqual(self.client.get(url('home')).status_code, 200)

    def test_cerrar_sesion_sin_sesion_no_falla(self):
        self.assertRedirects(self.client.post(url('logout')), url('home'))


class RolCorrectoTests(PermisosBase):

    def test_el_administrador_abre_todas_sus_pantallas(self):
        self.client.force_login(self.admin)
        for ruta in RUTAS_ADMIN:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(url(ruta)).status_code, 200)

    def test_el_decisor_abre_todas_sus_pantallas(self):
        self.client.force_login(self.decisor)
        for ruta in RUTAS_DECISOR:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(url(ruta)).status_code, 200)


class RolEquivocadoTests(PermisosBase):

    def test_el_decisor_no_abre_pantallas_de_administracion(self):
        self.client.force_login(self.decisor)
        for ruta in RUTAS_ADMIN:
            with self.subTest(ruta=ruta, metodo='GET'):
                self.assertEqual(self.client.get(url(ruta)).status_code, 403)
            with self.subTest(ruta=ruta, metodo='POST'):
                self.assertEqual(self.client.post(url(ruta), {}).status_code, 403)

    def test_el_administrador_no_abre_pantallas_del_decisor(self):
        self.client.force_login(self.admin)
        for ruta in RUTAS_DECISOR:
            with self.subTest(ruta=ruta, metodo='GET'):
                self.assertEqual(self.client.get(url(ruta)).status_code, 403)
            with self.subTest(ruta=ruta, metodo='POST'):
                self.assertEqual(self.client.post(url(ruta), {}).status_code, 403)

    def test_la_pagina_403_explica_y_lleva_al_inicio_del_rol(self):
        self.client.force_login(self.decisor)
        r = self.client.get(url('admin-usuarios-roles'))
        self.assertContains(r, 'No tiene permiso para ver esta página', status_code=403)
        self.assertContains(r, 'href="%s"' % url('decisor-inicio'), status_code=403)

    def test_un_403_no_cierra_la_sesion(self):
        self.client.force_login(self.decisor)
        self.client.get(url('admin-inicio'))
        self.assertEqual(self.client.get(url('decisor-inicio')).status_code, 200)


class DestinoTrasLoginTests(PermisosBase):

    def entrar(self, siguiente):
        return self.client.post(url('home'), {
            'username': 'decisor@guios.test', 'password': 'Clave-Segura-123', 'next': siguiente})

    def test_next_permitido_se_respeta(self):
        destino = url('decisor-importancia-factores')
        self.assertRedirects(self.entrar(destino), destino)

    def test_next_de_otro_rol_se_ignora_y_va_al_inicio(self):
        r = self.entrar(url('admin-usuarios-roles'))
        self.assertRedirects(r, url('decisor-inicio'))

    def test_next_externo_se_ignora(self):
        r = self.entrar('https://sitio-malicioso.example/')
        self.assertRedirects(r, url('decisor-inicio'))

    def test_next_inexistente_se_ignora(self):
        r = self.entrar('/ruta/que/no/existe/')
        self.assertRedirects(r, url('decisor-inicio'))


class GuardianDeRutasTests(TestCase):
    """Obliga a declarar en el catálogo toda ruta nueva (negar por defecto)."""

    def test_las_rutas_de_las_areas_coinciden_con_el_catalogo(self):
        declaradas = {p.name for p in urls_admin.urlpatterns + urls_decisor.urlpatterns}
        catalogo = {m.ruta for m in menu.CATALOGO}
        self.assertEqual(
            declaradas, catalogo,
            'Toda ruta de urls_admin/urls_decisor debe estar en business_rules/menu.py (CATALOGO) '
            'con sus roles; si no, queda denegada para todos.')
