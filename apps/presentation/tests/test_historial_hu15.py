"""Pruebas específicas del historial de evaluaciones (HU15)."""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.data.models import (
    CatalogoVersion, Dimension, Evaluacion, EvaluacionFactor, Factor,
    Organizacion, ResultadoEvaluacion, Software, Usuario,
)


class HistorialHU15Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        cls.organizacion = Organizacion.objects.create(nombre="Organización HU15")
        cls.actor = Usuario.objects.create_user(
            "historial@guios.test", "Clave-Segura-123",
            nombre="Decisor HU15", organizacion=cls.organizacion)
        cls.otro = Usuario.objects.create_user(
            "otro-historial@guios.test", "Clave-Segura-123",
            nombre="Otro Decisor", organizacion=cls.organizacion)
        cls.catalogo = CatalogoVersion.objects.create(
            version="HU15", fecha_creacion=date.today())

        cls.evaluacion = Evaluacion.objects.create(
            organizacion=cls.organizacion, usuario=cls.actor, catalogo=cls.catalogo,
            software=Software.objects.create(
                nombre="LibreOffice", version="24.8", proveedor="The Document Foundation"),
            estado=Evaluacion.CERRADA, fecha_fin=timezone.now())
        ResultadoEvaluacion.objects.create(
            evaluacion=cls.evaluacion, recomendacion="Adoptar el FLOSS seleccionado",
            version_regla="1.0")

        dimension = Dimension.objects.create(nombre="Tecnológica HU15")
        factor = Factor.objects.create(
            dimension=dimension, nombre="Compatibilidad HU15", alcance=Factor.EXTERNO)
        EvaluacionFactor.objects.create(
            evaluacion=cls.evaluacion, factor=factor,
            ponderacion_media=Decimal("3.50"), clasificacion_foda="Fortaleza")

        cls.sin_recomendacion = Evaluacion.objects.create(
            organizacion=cls.organizacion, usuario=cls.actor, catalogo=cls.catalogo,
            software=Software.objects.create(nombre="PostgreSQL", version="17"),
            estado=Evaluacion.EN_PROCESO)

        cls.ajena = Evaluacion.objects.create(
            organizacion=cls.organizacion, usuario=cls.otro, catalogo=cls.catalogo,
            software=Software.objects.create(nombre="Software Ajeno", version="1"),
            estado=Evaluacion.CERRADA)

        cls.url = reverse("presentation:decisor-historial-evaluaciones")

    def cliente(self, usuario=None):
        self.client.force_login(usuario or self.actor)
        return self.client

    def test_lista_solo_evaluaciones_del_decisor_con_todos_los_datos(self):
        respuesta = self.cliente().get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "presentation/decisor/historial_evaluaciones.html")
        self.assertContains(respuesta, "EV-%03d" % self.evaluacion.pk)
        self.assertContains(respuesta, "LibreOffice 24.8")
        self.assertContains(respuesta, "Organización HU15")
        self.assertContains(respuesta, "The Document Foundation")
        self.assertContains(respuesta, "Calculada")
        self.assertContains(respuesta, "Cerrada")
        self.assertContains(respuesta, "Adoptar el FLOSS seleccionado")
        self.assertNotContains(respuesta, "Software Ajeno")

    def test_estado_vacio(self):
        usuario = Usuario.objects.create_user(
            "vacio-historial@guios.test", "Clave-Segura-123",
            nombre="Sin historial", rol=Usuario.DECISOR)
        respuesta = self.cliente(usuario).get(self.url)
        self.assertContains(respuesta, "Aún no hay evaluaciones registradas")
        self.assertContains(respuesta, "Iniciar ficha de evaluación")

    def test_enlaces_resultados_e_informe_respetan_la_recomendacion(self):
        respuesta = self.cliente().get(self.url)
        resultados = reverse("presentation:decisor-resultados")
        informe = reverse("presentation:decisor-informe")
        self.assertContains(respuesta, f'{resultados}?evaluacion={self.evaluacion.pk}')
        self.assertContains(respuesta, f'{informe}?evaluacion={self.evaluacion.pk}')
        self.assertContains(
            respuesta,
            f'{resultados}?evaluacion={self.sin_recomendacion.pk}')
        self.assertNotContains(
            respuesta,
            f'{informe}?evaluacion={self.sin_recomendacion.pk}')

    def test_informe_directo_sin_recomendacion_no_abre_resultado(self):
        respuesta = self.cliente().get(
            reverse("presentation:decisor-informe"),
            {"evaluacion": self.sin_recomendacion.pk})
        self.assertEqual(respuesta.status_code, 404)

    def test_indicadores_y_filtros_del_historial(self):
        respuesta = self.cliente().get(self.url)
        self.assertEqual(respuesta.context["total"], 2)
        self.assertEqual(respuesta.context["con_informe"], 1)
        self.assertEqual(respuesta.context["en_curso"], 1)
        self.assertContains(respuesta, 'id="historial-buscar"')
        self.assertContains(respuesta, 'data-estado="en curso"')
        self.assertContains(respuesta, 'data-estado="cerrada"')
