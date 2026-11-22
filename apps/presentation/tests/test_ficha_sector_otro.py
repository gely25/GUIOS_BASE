"""Ficha inicial: tamaño con rangos y sector «Otro» con texto propio."""

from django.test import SimpleTestCase

from apps.presentation.forms import TAMANOS, EvaluacionInicialForm


def datos(**extra):
    base = {'nombre_organizacion': 'Instituto QA', 'nombre_software': 'GIMP'}
    base.update(extra)
    return base


class FichaSectorOtroYRangosTests(SimpleTestCase):

    def test_tamano_muestra_el_rango_de_personas_y_guarda_el_nombre(self):
        etiquetas = dict(TAMANOS)
        self.assertEqual(etiquetas['Mediana'], 'Mediana · de 50 a 199 personas')
        self.assertIn('200 personas o más', etiquetas['Grande'])
        form = EvaluacionInicialForm(datos(tamano='Mediana'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['tamano'], 'Mediana')

    def test_otro_sector_guarda_el_texto_escrito(self):
        form = EvaluacionInicialForm(datos(sector='Otro', sector_otro='  Minería   artesanal '))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['sector'], 'Minería artesanal')

    def test_otro_sector_sin_texto_pide_escribirlo(self):
        form = EvaluacionInicialForm(datos(sector='Otro', sector_otro='   '))
        self.assertFalse(form.is_valid())
        self.assertIn('sector_otro', form.errors)

    def test_sector_de_la_lista_ignora_el_texto_de_otro(self):
        form = EvaluacionInicialForm(datos(sector='Salud', sector_otro='Minería'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['sector'], 'Salud')