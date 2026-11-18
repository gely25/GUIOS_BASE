"""
Pruebas del acceso (HU01): login por correo, redirección por rol y cierre de sesión.
"""

from django.test import TestCase
from django.urls import reverse

from apps.data.models import Usuario


class AccesoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(
            correo='admin@guios.test', password='Clave-Segura-123',
            nombre='Ana Admin', rol=Usuario.ADMINISTRADOR)
        cls.decisor = Usuario.objects.create_user(
            correo='decisor@guios.test', password='Clave-Segura-123',
            nombre='Dario Decisor', rol=Usuario.DECISOR)
        cls.inactivo = Usuario.objects.create_user(
            correo='baja@guios.test', password='Clave-Segura-123',
            nombre='Beto Baja', rol=Usuario.DECISOR, activo=False)
        cls.url = reverse('presentation:home')

    def entrar(self, correo, clave='Clave-Segura-123'):
        return self.client.post(self.url, {'username': correo, 'password': clave})

    def test_administrador_va_al_inicio_de_administracion(self):
        self.assertRedirects(self.entrar('admin@guios.test'),
                             reverse('presentation:admin-inicio'))

    def test_decisor_va_al_inicio_del_decisor(self):
        self.assertRedirects(self.entrar('decisor@guios.test'),
                             reverse('presentation:decisor-inicio'))

    def test_correo_en_mayusculas_tambien_entra(self):
        self.assertRedirects(self.entrar('ADMIN@Guios.TEST'),
                             reverse('presentation:admin-inicio'))

    def test_clave_incorrecta_no_entra_y_muestra_mensaje_generico(self):
        r = self.entrar('admin@guios.test', 'otra-clave')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Correo o contraseña incorrectos.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_correo_inexistente_da_el_mismo_mensaje(self):
        r = self.entrar('nadie@guios.test')
        self.assertContains(r, 'Correo o contraseña incorrectos.')

    def test_usuario_inactivo_no_entra_y_da_el_mismo_mensaje(self):
        r = self.entrar('baja@guios.test')
        self.assertContains(r, 'Correo o contraseña incorrectos.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_usuario_con_sesion_que_abre_el_login_es_redirigido(self):
        self.client.force_login(self.decisor)
        r = self.client.get(self.url)
        self.assertRedirects(r, reverse('presentation:decisor-inicio'))

    def test_logout_por_get_no_esta_permitido(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('presentation:logout'))
        self.assertEqual(r.status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

    def test_logout_por_post_cierra_la_sesion(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('presentation:logout'))
        self.assertRedirects(r, self.url)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_topbar_muestra_nombre_y_rol_del_usuario(self):
        self.client.force_login(self.decisor)
        r = self.client.get(reverse('presentation:decisor-inicio'))
        self.assertContains(r, 'Dario Decisor')
        self.assertContains(r, 'Decisor')
        self.assertContains(r, 'action="%s"' % reverse('presentation:logout'))
