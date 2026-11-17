"""
Pruebas de cuartiles e IL (apps/business_rules/il.py).

Usan unittest estándar: esta capa no depende de Django.
"""

import random
import statistics
import unittest
from fractions import Fraction

from apps.business_rules.il import (
    Cuartiles,
    asignar_il,
    calcular_cuartiles,
    calcular_il_factores,
)

# Límites de la Tabla 5.3 de la tesis (valores publicados, con decimales
# truncados): rq1 = 1.864, rq2 = 3.65, rq3 = 4.781, rq4 = 12.
LIMITES_TESIS = Cuartiles(
    rq1=Fraction("1.864"),
    rq2=Fraction("3.65"),
    rq3=Fraction("4.781"),
    rq4=Fraction(12),
)


class CalcularCuartilesTests(unittest.TestCase):

    def test_coincide_con_percentil_inclusivo_de_la_biblioteca_estandar(self):
        """Mismo método que QUARTILE.INC de Excel y numpy por defecto."""
        generador = random.Random(2026)
        for n in (2, 3, 5, 8, 18, 25):
            datos = [Fraction(generador.randint(0, 40), generador.randint(1, 11)) for _ in range(n)]
            esperado = statistics.quantiles([float(d) for d in datos], n=4, method="inclusive")

            obtenido = calcular_cuartiles(datos)

            with self.subTest(n=n):
                self.assertAlmostEqual(float(obtenido.rq1), esperado[0], places=9)
                self.assertAlmostEqual(float(obtenido.rq2), esperado[1], places=9)
                self.assertAlmostEqual(float(obtenido.rq3), esperado[2], places=9)
                self.assertEqual(obtenido.rq4, max(datos))

    def test_ejemplo_pequeno_a_mano(self):
        """1, 2, 3, 4, 5: percentiles 25/50/75 caen en posiciones exactas."""
        cuartiles = calcular_cuartiles([5, 1, 3, 2, 4])  # desordenados a propósito
        self.assertEqual(cuartiles, Cuartiles(2, 3, 4, 5))

    def test_interpola_entre_valores_vecinos(self):
        """Con 4 valores, el percentil 25 cae en la posición 0.75."""
        cuartiles = calcular_cuartiles([0, 4, 8, 12])
        self.assertEqual(cuartiles.rq1, Fraction(3))
        self.assertEqual(cuartiles.rq2, Fraction(6))
        self.assertEqual(cuartiles.rq3, Fraction(9))
        self.assertEqual(cuartiles.rq4, Fraction(12))

    def test_resultado_exacto_sin_redondeo(self):
        """Devuelve fracciones exactas: 1/3 no se convierte en 0.333...."""
        cuartiles = calcular_cuartiles([Fraction(1, 3), Fraction(1, 3), Fraction(2, 3), Fraction(1)])
        self.assertEqual(cuartiles.rq1, Fraction(1, 3))
        self.assertEqual(cuartiles.rq4, Fraction(1))

    def test_rechaza_menos_de_dos_valores(self):
        for datos in ([], [1]):
            with self.subTest(datos=datos):
                with self.assertRaises(ValueError):
                    calcular_cuartiles(datos)

    def test_rechaza_valores_negativos(self):
        with self.assertRaises(ValueError):
            calcular_cuartiles([1, -2, 3])

    def test_rechaza_valores_que_no_son_numeros(self):
        for malo in ("3", None, True):
            with self.subTest(malo=malo):
                with self.assertRaises(TypeError):
                    calcular_cuartiles([1, malo, 3])


