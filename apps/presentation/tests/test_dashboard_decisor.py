"""Regresión del dashboard del decisor contra GUIOS_2: Inicio."""

from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.data.models import (
    CatalogoVersion, Dimension, Documento, Evaluacion, EvaluacionFactor,
    Evidencia, Factor, FragmentoDocumento, Organizacion, Software,
    Subfactor, Usuario, ValoracionSubfactor,
)


class DashboardDecisorFigmaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        cls.org = Organizacion.objects.create(
            nombre='Institución de prueba', objetivo_adopcion='Ofimática institucional')
        cls.actor = Usuario.objects.create_user(
            'panel-figma@guios.test', 'clave-segura', nombre='Ana Decisora', organizacion=cls.org)
        cls.otro = Usuario.objects.create_user(
            'otro-figma@guios.test', 'clave-segura', nombre='Otro Decisor', organizacion=cls.org)
        cls.catalogo = CatalogoVersion.objects.create(
            version='PANEL-FIGMA-PRUEBA', fecha_creacion=date.today())
        cls.abierta = Evaluacion.objects.create(
            organizacion=cls.org, usuario=cls.actor, catalogo=cls.catalogo,
            software=Software.objects.create(nombre='Moodle', version='4.5'),
            estado=Evaluacion.EN_PROCESO)
        cls.cerrada = Evaluacion.objects.create(
            organizacion=cls.org, usuario=cls.actor, catalogo=cls.catalogo,
            software=Software.objects.create(nombre='LibreOffice', version='25.2'),
            estado=Evaluacion.CERRADA, fecha_fin=timezone.now())
        cls.ajena = Evaluacion.objects.create(
            organizacion=cls.org, usuario=cls.otro, catalogo=cls.catalogo,
            software=Software.objects.create(nombre='Proyecto Confidencial'),
            estado=Evaluacion.EN_PROCESO)
        cls.url = reverse('presentation:decisor-inicio')

    def setUp(self):
        self.client.force_login(self.actor)

    def test_indicadores_tres_tarjetas_y_privacidad(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['indicadores']['total'], 2)
        self.assertEqual(res.context['indicadores']['en_proceso'], 1)
        self.assertEqual(res.context['indicadores']['cerradas'], 1)
        self.assertEqual(res.context['indicadores']['documentos_revisados'], 0)
        self.assertContains(res, 'En curso')
        self.assertContains(res, 'Completadas')
        self.assertContains(res, 'Documentos revisados')
        self.assertContains(res, 'Continúe su evaluación')
        self.assertContains(res, 'Moodle 4.5')
        self.assertNotContains(res, 'Proyecto Confidencial')

    def test_tabla_con_proposito_y_enlaces_personales(self):
        res = self.client.get(self.url)
        self.assertContains(res, 'Evaluaciones recientes')
        self.assertContains(res, 'Ofimática institucional')
        self.assertContains(res, 'LibreOffice 25.2')
        self.assertContains(res, f'evaluacion_id={self.abierta.pk}')
        self.assertNotContains(res, f'evaluacion_id={self.ajena.pk}')

    def test_progreso_refleja_solo_confirmaciones(self):
        dimension = Dimension.objects.create(nombre='Tecnológica Figma')
        factor = Factor.objects.create(
            dimension=dimension, nombre='Compatibilidad Figma', alcance=Factor.INTERNO)
        subfactor1 = Subfactor.objects.create(factor=factor, descripcion='Formato de archivo')
        subfactor2 = Subfactor.objects.create(factor=factor, descripcion='Compatibilidad adicional')
        ef = EvaluacionFactor.objects.create(
            evaluacion=self.abierta, factor=factor,
            importancia_relativa=3, relevante=True)
        confirmada = ValoracionSubfactor.objects.create(
            evaluacion_factor=ef, subfactor=subfactor1, valor_confirmado=3)
        ValoracionSubfactor.objects.create(
            evaluacion_factor=ef, subfactor=subfactor2)

        res = self.client.get(self.url)
        self.assertEqual(res.context['progreso']['total'], 2)
        self.assertEqual(res.context['progreso']['confirmadas'], 1)
        self.assertEqual(res.context['progreso']['porcentaje'], 50)
        self.assertContains(res, '1 de 2 valoraciones confirmadas')
        self.assertContains(res, 'Paso 4 de 6')
        self.assertContains(res, f'evaluacion={self.abierta.pk}')

        documento = Documento.objects.create(
            evaluacion=self.abierta, usuario=self.actor, nombre='evidencia.pdf',
            tipo='PDF', ubicacion='archivo-de-prueba.pdf')
        fragmento = FragmentoDocumento.objects.create(
            documento=documento, contenido='El sistema admite ODF')
        Evidencia.objects.create(valoracion=confirmada, fragmento=fragmento)
        res = self.client.get(self.url)
        self.assertEqual(res.context['indicadores']['documentos_revisados'], 1)

    def test_no_cuenta_documentos_ajenos_o_no_validados(self):
        doc = Documento.objects.create(
            evaluacion=self.abierta, usuario=self.actor, nombre='sin-confirmar.pdf',
            tipo='PDF', ubicacion='sin-confirmar.pdf')
        FragmentoDocumento.objects.create(documento=doc, contenido='Información sin confirmar')
        doc_ajeno = Documento.objects.create(
            evaluacion=self.ajena, usuario=self.otro, nombre='privado.pdf',
            tipo='PDF', ubicacion='privado.pdf')
        FragmentoDocumento.objects.create(documento=doc_ajeno, contenido='Información privada')
        res = self.client.get(self.url)
        self.assertEqual(res.context['indicadores']['documentos_revisados'], 0)

    def test_estado_vacio(self):
        usuario = Usuario.objects.create_user(
            'sin-evaluaciones-figma@guios.test', 'clave-segura', nombre='Nuevo Decisor')
        self.client.force_login(usuario)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['indicadores']['en_proceso'], 0)
        self.assertContains(res, 'Aún no hay evaluaciones registradas')
        self.assertContains(res, 'Iniciar ficha de evaluación')

    def test_greeting_personalizado_y_sin_nombre_ficticio(self):
        res = self.client.get(self.url)
        self.assertContains(res, 'Ana')
        self.assertNotContains(res, 'Ana Martínez')
