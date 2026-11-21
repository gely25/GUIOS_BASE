"""Pruebas de `manage.py cargar_catalogo_guios` (catálogo GUIOS 2021)."""

from django.core.management import call_command
from django.test import TestCase

from apps.business_rules.tests.test_caso_referencia_il_is import CASO_REFERENCIA_IL_IS, NS_POR_FACTOR
from apps.data.models import CatalogoVersion, Dimension, Factor, IndicadorFactor, Subfactor


class CargarCatalogoTests(TestCase):

    def setUp(self):
        call_command('cargar_catalogo_guios', verbosity=0)

    def test_carga_3_dimensiones_18_factores_y_61_subfactores(self):
        self.assertEqual(Dimension.objects.count(), 3)
        self.assertEqual(Factor.objects.count(), 18)
        self.assertEqual(Subfactor.objects.count(), 61)
        for nombre, ns in NS_POR_FACTOR.items():
            self.assertEqual(Subfactor.objects.filter(factor__nombre=nombre).count(), ns, nombre)

    def test_crea_la_version_inicial_activa(self):
        version = CatalogoVersion.objects.get()
        self.assertEqual((version.version, version.estado), ('v1-2021', CatalogoVersion.ACTIVO))

    def test_reproduce_tc_il_e_is_del_caso_de_referencia(self):
        for factor, tc, il, is_ in CASO_REFERENCIA_IL_IS:
            with self.subTest(factor=factor):
                i = IndicadorFactor.objects.get(factor__nombre=factor)
                self.assertEqual((i.total_citas_base, i.total_citas), (tc, tc))
                self.assertEqual(i.numero_subfactores, NS_POR_FACTOR[factor])
                self.assertEqual((i.importancia_experto, i.importancia_literatura, i.importancia_sugerida),
                                 (3, il, is_))

    def test_la_is_sale_de_las_reglas_y_no_del_csv(self):
        # factors.csv decía Usabilidad 3 y Apoyo de la alta dirección 2; el caso de referencia dice 2 y 3.
        self.assertEqual(IndicadorFactor.objects.get(factor__nombre='Usabilidad').importancia_sugerida, 2)
        self.assertEqual(
            IndicadorFactor.objects.get(factor__nombre='Apoyo de la alta dirección').importancia_sugerida, 3)

    def test_alcance_y_erratas_corregidas(self):
        self.assertEqual(Factor.objects.get(nombre='Soporte').alcance, Factor.AMBOS)
        self.assertFalse(Subfactor.objects.filter(descripcion__contains='códigofuente').exists())
        self.assertFalse(Subfactor.objects.filter(descripcion__contains='una sistemas').exists())

    def test_es_repetible(self):
        call_command('cargar_catalogo_guios', verbosity=0)
        self.assertEqual(Factor.objects.count(), 18)
        self.assertEqual(Subfactor.objects.count(), 61)
        self.assertEqual(IndicadorFactor.objects.count(), 18)
        self.assertEqual(CatalogoVersion.objects.count(), 1)
