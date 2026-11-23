"""Pruebas de la regla v1.0 de recomendación HU13."""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.application.services.recomendacion import REGLA_VERSION, calcular_recomendacion


class RecomendacionHu13Tests(SimpleTestCase):
    def factor(self, nombre, ir, pm, foda):
        return {'factor': nombre, 'ir': ir, 'pm': pm, 'foda': foda}

    def test_todos_fortalezas_u_oportunidades_da_recomendacion_a(self):
        filas = [
            self.factor('Usabilidad', 4, '3.50', 'Fortaleza'),
            self.factor('Coste', 3, '3.00', 'Oportunidad'),
        ]
        resultado = calcular_recomendacion(filas)
        self.assertEqual(resultado.tipo, 'A')
        self.assertEqual(resultado.version, '1.0')
        self.assertEqual(resultado.conteos, {'F': 1, 'O': 1, 'D': 0, 'A': 0})

    def test_una_debilidad_da_recomendacion_b(self):
        resultado = calcular_recomendacion([
            self.factor('Usabilidad', 4, '3.50', 'Fortaleza'),
            self.factor('Coste', 3, '2.50', 'Debilidad'),
        ])
        self.assertEqual(resultado.tipo, 'B')

    def test_negativas_mayores_que_positivas_da_recomendacion_c(self):
        resultado = calcular_recomendacion([
            self.factor('Usabilidad', 4, '3.50', 'Fortaleza'),
            self.factor('Coste', 3, '2.50', 'Debilidad'),
            self.factor('Soporte', 2, '2.00', 'Amenaza'),
        ])
        self.assertEqual(resultado.tipo, 'C')
        self.assertEqual(len(resultado.factores_criticos), 2)

    def test_empate_negativas_y_positivas_da_recomendacion_b(self):
        resultado = calcular_recomendacion([
            self.factor('Usabilidad', 4, '3.50', 'Fortaleza'),
            self.factor('Coste', 3, '2.50', 'Debilidad'),
        ])
        self.assertEqual(resultado.tipo, 'B')

    def test_ir_uno_no_participa(self):
        resultado = calcular_recomendacion([
            self.factor('Usabilidad', 4, '3.50', 'Fortaleza'),
            self.factor('Excluido', 1, '1.00', 'Amenaza'),
        ])
        self.assertEqual(resultado.tipo, 'A')

    def test_sin_factores_participantes_lanza_error_claro(self):
        with self.assertRaises(ValidationError):
            calcular_recomendacion([
                self.factor('Excluido', 1, '1.00', 'Amenaza'),
                self.factor('Sin FODA', 3, '3.00', None),
            ])

    def test_resultado_es_determinista(self):
        filas = [
            self.factor('Soporte', 2, '2.25', 'Amenaza'),
            self.factor('Usabilidad', 4, '3.50', 'Fortaleza'),
        ]
        primero = calcular_recomendacion(filas)
        segundo = calcular_recomendacion(filas)
        self.assertEqual(
            (primero.tipo, primero.texto, primero.conteos, primero.factores_criticos,
             primero.explicacion, primero.version),
            (segundo.tipo, segundo.texto, segundo.conteos, segundo.factores_criticos,
             segundo.explicacion, segundo.version),
        )
        self.assertEqual(REGLA_VERSION, '1.0')
