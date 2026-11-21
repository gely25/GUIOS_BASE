"""Pruebas de aceptación CP-05 para el registro de evaluaciones (HU05)."""

from datetime import date
import time

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.application.services.catalog import CatalogService
from apps.application.services.evaluation import EvaluationService
from apps.data.models import CatalogoVersion, Evaluacion, Organizacion, Usuario


class RegistroEvaluacionHU05Tests(TestCase):

    def setUp(self):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='INACTIVO')
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
        CatalogoVersion.objects.update(estado='HISTORICO')
        with self.assertRaises(ValidationError):
            EvaluationService.crear_evaluacion(self.decisor, self.datos_validos())


    def test_cp05_segunda_evaluacion_no_modifica_organizacion_historica(self):
        primera = EvaluationService.crear_evaluacion(
            self.decisor, self.datos_validos()
        )
        organizacion_primera = primera.organizacion
        datos_segunda = self.datos_validos()
        datos_segunda['nombre_organizacion'] = 'Universidad Nueva'
        datos_segunda['sector'] = 'Investigación'

        segunda = EvaluationService.crear_evaluacion(
            self.decisor, datos_segunda
        )

        organizacion_primera.refresh_from_db()
        self.assertEqual(organizacion_primera.nombre, 'Universidad Test')
        self.assertEqual(organizacion_primera.sector, 'Educación')
        self.assertNotEqual(segunda.organizacion_id, organizacion_primera.pk)
        self.assertEqual(segunda.organizacion.nombre, 'Universidad Nueva')
        self.assertEqual(self.decisor.organizacion_id, segunda.organizacion_id)

    def test_cp05_reutiliza_organizacion_historica_si_los_datos_no_cambian(self):
        primera = EvaluationService.crear_evaluacion(
            self.decisor, self.datos_validos()
        )
        segunda = EvaluationService.crear_evaluacion(
            self.decisor, self.datos_validos()
        )
        self.assertEqual(segunda.organizacion_id, primera.organizacion_id)

    def test_cp05_no_modifica_organizacion_compartida_con_otro_usuario(self):
        organizacion = Organizacion.objects.create(
            nombre='Organización compartida',
            sector='Educación',
        )
        self.decisor.organizacion = organizacion
        self.decisor.save(update_fields=['organizacion'])
        otro = Usuario.objects.create_user(
            correo='otro.hu05@guios.test',
            password='Clave-Segura-123',
            nombre='Otro decisor',
            rol=Usuario.DECISOR,
            organizacion=organizacion,
        )
        datos = self.datos_validos()
        datos['nombre_organizacion'] = 'Organización actualizada'

        evaluacion = EvaluationService.crear_evaluacion(self.decisor, datos)

        organizacion.refresh_from_db()
        otro.refresh_from_db()
        self.assertEqual(organizacion.nombre, 'Organización compartida')
        self.assertEqual(otro.organizacion_id, organizacion.pk)
        self.assertNotEqual(evaluacion.organizacion_id, organizacion.pk)
        self.assertEqual(
            evaluacion.organizacion.nombre,
            'Organización actualizada',
        )

    def test_cp05_actualiza_organizacion_exclusiva_sin_historial(self):
        organizacion = Organizacion.objects.create(
            nombre='Organización inicial',
            sector='Educación',
        )
        self.decisor.organizacion = organizacion
        self.decisor.save(update_fields=['organizacion'])
        datos = self.datos_validos()
        datos['nombre_organizacion'] = 'Organización corregida'

        evaluacion = EvaluationService.crear_evaluacion(self.decisor, datos)

        organizacion.refresh_from_db()
        self.assertEqual(evaluacion.organizacion_id, organizacion.pk)
        self.assertEqual(organizacion.nombre, 'Organización corregida')

    def test_cp05_catalogo_demo_no_se_selecciona_como_vigente(self):
        CatalogoVersion.objects.create(
            version='GUIOS-DEMO-TEST',
            fecha_creacion=date.today(),
            estado='DEMO',
        )
        self.assertEqual(
            CatalogService.obtener_version_vigente().pk,
            self.catalogo.pk,
        )

    def test_cp05_fecha_actualizacion_cambia_al_modificar_evaluacion(self):
        evaluacion = EvaluationService.crear_evaluacion(
            self.decisor, self.datos_validos()
        )
        fecha_original = evaluacion.fecha_actualizacion
        time.sleep(0.01)

        evaluacion.estado = Evaluacion.CERRADA
        evaluacion.save()
        evaluacion.refresh_from_db()

        self.assertGreater(evaluacion.fecha_actualizacion, fecha_original)

    def test_cp05_no_admite_administrador(self):
        administrador = Usuario.objects.create_superuser(
            correo='admin.hu05@guios.test',
            password='Clave-Segura-123',
            nombre='Admin HU05',
        )
        with self.assertRaises(ValidationError):
            EvaluationService.crear_evaluacion(administrador, self.datos_validos())
