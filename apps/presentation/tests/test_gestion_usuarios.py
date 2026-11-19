"""Pruebas de alta, edición, estado y seguridad de cuentas (HU01)."""
from django.contrib.admin.models import LogEntry
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.data.models import Usuario


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class GestionUsuariosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(
            correo='admin@guios.test', nombre='Ana Admin', rol=Usuario.ADMINISTRADOR)
        cls.decisor = Usuario.objects.create_user(
            correo='decisor@guios.test', nombre='Carlos Decisor', password='Clave-Original-123!')

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse('presentation:admin-usuarios-roles')

    def nuevo(self, **cambios):
        datos = {'accion': 'nuevo', 'nombre': 'Nueva Persona', 'correo': 'NUEVA@guios.test',
                 'rol': Usuario.DECISOR, 'password': 'Clave-Segura-684!z',
                 'confirmacion': 'Clave-Segura-684!z'}
        return self.client.post(self.url, {**datos, **cambios})

    def editar(self, usuario, **cambios):
        datos = {'accion': 'editar', 'usuario': usuario.pk, 'nombre': 'Nombre actualizado',
                 'correo': usuario.correo, 'rol': usuario.rol}
        return self.client.post(self.url, {**datos, **cambios})

    def estado(self, usuario, activo='0', motivo='Cambio institucional'):
        return self.client.post(self.url, {'accion': 'estado', 'usuario': usuario.pk,
                                          'activo': activo, 'motivo': motivo})

    def test_abre_formulario_de_alta(self):
        self.assertContains(self.client.get(self.url, {'accion': 'nuevo'}), 'Confirmar contraseña')

    def test_crea_usuario_con_hash_y_correo_normalizado(self):
        self.assertRedirects(self.nuevo(), self.url)
        usuario = Usuario.objects.get(correo='nueva@guios.test')
        self.assertTrue(usuario.check_password('Clave-Segura-684!z'))
        self.assertNotEqual(usuario.password, 'Clave-Segura-684!z')
        self.assertTrue(usuario.activo)
        self.assertTrue(LogEntry.objects.filter(object_id=str(usuario.pk), user_id=self.admin.pk).exists())

    def test_rechaza_correo_duplicado(self):
        self.assertContains(self.nuevo(correo='DECISOR@guios.test'), 'Este correo ya está registrado.')
        self.assertEqual(Usuario.objects.count(), 2)

    def test_rechaza_password_debil(self):
        r = self.nuevo(password='123', confirmacion='123')
        self.assertTrue(r.context['formulario_usuario'].errors)
        self.assertEqual(Usuario.objects.count(), 2)

    def test_rechaza_password_distinto(self):
        self.assertContains(self.nuevo(confirmacion='Otra-clave'), 'Las contraseñas no coinciden.')
        self.assertEqual(Usuario.objects.count(), 2)

    def test_rechaza_rol_invalido(self):
        r = self.nuevo(rol='SUPERADMIN')
        self.assertIn('rol', r.context['formulario_usuario'].errors)
        self.assertEqual(Usuario.objects.count(), 2)

    def test_edita_sin_cambiar_password(self):
        clave = self.decisor.password
        self.assertRedirects(self.editar(self.decisor, correo='actualizado@guios.test'), self.url)
        self.decisor.refresh_from_db()
        self.assertEqual(self.decisor.nombre, 'Nombre actualizado')
        self.assertEqual(self.decisor.correo, 'actualizado@guios.test')
        self.assertEqual(self.decisor.password, clave)

    def test_desactiva_y_reactiva_con_trazabilidad(self):
        self.assertRedirects(self.estado(self.decisor), self.url)
        self.decisor.refresh_from_db()
        self.assertFalse(self.decisor.activo)
        cliente = Client()
        self.assertFalse(cliente.login(correo=self.decisor.correo, password='Clave-Original-123!'))
        self.assertRedirects(self.estado(self.decisor, '1', 'Retorno institucional'), self.url)
        self.decisor.refresh_from_db()
        self.assertTrue(self.decisor.activo)
        self.assertTrue(cliente.login(correo=self.decisor.correo, password='Clave-Original-123!'))
        self.assertEqual(LogEntry.objects.filter(object_id=str(self.decisor.pk), user_id=self.admin.pk).count(), 2)
        self.assertTrue(LogEntry.objects.filter(change_message__contains='Cambio institucional').exists())

    def test_no_permite_desactivar_su_propia_cuenta(self):
        self.assertContains(self.estado(self.admin), 'No puedes cambiar el estado de tu propia cuenta.')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.activo)

    def test_no_permite_quitar_su_propio_rol(self):
        self.assertContains(self.editar(self.admin, rol=Usuario.DECISOR), 'No puedes cambiar tu propio rol.')
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.rol, Usuario.ADMINISTRADOR)

    def test_exige_motivo_de_cambio(self):
        r = self.estado(self.decisor, motivo='   ')
        self.assertIn('motivo', r.context['formulario_usuario'].errors)
        self.decisor.refresh_from_db()
        self.assertTrue(self.decisor.activo)

    def test_decisor_no_puede_modificar_cuentas(self):
        self.client.force_login(self.decisor)
        self.assertEqual(self.nuevo().status_code, 403)
        self.assertEqual(self.editar(self.admin).status_code, 403)
        self.assertEqual(self.estado(self.admin).status_code, 403)
        self.assertEqual(Usuario.objects.count(), 2)

    def test_post_exige_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        self.assertEqual(cliente.post(self.url, {'accion': 'nuevo'}).status_code, 403)

    def test_usuario_inexistente_devuelve_404(self):
        self.assertEqual(self.client.get(self.url, {'accion': 'editar', 'usuario': 99999}).status_code, 404)
