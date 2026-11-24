"""
Pruebas del menú lateral por rol (HU01).
"""

from django.test import TestCase
from django.urls import reverse

from apps.data.models import Usuario


class MenuLateralTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(
            correo='admin@guios.test', password='Clave-Segura-123',
            nombre='Ana Admin', rol=Usuario.ADMINISTRADOR)
        cls.decisor = Usuario.objects.create_user(
            correo='decisor@guios.test', password='Clave-Segura-123',
            nombre='Dario Decisor', rol=Usuario.DECISOR)

    def etiquetas(self, respuesta):
        return [i['etiqueta'] for i in respuesta.context['menu_items']]

    def test_el_administrador_ve_su_menu(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('presentation:admin-inicio'))
        self.assertEqual(self.etiquetas(r), [
            'Usuarios y roles', 'Actualización bibliográfica'])
        self.assertEqual(r.context['menu_seccion'], 'ADMINISTRACIÓN')

    def test_el_decisor_ve_su_menu(self):
        self.client.force_login(self.decisor)
        r = self.client.get(reverse('presentation:decisor-inicio'))
        self.assertEqual(self.etiquetas(r), [
            'Inicio', 'Nueva evaluación', 'Historial de evaluaciones'])
        self.assertEqual(r.context['menu_seccion'], 'ESPACIO DEL DECISOR')

    def test_el_logo_lleva_al_inicio_del_rol(self):
        self.client.force_login(self.decisor)
        r = self.client.get(reverse('presentation:decisor-inicio'))
        self.assertEqual(r.context['menu_inicio_url'], reverse('presentation:decisor-inicio'))

    def test_marca_como_activa_solo_la_pagina_actual(self):
        self.client.force_login(self.decisor)
        r = self.client.get(reverse('presentation:decisor-historial-evaluaciones'))
        activos = [i['etiqueta'] for i in r.context['menu_items'] if i['activo']]
        self.assertEqual(activos, ['Historial de evaluaciones'])

    def test_el_inicio_de_administracion_marca_usuarios_y_roles(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('presentation:admin-inicio'))
        activos = [i['etiqueta'] for i in r.context['menu_items'] if i['activo']]
        self.assertEqual(activos, ['Usuarios y roles'])

    def test_el_sidebar_dibuja_las_opciones_del_menu(self):
        self.client.force_login(self.decisor)
        r = self.client.get(reverse('presentation:decisor-inicio'))
        self.assertContains(r, 'Nueva evaluación')
        self.assertNotContains(r, 'Actualización bibliográfica')
