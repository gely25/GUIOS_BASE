"""
Servicio de Aplicación: BibliographicService.

Capa: application. Punto de entrada de la literatura científica:
- HU02: búsqueda 2020-2025, revisión de vínculos publicación-factor, recálculo de
  TC/IL/IS y publicación de una nueva versión del catálogo (actualizacion_bibliografica/).
- HU03: indicadores de literatura de la versión activa (indicadores_literatura/).

Los cálculos viven en apps/business_rules; las consultas, en apps/data/repositorios.
"""

from typing import Callable, Optional, Sequence

from apps.application.services.actualizacion_bibliografica import busquedas, revision, sugerencias_ia, versiones
from apps.application.services.indicadores_literatura import (
    FactorCatalogo,
    IndicadoresLiteratura,
    obtener_indicadores_literatura,
)
from apps.data.repositorios import bibliografia as repo
from apps.data.repositorios import catalogo as repo_catalogo


class BibliographicService:
    """Punto de entrada de la capa de aplicación para la literatura científica."""

    # --- HU03 -----------------------------------------------------------------
    def indicadores_literatura(
        self,
        fuente: Optional[Callable[[], Sequence[FactorCatalogo]]] = None,
    ) -> Optional[IndicadoresLiteratura]:
        """TC, r, IL e IS de todos los factores. Sin `fuente`, usa la versión activa del catálogo."""
        return obtener_indicadores_literatura(fuente)

    # --- HU02: búsquedas --------------------------------------------------------
    @staticmethod
    def lanzar_actualizacion(actor_id, factor_ids=None):
        return busquedas.lanzar_actualizacion(actor_id, factor_ids)

    @staticmethod
    def procesar_pendientes(limite=None, fuente=None):
        return busquedas.procesar_pendientes(limite=limite, fuente=fuente)

    @staticmethod
    def estado_lote(lote=None):
        return busquedas.estado_lote(lote)

    @staticmethod
    def busquedas_recientes(limite=50):
        return repo.busquedas_recientes(limite)

    @staticmethod
    def busquedas_paginables():
        """QuerySet de todas las búsquedas, para paginar en la vista."""
        return repo.busquedas_paginables()

    @staticmethod
    def detalle_busqueda(busqueda_id):
        """(búsqueda, resultados con sus vínculos, factores activos para vincular a mano)."""
        busqueda = repo.obtener_busqueda(busqueda_id)
        factores = repo_catalogo.factores_de(repo_catalogo.version_activa())
        return busqueda, repo.resultados_de(busqueda), factores

    @staticmethod
    def sugerir_publicaciones_ia(actor_id, busqueda_id, proveedor):
        return sugerencias_ia.sugerir_publicaciones(actor_id, busqueda_id, proveedor)

    @staticmethod
    def resumen_vinculos():
        return repo.conteo_vinculos()

    # --- HU02: revisión ---------------------------------------------------------
    @staticmethod
    def revisar_vinculo(actor_id, busqueda_id, vinculo_id, aprobar):
        return revision.revisar(actor_id, busqueda_id, vinculo_id, aprobar)

    @staticmethod
    def vincular_manual(actor_id, busqueda_id, publicacion_id, factor_id, justificacion=''):
        return revision.vincular_manual(actor_id, busqueda_id, publicacion_id, factor_id, justificacion)

    # --- HU02: versiones del catálogo -------------------------------------------
    @staticmethod
    def crear_borrador(actor_id):
        return versiones.crear_borrador(actor_id)

    @staticmethod
    def publicar_borrador(actor_id):
        return versiones.publicar(actor_id)

    @staticmethod
    def descartar_borrador(actor_id):
        return versiones.descartar(actor_id)

    @staticmethod
    def comparacion_versiones():
        return versiones.comparacion()
