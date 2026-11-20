"""Pruebas de aceptación CP-05 para el registro de evaluaciones (HU05)."""

from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.application.services.evaluation import EvaluationService
from apps.data.models import CatalogoVersion, Usuario


class RegistroEvaluacionHU05Tests(TestCase):

    def setUp(self):
        self.decisor = Usuario.objects.create_user(
            correo='decisor.hu05@guios.test',
            password='Clave-Segura-123',
            nombre='Decisor HU05',
            rol=Usuario.DECISOR,
        )
        self.catalogo = CatalogoVersion.objects.create(
            version='GUIOS-TEST-V1',
            fecha_creacion=date.today(),
            estado='ACTIVO',
        )

    def datos_validos(self):
        return {
            'nombre_organizacion': 'Universidad Test',
            'sector': 'Educación',
            'tamano': 'Mediana',
            'objetivo_adopcion': 'Reducir costos de licencias',
            'nombre_software': 'LibreOffice',
            'version_software': '24.2',
            'proveedor': 'The Document Foundation',
            'descripcion_software': 'Suite de productividad',
        }

    def test_caso_cp05_guarda_organizacion_software_usuario_catalogo_y_estado(self):
        evaluacion = EvaluationService.crear_evaluacion(self.decisor, self.datos_validos())

        self.assertEqual(evaluacion.organizacion.nombre, 'Universidad Test')
        self.assertEqual(evaluacion.organizacion.sector, 'Educación')
        self.assertEqual(evaluacion.software.nombre, 'LibreOffice')
        self.assertEqual(evaluacion.software.version, '24.2')
        self.assertEqual(evaluacion.usuario, self.decisor)
        self.assertEqual(evaluacion.catalogo, self.catalogo)
        self.assertEqual(evaluacion.estado, 'EN_PROCESO')
        self.assertIsNone(evaluacion.fecha_fin)
        self.assertIsNotNone(evaluacion.fecha_inicio)
        self.assertIsNotNone(evaluacion.fecha_actualizacion)

    def test_cp05_falla_sin_nombre_de_organizacion(self):
        datos = self.datos_validos()
        datos['nombre_organizacion'] = '   '
        with self.assertRaises(ValidationError):
            EvaluationService.crear_evaluacion(self.decisor, datos)

    def test_cp05_falla_sin_nombre_de_software(self):
        datos = self.datos_validos()
        datos['nombre_software'] = ''
        with self.assertRaises(ValidationError):
            EvaluationService.crear_evaluacion(self.decisor, datos)

    def test_cp05_falla_si_no_hay_catalogo_vigente(self):
        self.catalogo.estado = 'INACTIVO'
        self.catalogo.save()
        with self.assertRaises(ValidationError):
            EvaluationService.crear_evaluacion(self.decisor, self.datos_validos())

    def test_cp05_no_admite_administrador(self):
        administrador = Usuario.objects.create_superuser(
            correo='admin.hu05@guios.test',
            password='Clave-Segura-123',
            nombre='Admin HU05',
        )
        with self.assertRaises(ValidationError):
            EvaluationService.crear_evaluacion(administrador, self.datos_validos())
