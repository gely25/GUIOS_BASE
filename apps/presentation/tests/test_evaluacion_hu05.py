"""Pruebas funcionales CP-05 de la pantalla de registro."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.data.models import CatalogoVersion, Usuario


class RegistroEvaluacionInterfazHU05Tests(TestCase):

    def setUp(self):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='INACTIVO')
        self.decisor = Usuario.objects.create_user(
            correo='decisor.hu05.ui@guios.test',
            password='Clave-Segura-123',
            nombre='Decisor Interfaz',
            rol=Usuario.DECISOR,
        )
        CatalogoVersion.objects.create(
            version='GUIOS-TEST-UI-V1',
            fecha_creacion=date.today(),
            estado='ACTIVO',
        )
        self.url = reverse('presentation:decisor-ficha-inicial')

    def test_cp05_muestra_formulario_a_usuario_autenticado(self):
        self.client.force_login(self.decisor)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Ficha inicial de evaluación')
        self.assertContains(respuesta, 'Nombre de la organización')
        self.assertContains(respuesta, 'Nombre del software')

    def test_cp05_registra_por_post_y_asocia_la_evaluacion(self):
        self.client.force_login(self.decisor)
        respuesta = self.client.post(self.url, {
            'nombre_organizacion': 'Instituto QA',
            'sector': 'Tecnología',
            'tamano': 'Pequeña',
            'objetivo_adopcion': 'Evaluar adopción FLOSS',
            'nombre_software': 'OpenOffice',
            'version_software': '4.1',
            'proveedor': '',
            'descripcion_software': '',
        })

        self.assertEqual(respuesta.status_code, 302)
        evaluacion = self.decisor.evaluaciones.select_related(
            'organizacion', 'software', 'catalogo',
        ).get()
        self.assertEqual(respuesta.url, (
            f'{reverse("presentation:decisor-importancia-factores")}'
            f'?evaluacion_id={evaluacion.pk}'
        ))
        self.assertEqual(evaluacion.organizacion.nombre, 'Instituto QA')
        self.assertEqual(evaluacion.software.nombre, 'OpenOffice')
        self.assertEqual(evaluacion.catalogo.version, 'GUIOS-TEST-UI-V1')
        self.assertEqual(evaluacion.estado, 'EN_PROCESO')

        siguiente = self.client.get(respuesta.url)
        self.assertEqual(siguiente.status_code, 200)
        self.assertContains(siguiente, 'Importancia de factores')
        self.assertContains(siguiente, f'Evaluación #{evaluacion.pk} registrada')

    def test_cp05_formulario_falla_sin_campos_obligatorios(self):
        self.client.force_login(self.decisor)
        respuesta = self.client.post(self.url, {
            'nombre_organizacion': '',
            'nombre_software': '',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Este campo es obligatorio')

    def test_cp05_administrador_no_accede_a_la_ruta(self):
        administrador = Usuario.objects.create_superuser(
            correo='admin.hu05.ui@guios.test',
            password='Clave-Segura-123',
            nombre='Admin Interfaz',
        )
        self.client.force_login(administrador)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 403)
