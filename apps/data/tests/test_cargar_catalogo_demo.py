"""Pruebas del comando cargar_catalogo_demo."""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.application.services.indicadores_literatura.fuente_bd import cargar_datos_catalogo_bd
from apps.data.management.commands.cargar_catalogo_demo import (
    CATALOGO_REFERENCIA,
    cargar_catalogo_referencia,
    es_base_de_desarrollo,
)
from apps.data.models.catalogo import Factor, IndicadorFactor


class CargarCatalogoDemoTests(TestCase):
    def test_carga_18_factores_con_61_subfactores_y_ie_3(self):
        self.assertEqual(cargar_catalogo_referencia(), 18)
        datos = cargar_datos_catalogo_bd()
        self.assertEqual(len(datos), 18)
        self.assertEqual(sum(f.ns for f in datos), 61)
        self.assertEqual({f.ie for f in datos}, {3})
        self.assertEqual({f.dimension for f in datos}, {"Tecnológica", "Organizacional", "Económica"})

    def test_alcance_segun_la_tesis(self):
        cargar_catalogo_referencia()
        alcance = {f.nombre: f.alcance for f in Factor.objects.all()}
        self.assertEqual(alcance["Soporte"], "ambos")
        self.assertEqual(alcance["Formación"], "interno")
        self.assertEqual(alcance["Compatibilidad"], "externo")
        self.assertEqual(sum(1 for a in alcance.values() if a == "ambos"), 1)

    def test_es_idempotente(self):
        cargar_catalogo_referencia()
        cargar_catalogo_referencia()
        self.assertEqual(Factor.objects.count(), len(CATALOGO_REFERENCIA))
        self.assertEqual(IndicadorFactor.objects.count(), len(CATALOGO_REFERENCIA))

    def test_nombres_unicos(self):
        nombres = [f[1] for f in CATALOGO_REFERENCIA]
        self.assertEqual(len(nombres), len(set(nombres)))

    def test_solo_bases_de_desarrollo(self):
        self.assertTrue(es_base_de_desarrollo("guios_pro_db_dev"))
        self.assertFalse(es_base_de_desarrollo("guios_pro_db"))
        self.assertFalse(es_base_de_desarrollo("guios_pro_db_prod"))

    def test_comando_se_niega_en_base_que_no_es_dev(self):
        from unittest import mock
        with mock.patch.dict("django.db.connection.settings_dict", {"NAME": "guios_pro_db"}):
            with self.assertRaisesRegex(CommandError, "_dev"):
                call_command("cargar_catalogo_demo")
        self.assertEqual(Factor.objects.count(), 0)

    def test_comando_funciona_en_base_dev(self):
        from unittest import mock
        with mock.patch.dict("django.db.connection.settings_dict", {"NAME": "guios_pro_db_dev"}):
            call_command("cargar_catalogo_demo", stdout=StringIO())
        self.assertEqual(Factor.objects.count(), 18)