class AsignarILTests(unittest.TestCase):

    def test_casos_de_verificacion_de_la_tesis(self):
        """
        Mantenibilidad (r = 4) cae entre rq2 y rq3 -> IL 3.
        Apoyo de la alta dirección (r = 5) supera rq3 -> IL 4.
        """
        self.assertEqual(asignar_il(4, LIMITES_TESIS), 3)
        self.assertEqual(asignar_il(5, LIMITES_TESIS), 4)

    def test_cada_tramo(self):
        self.assertEqual(asignar_il(0, LIMITES_TESIS), 1)
        self.assertEqual(asignar_il(1, LIMITES_TESIS), 1)
        self.assertEqual(asignar_il(2, LIMITES_TESIS), 2)
        self.assertEqual(asignar_il(3, LIMITES_TESIS), 2)
        self.assertEqual(asignar_il(4, LIMITES_TESIS), 3)
        self.assertEqual(asignar_il(5, LIMITES_TESIS), 4)
        self.assertEqual(asignar_il(12, LIMITES_TESIS), 4)

    def test_un_valor_igual_al_limite_queda_en_el_tramo_inferior(self):
        """Cortes inclusivos por arriba: r == rq cae en el grupo de abajo."""
        self.assertEqual(asignar_il(LIMITES_TESIS.rq1, LIMITES_TESIS), 1)
        self.assertEqual(asignar_il(LIMITES_TESIS.rq2, LIMITES_TESIS), 2)
        self.assertEqual(asignar_il(LIMITES_TESIS.rq3, LIMITES_TESIS), 3)
        self.assertEqual(asignar_il(LIMITES_TESIS.rq4, LIMITES_TESIS), 4)

    def test_justo_encima_de_un_limite_sube_de_tramo(self):
        minimo = Fraction(1, 10**6)
        self.assertEqual(asignar_il(LIMITES_TESIS.rq1 + minimo, LIMITES_TESIS), 2)
        self.assertEqual(asignar_il(LIMITES_TESIS.rq2 + minimo, LIMITES_TESIS), 3)
        self.assertEqual(asignar_il(LIMITES_TESIS.rq3 + minimo, LIMITES_TESIS), 4)

    def test_r_mayor_que_rq4_se_rechaza(self):
        with self.assertRaises(ValueError):
            asignar_il(Fraction("12.0001"), LIMITES_TESIS)

    def test_r_negativo_o_no_numerico_se_rechaza(self):
        with self.assertRaises(ValueError):
            asignar_il(-1, LIMITES_TESIS)
        with self.assertRaises(TypeError):
            asignar_il("3", LIMITES_TESIS)


class CalcularILFactoresTests(unittest.TestCase):

    def test_ejemplo_completo(self):
        """
        Cuatro factores con r = 0, 1, 2 y 4:
        cuartiles 0.75 / 1.5 / 2.5 / 4 -> IL 1, 2, 3 y 4.
        """
        factores = {"A": (0, 5), "B": (4, 4), "C": (6, 3), "D": (16, 4)}

        cuartiles, resultados = calcular_il_factores(factores)

        self.assertEqual(cuartiles, Cuartiles(Fraction(3, 4), Fraction(3, 2), Fraction(5, 2), Fraction(4)))
        self.assertEqual({n: r.il for n, r in resultados.items()}, {"A": 1, "B": 2, "C": 3, "D": 4})

    def test_conserva_tc_ns_y_r_para_explicar_el_calculo(self):
        _, resultados = calcular_il_factores({"A": (3, 8), "B": (1, 1)})
        self.assertEqual(resultados["A"].tc, 3)
        self.assertEqual(resultados["A"].ns, 8)
        self.assertEqual(resultados["A"].r, Fraction(3, 8))

    def test_el_factor_sin_referencias_recibe_il_1(self):
        _, resultados = calcular_il_factores({"A": (0, 5), "B": (3, 3), "C": (9, 3)})
        self.assertEqual(resultados["A"].il, 1)

    def test_empate_exacto_con_un_limite_no_depende_de_decimales(self):
        """
        r = 1/3 se compara como fracción exacta: nunca queda mal clasificado
        por el error de 0.333... en punto flotante.
        """
        factores = {"A": (1, 3), "B": (1, 3), "C": (2, 3), "D": (1, 1)}
        _, resultados = calcular_il_factores(factores)
        self.assertEqual(resultados["A"].il, 1)
        self.assertEqual(resultados["B"].il, 1)

    def test_rechaza_datos_invalidos(self):
        with self.assertRaises(ValueError):
            calcular_il_factores({"A": (3, 8)})  # un solo factor
        with self.assertRaises(ValueError):
            calcular_il_factores({"A": (3, 0), "B": (1, 1)})  # NS = 0
        with self.assertRaises(ValueError):
            calcular_il_factores({"A": (-1, 8), "B": (1, 1)})  # TC negativo
        with self.assertRaises(TypeError):
            calcular_il_factores({"A": (3.5, 8), "B": (1, 1)})  # TC no entero
