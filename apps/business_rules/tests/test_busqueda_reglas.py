"""Pruebas del glosario, la coincidencia por palabras clave y la identidad de publicaciones (HU02)."""

import unittest
from decimal import Decimal

from apps.business_rules.coincidencia import normalizar, sugerir_factores
from apps.business_rules.glosario_bibliografico import GLOSARIO, construir_consulta, terminos_de
from apps.business_rules.publicaciones import huella_publicacion, normalizar_doi
from apps.business_rules.tests.test_caso_referencia_il_is import NS_POR_FACTOR


class GlosarioTests(unittest.TestCase):

    def test_cada_factor_del_catalogo_2021_tiene_terminos(self):
        self.assertEqual(set(GLOSARIO), set(NS_POR_FACTOR))
        for factor, terminos in GLOSARIO.items():
            self.assertTrue(terminos, factor)

    def test_la_consulta_exige_contexto_floss_adopcion_y_terminos_del_factor(self):
        consulta = construir_consulta('Bloqueo de proveedores')
        self.assertIn('"open source"', consulta)
        self.assertIn('AND adoption AND', consulta)
        self.assertIn('"vendor lock-in"', consulta)

    def test_un_factor_nuevo_usa_su_nombre(self):
        self.assertEqual(terminos_de('Factor nuevo'), ('Factor nuevo',))


class CoincidenciaTests(unittest.TestCase):

    TERMINOS = {
        'usab': ('usability', 'ease of use', 'Usabilidad'),
        'tco': ('total cost of ownership', 'TCO'),
    }

    def test_normaliza_acentos_mayusculas_y_signos(self):
        self.assertEqual(normalizar('  Ease-of-Use, ÁRBOL!'), 'ease of use arbol')

    def test_coincidencia_en_el_titulo_basta(self):
        s = sugerir_factores('Usability of open source ERP', '', self.TERMINOS)
        self.assertEqual([x.clave for x in s], ['usab'])
        self.assertIn('título: usability', s[0].justificacion)

    def test_una_sola_coincidencia_en_el_resumen_no_basta(self):
        self.assertEqual(sugerir_factores('A study', 'We discuss usability.', self.TERMINOS), [])

    def test_no_confunde_palabras_parciales(self):
        self.assertEqual(sugerir_factores('TCOs and stocks', '', {'tco': ('TCO',)}), [])

    def test_pertinencia_de_0_a_100_ordenada(self):
        s = sugerir_factores('Usability and total cost of ownership', 'ease of use, TCO', self.TERMINOS)
        self.assertEqual(len(s), 2)
        self.assertTrue(all(Decimal(0) <= x.pertinencia <= Decimal(100) for x in s))
        self.assertGreaterEqual(s[0].pertinencia, s[1].pertinencia)

    def test_reconoce_el_nombre_en_espanol(self):
        self.assertEqual([x.clave for x in sugerir_factores('Usabilidad del software libre', '', self.TERMINOS)],
                         ['usab'])


class PublicacionesTests(unittest.TestCase):

    def test_normaliza_doi(self):
        self.assertEqual(normalizar_doi('https://doi.org/10.1000/ABC.1'), '10.1000/abc.1')
        self.assertEqual(normalizar_doi('doi: 10.1000/x'), '10.1000/x')
        self.assertIsNone(normalizar_doi('no-es-un-doi'))
        self.assertIsNone(normalizar_doi(None))

    def test_mismo_doi_misma_huella_aunque_cambie_el_titulo(self):
        self.assertEqual(huella_publicacion('https://doi.org/10.1/A', 'Uno', 2021),
                         huella_publicacion('10.1/a', 'Otro', 2022))

    def test_sin_doi_usa_titulo_normalizado_y_anio(self):
        self.assertEqual(huella_publicacion(None, 'Open Source, Adoption!', 2021),
                         huella_publicacion('', 'open source adoption', 2021))
        self.assertNotEqual(huella_publicacion(None, 'Open source adoption', 2021),
                            huella_publicacion(None, 'Open source adoption', 2022))
        self.assertEqual(len(huella_publicacion(None, 'x', None)), 64)

    def test_sin_doi_ni_titulo_falla(self):
        with self.assertRaises(ValueError):
            huella_publicacion(None, '  ', 2021)
