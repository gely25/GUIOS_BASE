"""Ficha inicial: sector y tamaño se eligen de una lista en vez de escribirse."""

from django.test import SimpleTestCase

from apps.presentation.forms import SECTORES, TAMANOS, EvaluacionInicialForm


def datos(**extra):
    base = {'nombre_organizacion': 'Instituto QA', 'nombre_software': 'GIMP'}
    base.update(extra)
    return base


class FichaListasDesplegablesTests(SimpleTestCase):

    def test_sector_y_tamano_son_listas_con_opcion_vacia(self):
        form = EvaluacionInicialForm()
        self.assertEqual(form.fields['sector'].choices[0][0], '')
        self.assertEqual(form.fields['tamano'].choices[0][0], '')
        self.assertIn('Educación', [v for v, _ in SECTORES])
        self.assertEqual([v for v, _ in TAMANOS][1:], ['Microempresa', 'Pequeña', 'Mediana', 'Grande'])
        self.assertIn('<select', str(form['tamano']))

    def test_acepta_un_valor_de_la_lista_y_deja_vacio_el_opcional(self):
        form = EvaluacionInicialForm(datos(sector='Educación', tamano='Mediana'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(EvaluacionInicialForm(datos()).is_valid())

    def test_rechaza_un_valor_que_no_esta_en_la_lista(self):
        form = EvaluacionInicialForm(datos(tamano='Gigante'))
        self.assertFalse(form.is_valid())
        self.assertIn('tamano', form.errors)

    def test_conserva_un_valor_anterior_escrito_a_mano(self):
        form = EvaluacionInicialForm(initial={'sector': 'Minería', 'tamano': 'Mediana'})
        valores = [v for v, _ in form.fields['sector'].choices]
        self.assertIn('Minería', valores)
        self.assertEqual(valores.count('Educación'), 1)
