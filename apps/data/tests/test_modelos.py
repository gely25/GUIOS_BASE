"""
Pruebas del modelo de usuario (acceso por correo y rol) y de las restricciones del catálogo.

Usan la base de datos de pruebas de Django.
"""

from datetime import date

from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.data.models import CatalogoVersion, Dimension, Factor, IndicadorFactor, Usuario


class UsuarioTests(TestCase):

    def setUp(self):
        self.decisor = Usuario.objects.create_user(
            '  Decisor@Ejemplo.COM ', 'ClaveSegura#1', nombre='Ana')
        self.admin = Usuario.objects.create_superuser(
            'admin@ejemplo.com', 'ClaveSegura#2', nombre='Admin')

    def test_el_correo_se_guarda_en_minusculas_y_sin_espacios(self):
        self.assertEqual(self.decisor.correo, 'decisor@ejemplo.com')

    def test_el_rol_por_defecto_es_decisor(self):
        self.assertEqual(self.decisor.rol, Usuario.DECISOR)
        self.assertEqual(self.admin.rol, Usuario.ADMINISTRADOR)

    def test_la_clave_se_guarda_con_hash(self):
        self.assertNotIn('ClaveSegura#1', self.decisor.password)
        self.assertTrue(self.decisor.check_password('ClaveSegura#1'))

    def test_inicia_sesion_con_el_correo_sin_importar_mayusculas(self):
        for correo in ('Decisor@Ejemplo.com', 'decisor@ejemplo.com', 'DECISOR@EJEMPLO.COM'):
            with self.subTest(correo=correo):
                self.assertIsNotNone(authenticate(username=correo, password='ClaveSegura#1'))

    def test_clave_incorrecta_o_correo_inexistente_no_entran(self):
        self.assertIsNone(authenticate(username='decisor@ejemplo.com', password='mala'))
        self.assertIsNone(authenticate(username='nadie@ejemplo.com', password='ClaveSegura#1'))

    def test_un_usuario_inactivo_no_entra(self):
        self.decisor.activo = False
        self.decisor.save()
        self.assertIsNone(authenticate(username='decisor@ejemplo.com', password='ClaveSegura#1'))

    def test_solo_el_administrador_accede_al_admin_de_django(self):
        self.assertFalse(self.decisor.is_staff)
        self.assertFalse(self.decisor.is_superuser)
        self.assertTrue(self.admin.is_staff)
        self.assertTrue(self.admin.has_perm('cualquiera'))

    def test_la_base_rechaza_un_rol_invalido(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Usuario.objects.create_user('otro@ejemplo.com', 'x', nombre='Otro', rol='SUPERROL')

    def test_no_se_permiten_dos_usuarios_con_el_mismo_correo(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Usuario.objects.create_user('DECISOR@ejemplo.com', 'x', nombre='Copia')


class RestriccionesCatalogoTests(TestCase):

    def setUp(self):
        self.dimension = Dimension.objects.create(nombre='Tecnológica')

    def test_la_base_rechaza_un_alcance_invalido(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Factor.objects.create(dimension=self.dimension, nombre='Compatibilidad', alcance='otro')

    def test_la_base_rechaza_una_importancia_fuera_de_1_a_4(self):
        factor = Factor.objects.create(
            dimension=self.dimension, nombre='Compatibilidad', alcance=Factor.EXTERNO)
        catalogo = CatalogoVersion.objects.create(version='v1', fecha_creacion=date.today())
        with self.assertRaises(IntegrityError), transaction.atomic():
            IndicadorFactor.objects.create(
                catalogo=catalogo, factor=factor, numero_subfactores=3, importancia_sugerida=5)
