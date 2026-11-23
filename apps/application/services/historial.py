"""Servicio de aplicación del historial de evaluaciones (HU15)."""

from dataclasses import dataclass
from typing import Optional

from django.db.models import Exists, OuterRef

from apps.data.models import Evaluacion, EvaluacionFactor, Usuario


@dataclass(frozen=True)
class EvaluacionHistorial:
    evaluacion_id: int
    software: str
    version: Optional[str]
    proveedor: Optional[str]
    organizacion: str
    fecha_inicio: object
    fecha_fin: Optional[object]
    estado: str
    recomendacion: Optional[str]
    tiene_pm_foda: bool

    @property
    def codigo(self) -> str:
        return f"EV-{self.evaluacion_id:03d}"

    @property
    def software_completo(self) -> str:
        return f"{self.software} {self.version}".strip() if self.version else self.software

    @property
    def tiene_recomendacion(self) -> bool:
        return bool((self.recomendacion or "").strip())

    @property
    def pm_foda_calculada(self) -> bool:
        return self.tiene_pm_foda

    @property
    def tiene_pm_foda_calculada(self) -> bool:
        return self.tiene_pm_foda


class HistorialEvaluacionesService:
    """Carga solo el historial que pertenece al decisor autenticado."""

    @staticmethod
    def cargar(usuario):
        if (not getattr(usuario, "is_authenticated", False)
                or getattr(usuario, "rol", None) != Usuario.DECISOR):
            return []

        calculada = EvaluacionFactor.objects.filter(
            evaluacion=OuterRef("pk"),
            relevante=True,
            ponderacion_media__isnull=False,
            clasificacion_foda__isnull=False,
        ).exclude(clasificacion_foda="")

        evaluaciones = (
            Evaluacion.objects.filter(usuario=usuario)
            .select_related("software", "organizacion", "resultado")
            .annotate(tiene_pm_foda=Exists(calculada))
            .order_by("-fecha_inicio", "-evaluacion_id")
        )

        filas = []
        for evaluacion in evaluaciones:
            resultado = getattr(evaluacion, "resultado", None)
            recomendacion = (resultado.recomendacion or "").strip() if resultado else None
            filas.append(EvaluacionHistorial(
                evaluacion_id=evaluacion.pk,
                software=evaluacion.software.nombre,
                version=evaluacion.software.version,
                proveedor=evaluacion.software.proveedor,
                organizacion=evaluacion.organizacion.nombre,
                fecha_inicio=evaluacion.fecha_inicio,
                fecha_fin=evaluacion.fecha_fin,
                estado=evaluacion.get_estado_display(),
                recomendacion=recomendacion or None,
                tiene_pm_foda=bool(evaluacion.tiene_pm_foda),
            ))
        return filas
