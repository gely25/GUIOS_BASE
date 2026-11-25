"""Pruebas de la regla híbrida v2.0 de recomendación HU13 (FODA + IR + conteo)."""

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
        self.assertEqual(resultado.version, '2.0')
        self.assertEqual(resultado.conteos, {'F': 1, 'O': 1, 'D': 0, 'A': 0})

    def test_debilidad_en_factor_opcional_da_recomendacion_b(self):
        resultado = calcular_recomendacion([
            self.factor('Usabilidad', 4, '3.50', 'Fortaleza'),
            self.factor('Reusabilidad', 2, '2.50', 'Debilidad'),
        ])
        self.assertEqual(resultado.tipo, 'B')
        self.assertIn('solo en factores opcionales', resultado.explicacion)

    def test_varias_negativas_opcionales_sin_superar_positivas_da_b(self):
        resultado = calcular_recomendacion([
            self.factor('Compatibilidad', 4, '3.80', 'Oportunidad'),
            self.factor('Prueba', 3, '3.00', 'Oportunidad'),
            self.factor('Reusabilidad', 2, '2.00', 'Amenaza'),
            self.factor('Tiempo de adopción', 2, '2.50', 'Debilidad'),
        ])
        self.assertEqual(resultado.tipo, 'B')

    def test_una_debilidad_importante_da_c_aunque_haya_mas_positivas(self):
        resultado = calcular_recomendacion([
            self.factor('Compatibilidad', 4, '3.80', 'Oportunidad'),
            self.factor('Prueba', 3, '3.00', 'Oportunidad'),
            self.factor('Fiabilidad', 3, '3.20', 'Oportunidad'),
            self.factor('Formación', 3, '2.80', 'Debilidad'),
        ])
        self.assertEqual(resultado.tipo, 'C')
        self.assertIn('Formación', resultado.explicacion)

    def test_una_amenaza_fundamental_da_c(self):
        resultado = calcular_recomendacion([
            self.factor('Usabilidad', 3, '3.50', 'Oportunidad'),
            self.factor('Soporte', 4, '2.30', 'Amenaza'),
        ])
        self.assertEqual(resultado.tipo, 'C')

    def test_negativas_opcionales_que_superan_a_positivas_da_c(self):
        resultado = calcular_recomendacion([
            self.factor('Usabilidad', 3, '3.50', 'Oportunidad'),
            self.factor('Reusabilidad', 2, '2.00', 'Amenaza'),
            self.factor('Tiempo de adopción', 2, '2.50', 'Debilidad'),
        ])
        self.assertEqual(resultado.tipo, 'C')
        self.assertEqual(len(resultado.factores_criticos), 2)

    def test_empate_con_negativas_opcionales_da_b(self):
        resultado = calcular_recomendacion([
            self.factor('Usabilidad', 4, '3.50', 'Fortaleza'),
            self.factor('Reusabilidad', 2, '2.50', 'Debilidad'),
        ])
        self.assertEqual(resultado.tipo, 'B')

    def test_caso_libreoffice_de_la_tesis_da_c(self):
        # Tesis, Figuras 6.3 (IR) y 6.5 (PM y FODA): 11 factores a favor y 7 en contra,
        # con Personalización, Formación y Soporte en contra e IR Importante -> Recomendación C.
        filas = [
            self.factor('Compatibilidad', 3, '3.8', 'Oportunidad'),
            self.factor('Personalización', 3, '1.7', 'Amenaza'),
            self.factor('Prueba', 3, '3.0', 'Oportunidad'),
            self.factor('Fiabilidad', 3, '3.2', 'Oportunidad'),
            self.factor('Reusabilidad', 2, '3.0', 'Oportunidad'),
            self.factor('Usabilidad', 2, '3.5', 'Oportunidad'),
            self.factor('Mantenibilidad', 3, '4.0', 'Oportunidad'),
            self.factor('Portabilidad', 2, '2.0', 'Amenaza'),
            self.factor('Documentación', 2, '2.4', 'Amenaza'),
            self.factor('Formación', 3, '2.8', 'Debilidad'),
            self.factor('Tiempo de adopción', 2, '3.5', 'Fortaleza'),
            self.factor('Casos de estudio de adopción FLOSS', 2, '3.0', 'Oportunidad'),
            self.factor('Centralidad de la tecnología de la información', 2, '2.5', 'Debilidad'),
            self.factor('Apoyo de la alta dirección', 3, '4.0', 'Fortaleza'),
            self.factor('Bloqueo de proveedores', 2, '2.0', 'Amenaza'),
            self.factor('Soporte', 3, '2.3', 'Debilidad'),
            self.factor('Actitud hacia el cambio', 2, '3.0', 'Fortaleza'),
            self.factor('Coste total de propiedad', 3, '3.5', 'Fortaleza'),
        ]
        resultado = calcular_recomendacion(filas)
        self.assertEqual(resultado.conteos, {'F': 4, 'O': 7, 'D': 3, 'A': 4})
        self.assertEqual(resultado.tipo, 'C')

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
        self.assertEqual(REGLA_VERSION, '2.0')
