"""El comando `verificar_foda` muestra el caso a mano y detecta resultados guardados incorrectos."""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.data.management.commands.verificar_foda import CASO_A_MANO
from apps.data.models import (CatalogoVersion, Dimension, Evaluacion, EvaluacionFactor, Factor,
                              Organizacion, Software, Subfactor, Usuario, ValoracionSubfactor)


def ejecutar(**opciones):
    salida = StringIO()
    call_command('verificar_foda', stdout=salida, **opciones)
    return salida.getvalue()


class VerificarFodaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        org = Organizacion.objects.create(nombre='Org verificar')
        usuario = Usuario.objects.create_user('verif@test.local', 'Clave-test-123', nombre='D', organizacion=org)
        cat = CatalogoVersion.objects.create(version='verif', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=usuario, catalogo=cat,
                                           software=Software.objects.create(nombre='Soft'))
        dim = Dimension.objects.create(nombre='Tecnológica')
        factor = Factor.objects.create(dimension=dim, nombre='Usabilidad', alcance=Factor.INTERNO)
        cls.ef = EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=factor, importancia_relativa=4,
                                                 ponderacion_media=Decimal('3.67'), clasificacion_foda='Fortaleza')
        for i, valor in enumerate((4, 4, 3)):
            sub = Subfactor.objects.create(factor=factor, descripcion=f'S{i}')
            ValoracionSubfactor.objects.create(evaluacion_factor=cls.ef, subfactor=sub,
                                               valor_confirmado=valor, estado_validacion='CONFIRMADA')

    def test_el_caso_a_mano_coincide_y_se_muestra(self):
        salida = ejecutar()
        self.assertIn('PARTE 1', salida)
        self.assertIn(f'{len(CASO_A_MANO)} de {len(CASO_A_MANO)} correctos', salida)
        self.assertIn('Borde: PM = 3 exacto', salida)
        self.assertIn('todo coincide', salida)

    def test_evaluacion_con_resultados_correctos(self):
        salida = ejecutar(evaluacion=self.ev.pk)
        self.assertIn('PARTE 2', salida)
        self.assertIn('1 de 1 factores correctos', salida)

    def test_detecta_una_pm_guardada_incorrecta(self):
        EvaluacionFactor.objects.filter(pk=self.ef.pk).update(ponderacion_media=Decimal('2.00'))
        with self.assertRaises(CommandError):
            ejecutar(evaluacion=self.ev.pk)

    def test_detecta_una_etiqueta_que_no_sigue_la_regla(self):
        EvaluacionFactor.objects.filter(pk=self.ef.pk).update(clasificacion_foda='Debilidad')
        with self.assertRaises(CommandError):
            ejecutar(evaluacion=self.ev.pk)

    def test_evaluacion_sin_pm_avisa(self):
        EvaluacionFactor.objects.filter(pk=self.ef.pk).update(ponderacion_media=None)
        with self.assertRaises(CommandError):
            ejecutar(evaluacion=self.ev.pk)