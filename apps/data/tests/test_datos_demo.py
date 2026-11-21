from io import StringIO
from datetime import date
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.data.models import CatalogoVersion, Usuario


class DatosDemoTests(TestCase):

    def cargar(self):
        salida = StringIO()
        call_command('cargar_datos_demo', stdout=salida)
        return salida.getvalue()

    def test_crea_un_usuario_por_cada_caso(self):
        self.cargar()
        self.assertEqual(Usuario.objects.get(correo='admin.demo@guios.local').rol,
                         Usuario.ADMINISTRADOR)
        self.assertEqual(Usuario.objects.get(correo='decisor.demo@guios.local').rol,
                         Usuario.DECISOR)
        self.assertFalse(Usuario.objects.get(correo='inactivo.demo@guios.local').activo)

    def test_se_puede_correr_dos_veces_sin_duplicar(self):
        self.cargar()
        self.cargar()
        self.assertEqual(Usuario.objects.filter(correo__endswith='.demo@guios.local').count(), 3)

    def test_catalogo_demo_no_desplaza_al_catalogo_vigente(self):
        vigente = CatalogoVersion.objects.create(
            version='GUIOS-V1',
            fecha_creacion=date.today(),
            estado='ACTIVO',
        )

        self.cargar()

        vigente.refresh_from_db()
        demo = CatalogoVersion.objects.get(version='GUIOS-DEMO-V1')

        self.assertEqual(vigente.estado, 'ACTIVO')
        self.assertEqual(demo.estado, 'DEMO')
        self.assertEqual(
            CatalogoVersion.objects.filter(estado='ACTIVO').count(),
            1,
        )

    def test_las_contrasenas_demo_permiten_entrar(self):
        self.cargar()
        self.assertTrue(self.client.login(username='admin.demo@guios.local',
                                          password='Demo-Admin-123'))
        self.client.logout()
        self.assertFalse(self.client.login(username='inactivo.demo@guios.local',
                                           password='Demo-Inactivo-123'))

    def test_se_niega_en_una_base_que_no_es_de_desarrollo(self):
        from django.db import connection
        original = connection.settings_dict['NAME']
        connection.settings_dict['NAME'] = 'guios_pro_produccion'
        try:
            with self.assertRaises(CommandError):
                self.cargar()
        finally:
            connection.settings_dict['NAME'] = original
