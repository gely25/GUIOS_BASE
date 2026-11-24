"""
Servicio de Aplicación: ReportService.

Capa: application. Resultados finales e informe PDF con fuentes, evidencias y justificaciones (HU14).
Los detalles (datos, modelo del informe y PDF) están en el subpaquete `informe/`.
"""

from typing import Optional

from django.utils import timezone
from django.utils.text import slugify

from apps.application.services.informe import (
    DocumentoVista,
    InformeEvaluacion,
    InformeNoDisponible,
    cargar_informe,
    construir_documento,
    generar_pdf,
)

__all__ = ["ReportService", "InformeNoDisponible"]


class ReportService:
    """Resultados finales e informe PDF con fuentes, evidencias y justificaciones (HU14)."""

    def informe(self, usuario, evaluacion_id: Optional[int] = None) -> InformeEvaluacion:
        """
        Informe de una evaluación del usuario (la más reciente con resultado si no se indica).
        Lanza InformeNoDisponible si no existe, no es suya o aún no tiene resultado.
        """
        return cargar_informe(usuario, evaluacion_id)

    def documento(self, informe: InformeEvaluacion, emitido=None) -> DocumentoVista:
        """Contenido del informe ya ordenado: lo usan la pantalla y el PDF, para que digan lo mismo."""
        return construir_documento(informe, emitido or timezone.now())

    def generar_pdf(self, informe: InformeEvaluacion) -> bytes:
        """Bytes del informe PDF."""
        return generar_pdf(informe)

    @staticmethod
    def nombre_archivo(informe: InformeEvaluacion) -> str:
        software = slugify(informe.software) or "evaluacion"
        return f"informe-guios-{software}-{informe.evaluacion_id}.pdf"
