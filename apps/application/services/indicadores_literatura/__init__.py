"""
Indicadores de literatura (HU-03): API pública del paquete.

Capa: application. Los demás módulos (modelos, fuente_simulada, servicio) son
detalles internos; quien use el servicio debe importar desde aquí.
"""

from .modelos import FactorCatalogo, FilaIndicadores, IndicadoresLiteratura
from .servicio import calcular_indicadores_literatura, obtener_indicadores_literatura

__all__ = [
    "obtener_indicadores_literatura",
    "calcular_indicadores_literatura",
    "FactorCatalogo",
    "FilaIndicadores",
    "IndicadoresLiteratura",
]
