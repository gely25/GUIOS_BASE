"""Pruebas de la fuente de datos real del catálogo (HU-03 con datos de HU02)."""

from datetime import date

from django.test import TestCase

from apps.application.services.indicadores_literatura.fuente_bd import cargar_datos_catalogo_bd
from apps.data.models.bibliografia import Publicacion, PublicacionFactor
from apps.data.models.catalogo import CatalogoVersion, Dimension, Factor, IndicadorFactor


class FuenteBdTests(TestCase):
    def setUp(self):
        self.dim = Dimension.objects.create(nombre="Tecnológica")
        self.version = CatalogoVersion.objects.create(version="2021", fecha_creacion=date(2021, 1, 1))
        self.compat = self._factor("Compatibilidad", ns=8, ie=3, citas=33)
        self.fiab = self._factor("Fiabilidad", ns=5, ie=3, citas=19)

    def _factor(self, nombre, ns, ie, citas, version=None):
        f = Factor.objects.create(dimension=self.dim, nombre=nombre, alcance="interno")
        IndicadorFactor.objects.create(
            catalogo=version or self.version, factor=f,
            numero_subfactores=ns, importancia_experto=ie, total_citas=citas)
        return f

    def _relacionar(self, factor, n, anio=2023, prefijo="a"):
        for i in range(n):
            p = Publicacion.objects.create(titulo="t", anio=anio, doi=f"10.1/{prefijo}{factor.factor_id}-{i}")
            PublicacionFactor.objects.create(publicacion=p, factor=factor)

    def test_sin_publicaciones_usa_el_tc_del_catalogo(self):
        datos = {f.nombre: f for f in cargar_datos_catalogo_bd()}
        self.assertEqual((datos["Compatibilidad"].tc, datos["Compatibilidad"].ns, datos["Compatibilidad"].ie), (33, 8, 3))
        self.assertEqual(datos["Fiabilidad"].tc, 19)
        self.assertEqual(datos["Fiabilidad"].dimension, "Tecnológica")

    def test_con_publicaciones_el_tc_sale_de_ellas_para_todos_los_factores(self):
        self._relacionar(self.compat, 4)
        datos = {f.nombre: f for f in cargar_datos_catalogo_bd()}
        self.assertEqual(datos["Compatibilidad"].tc, 4)
        self.assertEqual(datos["Fiabilidad"].tc, 0)  # no se mezcla con el TC viejo (19)

    def test_publicaciones_fuera_del_periodo_no_cuentan(self):
        self._relacionar(self.compat, 3, anio=2018)
        datos = {f.nombre: f for f in cargar_datos_catalogo_bd(2020, 2025)}
        self.assertEqual(datos["Compatibilidad"].tc, 33)  # sigue usando el catálogo

    def test_usa_solo_la_version_activa(self):
        vieja = CatalogoVersion.objects.create(version="2019", fecha_creacion=date(2019, 1, 1), estado="INACTIVO")
        self._factor("Usabilidad", ns=4, ie=3, citas=14, version=vieja)
        nombres = [f.nombre for f in cargar_datos_catalogo_bd()]
        self.assertNotIn("Usabilidad", nombres)

    def test_factor_inactivo_se_omite(self):
        self.fiab.activo = False
        self.fiab.save()
        self.assertEqual([f.nombre for f in cargar_datos_catalogo_bd()], ["Compatibilidad"])

    def test_sin_version_activa_falla_con_mensaje(self):
        CatalogoVersion.objects.update(estado="INACTIVO")
        with self.assertRaisesRegex(ValueError, "versión activa"):
            cargar_datos_catalogo_bd()

    def test_version_sin_indicadores_falla(self):
        IndicadorFactor.objects.all().delete()
        with self.assertRaisesRegex(ValueError, "no tiene indicadores"):
            cargar_datos_catalogo_bd()

    def test_factor_sin_ie_falla_nombrando_el_factor(self):
        IndicadorFactor.objects.filter(factor=self.fiab).update(importancia_experto=None)
        with self.assertRaisesRegex(ValueError, "Fiabilidad"):
            cargar_datos_catalogo_bd()
