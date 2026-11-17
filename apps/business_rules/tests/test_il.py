"""
Pruebas de apps/business_rules/il.py (relación r = TC / NS).

Usan unittest estándar: esta capa no depende de Django.
Las referencias son simuladas mientras HU02 está en desarrollo.
"""

import unittest

from apps.business_rules.il import calcular_relacion_r

# Los 8 subfactores del factor Compatibilidad, tal como aparecen en
# guiosad_data.csv del prototipo original (Guios-Floss).
SUBFACTORES_COMPATIBILIDAD = [
    "Una empresa proporciona una infraestructura de nube lista para usar para este software",
    "Los programas informáticos pueden exportar formatos propietarios",
    "El software interactúa y se integra con el software propietario existente",
    "El software está certificado para operar en su nicho de mercado",
    "El software es compatible con los casos de uso y las funcionalidades más comunes",
    "El software es compatible con múltiples componentes de hardware",
    "El software utiliza formatos estándar",
    "El software es compatible con varios sistemas operativos diferentes (el software es multiplataforma)",
]

# Tres referencias simuladas, cada una vinculada a un subfactor distinto.
REFERENCIAS_SIMULADAS = [
    {"id": "REF-01", "anio": 2020, "subfactor": SUBFACTORES_COMPATIBILIDAD[0]},
    {"id": "REF-02", "anio": 2022, "subfactor": SUBFACTORES_COMPATIBILIDAD[1]},
    {"id": "REF-03", "anio": 2025, "subfactor": SUBFACTORES_COMPATIBILIDAD[2]},
]


class RelacionRTests(unittest.TestCase):

    def test_ejemplo_tres_referencias_da_0_375(self):
        """TC se obtiene contando los registros; NS es el total del catálogo."""
        tc = len(REFERENCIAS_SIMULADAS)
        ns = len(SUBFACTORES_COMPATIBILIDAD)

        # Identificamos cuáles referencias se contaron.
        ids_contados = [ref["id"] for ref in REFERENCIAS_SIMULADAS]
        self.assertEqual(ids_contados, ["REF-01", "REF-02", "REF-03"])

        self.assertEqual(tc, 3)
        self.assertEqual(ns, 8)
        self.assertEqual(calcular_relacion_r(tc, ns), 0.375)

    def test_datos_simulados_son_validos(self):
        """Años dentro de 2020-2025 y un subfactor distinto por referencia."""
        for ref in REFERENCIAS_SIMULADAS:
            self.assertTrue(2020 <= ref["anio"] <= 2025, ref["id"])
            self.assertIn(ref["subfactor"], SUBFACTORES_COMPATIBILIDAD)

        subfactores = [ref["subfactor"] for ref in REFERENCIAS_SIMULADAS]
        self.assertEqual(len(subfactores), len(set(subfactores)))

    def test_sin_referencias_da_cero(self):
        """TC = 0 es válido y el resultado es 0."""
        self.assertEqual(calcular_relacion_r(0, 8), 0.0)

    def test_ns_cero_se_rechaza(self):
        with self.assertRaises(ValueError):
            calcular_relacion_r(3, 0)

    def test_ns_negativo_se_rechaza(self):
        with self.assertRaises(ValueError):
            calcular_relacion_r(3, -8)

    def test_tc_negativo_se_rechaza(self):
        with self.assertRaises(ValueError):
            calcular_relacion_r(-1, 8)

    def test_no_redondea(self):
        """1/3 debe devolverse tal cual, sin redondeo previo."""
        self.assertEqual(calcular_relacion_r(1, 3), 1 / 3)

    def test_rechaza_valores_que_no_son_enteros(self):
        for tc, ns in [(3.5, 8), (3, 8.0), (True, 8), ("3", 8)]:
            with self.subTest(tc=tc, ns=ns):
                with self.assertRaises(TypeError):
                    calcular_relacion_r(tc, ns)