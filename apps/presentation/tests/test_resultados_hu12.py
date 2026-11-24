"""Resultados (paso 5): PM, matriz FODA y perfil de cumplimiento a partir de lo calculado por HU12."""
from datetime import date
from decimal import Decimal

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.data.models import (CatalogoVersion, Dimension, Evaluacion, EvaluacionFactor, Factor,
                              Organizacion, ResultadoEvaluacion, Software, Subfactor, Usuario,
                              ValoracionSubfactor)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ResultadosHU12Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        org = Organizacion.objects.create(nombre='Universidad Demo')
        cls.actor = Usuario.objects.create_user('res12@test.local', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cls.otro = Usuario.objects.create_user('otro-res12@test.local', 'Clave-test-123', nombre='Otro', organizacion=org)
        cat = CatalogoVersion.objects.create(version='HU12 res', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor, catalogo=cat,
                                           software=Software.objects.create(nombre='LibreGestión', version='3.2'))
        dim = Dimension.objects.create(nombre='Tecnológica')
        datos = [('Usabilidad', 4, Decimal('3.50'), 'Fortaleza', (4, 3)),
                 ('Compatibilidad', 4, Decimal('3.00'), 'Amenaza', (3, 3)),
                 ('Soporte', 3, Decimal('4.00'), 'Oportunidad', (4, 4)),
                 ('Coste', 3, Decimal('2.50'), 'Debilidad', (2, 3))]
        for nombre, ir, pm, foda, valores in datos:
            f = Factor.objects.create(dimension=dim, nombre=nombre, alcance=Factor.EXTERNO)
            ef = EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=f, importancia_relativa=ir,
                                                 ponderacion_media=pm, clasificacion_foda=foda)
            for i, valor in enumerate(valores):
                ValoracionSubfactor.objects.create(
                    evaluacion_factor=ef, subfactor=Subfactor.objects.create(factor=f, descripcion=f'{nombre} {i}'),
                    valor_confirmado=valor, estado_validacion='CONFIRMADA', fecha_validacion=timezone.now())
        cls.url = reverse('presentation:decisor-resultados')

    def cliente(self, usuario=None):
        c = Client()
        c.force_login(usuario or self.actor)
        return c

    def test_muestra_pm_matriz_y_perfil_sin_recomendacion(self):
        r = self.cliente().get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(r, 'Ponderación Media por factor')
        self.assertContains(r, 'Matriz FODA')
        self.assertContains(r, 'Perfil de cumplimiento')
        self.assertContains(r, '8 de 8 confirmadas')
        self.assertContains(r, 'Recomendación final · pendiente')
        for foda in ('Fortaleza', 'Oportunidad', 'Debilidad', 'Amenaza'):
            self.assertContains(r, f'res-cuadrante--{foda}')
        self.assertContains(r, 'Usabilidad')

    def test_sin_recomendacion_el_paso_siguiente_esta_inactivo(self):
        r = self.cliente().get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(r, 'res-boton--inactivo')

    def test_con_recomendacion_la_muestra_y_habilita_el_informe(self):
        ResultadoEvaluacion.objects.create(evaluacion=self.ev, recomendacion='Adoptar mediante un piloto controlado',
                                           explicacion='Resumen de prueba.', version_regla='v1.4')
        r = self.cliente().get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(r, 'Adoptar mediante un piloto controlado')
        self.assertContains(r, 'Siguiente · Informe')
        self.assertNotContains(r, 'res-boton--inactivo')
        self.assertNotContains(r, 'Explicación de la recomendación')

    def test_el_boton_anterior_lleva_a_la_revision_rapida_y_no_a_la_pantalla_antigua(self):
        r = self.cliente().get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(r, f'evaluacion={self.ev.pk}&amp;etapa=validacion')

    def test_el_banner_muestra_la_escala_a_b_c_con_la_recomendacion_activa(self):
        ResultadoEvaluacion.objects.create(evaluacion=self.ev, recomendacion='Es posible adoptar, con matices',
                                           explicacion='Resumen.', version_regla='1.0')
        r = self.cliente().get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(r, 'Escala de recomendación')
        self.assertContains(r, 'aria-label="Recomendación B"')
        self.assertContains(r, 'class="es-activa"', count=1)
        self.assertContains(r, 'Adoptar el FLOSS seleccionado')
        self.assertContains(r, 'Se sugiere analizar la adopción y debería ser pospuesta')

    def test_sin_evaluacion_indicada_usa_la_mas_reciente_con_pm(self):
        self.assertContains(self.cliente().get(self.url), 'Ponderación Media por factor')

    def test_evaluacion_sin_pm_muestra_estado_vacio(self):
        EvaluacionFactor.objects.filter(evaluacion=self.ev).update(ponderacion_media=None, clasificacion_foda=None)
        self.assertContains(self.cliente().get(self.url), 'Aún no hay resultados')

    def test_otro_decisor_no_ve_la_evaluacion(self):
        self.assertEqual(self.cliente(self.otro).get(self.url, {'evaluacion': self.ev.pk}).status_code, 404)

    def test_confirmadas_texto_resume_los_valores(self):
        r = self.cliente().get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(r, '4 y 3')