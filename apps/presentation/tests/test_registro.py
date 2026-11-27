"""Pruebas del registro público y sus permisos."""

from django.test import TestCase
from django.urls import reverse

from apps.data.models import Usuario


class RegistroTests(TestCase):

    def setUp(self):
        self.url = reverse('presentation:registro')
        self.datos = {'nombre': '  Laura   Pérez ', 'correo': 'Laura@Empresa.com',
                      'password1': 'Clave-Segura-123', 'password2': 'Clave-Segura-123'}

    def test_se_abre_sin_sesion_y_el_login_enlaza_al_registro(self):
        res = self.client.get(self.url)
        self.assertContains(res, 'Crear cuenta')
        self.assertContains(res, 'Decisor')
        self.assertNotContains(res, 'name="rol"')
        self.assertContains(self.client.get(reverse('presentation:home')), self.url)

    def test_crea_un_decisor_guarda_la_clave_cifrada_e_inicia_sesion(self):
        res = self.client.post(self.url, self.datos)
        self.assertRedirects(res, reverse('presentation:decisor-inicio'))
        usuario = Usuario.objects.get(correo='laura@empresa.com')
        self.assertEqual((usuario.nombre, usuario.rol, usuario.activo, usuario.organizacion),
                         ('Laura Pérez', Usuario.DECISOR, True, None))
        self.assertNotEqual(usuario.password, 'Clave-Segura-123')
        self.assertTrue(usuario.check_password('Clave-Segura-123'))
        self.assertEqual(int(self.client.session['_auth_user_id']), usuario.pk)

    def test_un_rol_administrativo_inyectado_no_otorga_acceso(self):
        res = self.client.post(self.url, {**self.datos, 'rol': Usuario.ADMINISTRADOR})
        self.assertRedirects(res, reverse('presentation:decisor-inicio'))
        self.assertEqual(Usuario.objects.get().rol, Usuario.DECISOR)
        self.assertEqual(self.client.get(reverse('presentation:admin-inicio')).status_code, 403)

    def test_rechaza_un_correo_repetido_sin_importar_mayusculas(self):
        Usuario.objects.create_user(correo='laura@empresa.com', password='x-Clave-123', nombre='Otra')
        res = self.client.post(self.url, self.datos)
        self.assertContains(res, 'Ya existe una cuenta con este correo')
        self.assertEqual(Usuario.objects.count(), 1)

    def test_rechaza_claves_que_no_coinciden_o_son_debiles(self):
        res = self.client.post(self.url, {**self.datos, 'password2': 'otra-cosa-123'})
        self.assertContains(res, 'Las contraseñas no coinciden.')
        res = self.client.post(self.url, {**self.datos, 'password1': '12345678', 'password2': '12345678'})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Usuario.objects.exists())

    def test_una_persona_con_sesion_no_ve_el_registro(self):
        self.client.post(self.url, self.datos)
        self.assertRedirects(self.client.get(self.url), reverse('presentation:decisor-inicio'))
