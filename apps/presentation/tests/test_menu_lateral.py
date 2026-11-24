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


class SesionYGuiaEnElMenuTests(TestCase):
    """La sesión de la persona usuaria y la guía viven al pie del menú, en todos los roles."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(
            correo='admin2@guios.test', password='Clave-Segura-123',
            nombre='Ana Admin', rol=Usuario.ADMINISTRADOR)
        cls.decisor = Usuario.objects.create_user(
            correo='decisor2@guios.test', password='Clave-Segura-123',
            nombre='Dario Decisor', rol=Usuario.DECISOR)

    def paginas(self):
        return [
            (self.admin, reverse('presentation:admin-inicio'), 'Ana Admin', 'Administrador'),
            (self.decisor, reverse('presentation:decisor-inicio'), 'Dario Decisor', 'Decisor'),
            (self.decisor, reverse('presentation:decisor-historial-evaluaciones'), 'Dario Decisor', 'Decisor'),
        ]

    def test_nombre_rol_e_inicial_estan_en_el_menu_lateral(self):
        for usuario, url, nombre, rol in self.paginas():
            with self.subTest(url=url):
                self.client.force_login(usuario)
                r = self.client.get(url)
                self.assertContains(r, 'class="sidebar-usuario-nombre">%s<' % nombre)
                self.assertContains(r, 'class="sidebar-usuario-rol">%s<' % rol)
                self.assertContains(r, 'class="sidebar-usuario-inicial" aria-hidden="true">%s<' % nombre[0])

    def test_cerrar_sesion_esta_una_sola_vez_y_no_en_la_barra_superior(self):
        for usuario, url, _, _ in self.paginas():
            with self.subTest(url=url):
                self.client.force_login(usuario)
                r = self.client.get(url)
                self.assertContains(r, 'action="%s"' % reverse('presentation:logout'), count=1)
                self.assertNotContains(r, 'user-role-badge')
                self.assertNotContains(r, 'topbar-logout')

    def test_la_guia_metodologica_es_una_ventana_con_sus_cuatro_secciones(self):
        self.client.force_login(self.decisor)
        r = self.client.get(reverse('presentation:decisor-inicio'))
        self.assertContains(r, '<dialog class="guia-ventana"')
        self.assertContains(r, 'data-abrir-guia')
        for seccion in ('Los 6 pasos', 'Cómo se calcula', 'IA y decisor', 'Glosario'):
            self.assertContains(r, seccion)
        self.assertContains(r, 'Es posible adoptar, con matices')

    def test_el_texto_de_la_guia_coincide_con_la_regla_del_sistema(self):
        from apps.application.services.recomendacion import TEXTOS_RECOMENDACION
        from apps.business_rules.foda import UMBRAL_PM
        self.client.force_login(self.decisor)
        r = self.client.get(reverse('presentation:decisor-inicio'))
        for texto in TEXTOS_RECOMENDACION.values():
            self.assertContains(r, texto)
        self.assertContains(r, 'el corte es %d' % UMBRAL_PM)
