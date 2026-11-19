"""Pruebas de la presentación de la gestión de usuarios."""
from django.test import TestCase
from django.urls import reverse
from apps.data.models import Usuario


class UsuariosInterfazTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(correo='admin@guios.test',
                                               nombre='Admin', rol=Usuario.ADMINISTRADOR)

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse('presentation:admin-usuarios-roles')

    def test_alta_selecciona_decisor_y_presenta_dialogo(self):
        r = self.client.get(self.url, {'accion': 'nuevo'})
        self.assertEqual(r.context['formulario_usuario']['rol'].value(), Usuario.DECISOR)
        self.assertContains(r, '<dialog open', html=False)
        self.assertContains(r, 'aria-controls="id_password"')
        self.assertContains(r, 'aria-controls="id_confirmacion"')

    def test_etiquetas_de_estado_y_proteccion_visual(self):
        Usuario.objects.create_user(correo='inactivo@guios.test', nombre='Inactivo', activo=False)
        r = self.client.get(self.url)
        self.assertContains(r, 'usuarios-activo')
        self.assertContains(r, 'usuarios-inactivo')
        self.assertNotContains(r, f'accion=estado&amp;usuario={self.admin.pk}#formulario-usuario')

    def test_mensaje_de_edicion_es_especifico(self):
        r = self.client.post(self.url, {'accion': 'editar', 'usuario': self.admin.pk,
            'nombre': 'Admin editado', 'correo': self.admin.correo, 'rol': self.admin.rol}, follow=True)
        self.assertContains(r, 'Usuario actualizado correctamente.')
