"""
Servicio de Aplicación: BibliographicService.

Capa: application. Coordina la información bibliográfica con los factores del
modelo GUIOS y entrega los indicadores de literatura (HU-03). El cálculo vive
en apps/business_rules; el detalle de datos, en indicadores_literatura/.
"""

from typing import Callable, Optional, Sequence

from apps.application.services.indicadores_literatura import (
    FactorCatalogo,
    IndicadoresLiteratura,
    obtener_indicadores_literatura,
)


class BibliographicService:
    """Punto de entrada de la capa de aplicación para la literatura científica."""

    def indicadores_literatura(
        self,
        fuente: Optional[Callable[[], Sequence[FactorCatalogo]]] = None,
    ) -> IndicadoresLiteratura:
        """TC, r, IL e IS de todos los factores. Sin `fuente`, usa la del catálogo."""
        if fuente is None:
            return obtener_indicadores_literatura()
        return obtener_indicadores_literatura(fuente)
