"""El interruptor de usuarios activa el flujo seguro y sustituye botones duplicados."""
from django.test import TestCase
from django.urls import reverse

from apps.data.models import Usuario


class InterruptorEstadoUsuariosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(
            correo='admin-toggle@guios.test', nombre='Admin Toggle', rol=Usuario.ADMINISTRADOR)
        cls.activo = Usuario.objects.create_user(
            correo='activo-toggle@guios.test', nombre='Activo Toggle', activo=True)
        cls.inactivo = Usuario.objects.create_user(
            correo='inactivo-toggle@guios.test', nombre='Inactivo Toggle', activo=False)

    def setUp(self):
        self.url = reverse('presentation:admin-usuarios-roles')
        self.client.force_login(self.admin)

    def test_interruptor_abre_confirmacion_sin_botones_duplicados(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        for usuario, etiqueta in ((self.activo, 'Desactivar'), (self.inactivo, 'Activar')):
            with self.subTest(usuario=usuario.pk):
                self.assertContains(r, f'accion=estado&amp;usuario={usuario.pk}#formulario-usuario')
                self.assertContains(r, f'{etiqueta} a {usuario.nombre} (requiere confirmación y motivo)')
        self.assertNotContains(r, 'usuarios-boton-secundario')
        self.assertNotContains(r, f'accion=estado&amp;usuario={self.admin.pk}#formulario-usuario')
        self.assertContains(r, 'No puedes cambiar el estado de tu propia cuenta')

    def test_click_interruptor_solo_abre_formulario_no_cambia_estado(self):
        r = self.client.get(self.url, {'accion': 'estado', 'usuario': self.activo.pk})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Motivo del cambio')
        self.assertContains(r, 'Confirmar cambio')
        self.activo.refresh_from_db()
        self.assertTrue(self.activo.activo)

    def test_confirmar_interruptor_desactiva_y_puede_reactivar(self):
        for valor, esperado in [('0', False), ('1', True)]:
            with self.subTest(activo=valor):
                r = self.client.post(self.url, {
                    'accion': 'estado', 'usuario': self.activo.pk,
                    'activo': valor, 'motivo': 'Cambio validado por administración',
                })
                self.assertRedirects(r, self.url)
                self.activo.refresh_from_db()
                self.assertIs(self.activo.activo, esperado)
