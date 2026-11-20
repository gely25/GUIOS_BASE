"""
Servicio de Aplicación: BibliographicService.

Capa: application. Coordina la información bibliográfica con los factores del
modelo GUIOS y entrega los indicadores de literatura (HU-03). El cálculo vive
en apps/business_rules; el detalle de datos, en indicadores_literatura/ y la
búsqueda de literatura (HU-02), en actualizacion_bibliografica/.
"""

from typing import Callable, Optional, Sequence

from apps.application.services.actualizacion_bibliografica import (
    ActualizacionBibliografica,
    ResultadoActualizacion,
)
from apps.application.services.indicadores_literatura import (
    FactorCatalogo,
    IndicadoresLiteratura,
    obtener_indicadores_literatura,
)
from apps.application.services.indicadores_literatura.fuente_bd import cargar_datos_catalogo_bd


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

    def indicadores_literatura_actualizados(
        self, anio_inicio: int = 2020, anio_fin: int = 2025,
    ) -> IndicadoresLiteratura:
        """Igual que `indicadores_literatura`, pero con datos reales de PostgreSQL (no simulados)."""
        return obtener_indicadores_literatura(lambda: cargar_datos_catalogo_bd(anio_inicio, anio_fin))

    def actualizar_literatura(
        self,
        buscador=None,
        anio_inicio: int = 2020,
        anio_fin: int = 2025,
        limite: int = 50,
    ) -> ResultadoActualizacion:
        """HU02: busca literatura de todos los factores activos y guarda las publicaciones."""
        return ActualizacionBibliografica(self._buscador(buscador)).actualizar(anio_inicio, anio_fin, limite)

    def totales_por_factor(self, buscador=None, anio_inicio: int = 2020, anio_fin: int = 2025):
        """HU02: cuántas publicaciones hay por factor en la fuente. Solo consulta, no guarda nada."""
        return ActualizacionBibliografica(self._buscador(buscador)).totales_por_factor(anio_inicio, anio_fin)

    @staticmethod
    def _buscador(buscador):
        if buscador is not None:
            return buscador
        from apps.external_services.openalex import OpenAlexClient
        return OpenAlexClient()
