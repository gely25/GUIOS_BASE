"""
Estructuras del informe de una evaluación (HU14).

Son datos ya calculados: el informe NO recalcula IS, IR, PM ni FODA, solo los presenta
tal como quedaron guardados. La explicación redactada no modifica ningún valor.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

FORTALEZA = "Fortaleza"
OPORTUNIDAD = "Oportunidad"
DEBILIDAD = "Debilidad"
AMENAZA = "Amenaza"
CLASES_FODA = (FORTALEZA, OPORTUNIDAD, DEBILIDAD, AMENAZA)

ALCANCES = {"interno": "Interno", "externo": "Externo", "ambos": "Interno o externo"}


class InformeNoDisponible(Exception):
    """La evaluación no existe, no es del usuario o todavía no tiene resultado."""


@dataclass(frozen=True)
class EvidenciaInforme:
    documento: str
    pagina: Optional[int]
    seccion: Optional[str]
    hoja: Optional[str]
    fragmento: str
    relevancia: Optional[Decimal] = None
    justificacion: Optional[str] = None

    @property
    def ubicacion(self) -> str:
        """Dónde está dentro del documento (página, sección u hoja)."""
        partes = []
        if self.pagina is not None:
            partes.append(f"p. {self.pagina}")
        if self.seccion:
            partes.append(f"sección {self.seccion}")
        if self.hoja:
            partes.append(f"hoja {self.hoja}")
        return ", ".join(partes)


@dataclass
class ValoracionInforme:
    subfactor: str
    valor_ia: Optional[int]
    valor_confirmado: Optional[int]
    estado_validacion: str
    justificacion_ia: Optional[str] = None
    justificacion_decisor: Optional[str] = None
    evidencias: List[EvidenciaInforme] = field(default_factory=list)

    @property
    def justificacion(self) -> str:
        """La del decisor si la escribió; si no, la propuesta por la IA."""
        return (self.justificacion_decisor or self.justificacion_ia or "").strip()


@dataclass
class FactorInforme:
    dimension: str
    factor: str
    alcance: str
    importancia_sugerida: Optional[int]      # IS
    importancia_decisor: Optional[int]       # ID
    importancia_relativa: Optional[int]      # IR
    ponderacion_media: Optional[Decimal]     # PM
    clasificacion_foda: Optional[str]
    valoraciones: List[ValoracionInforme] = field(default_factory=list)

    @property
    def alcance_texto(self) -> str:
        return ALCANCES.get(self.alcance, self.alcance)

    @property
    def total_evidencias(self) -> int:
        return sum(len(v.evidencias) for v in self.valoraciones)


@dataclass(frozen=True)
class DocumentoInforme:
    nombre: str
    tipo: str
    version: Optional[str]
    hash_sha256: Optional[str]
    fecha_carga: datetime


@dataclass(frozen=True)
class ResumenFoda:
    fortalezas: int = 0
    oportunidades: int = 0
    debilidades: int = 0
    amenazas: int = 0
    sin_clasificar: int = 0

    @property
    def filas(self):
        """(nombre, cantidad) en el orden de la metodología."""
        return (
            (FORTALEZA, self.fortalezas),
            (OPORTUNIDAD, self.oportunidades),
            (DEBILIDAD, self.debilidades),
            (AMENAZA, self.amenazas),
        )

    @property
    def filas_plural(self):
        """(nombre en plural, cantidad) para mostrar en tarjetas."""
        return (
            ("Fortalezas", self.fortalezas),
            ("Oportunidades", self.oportunidades),
            ("Debilidades", self.debilidades),
            ("Amenazas", self.amenazas),
        )


@dataclass
class InformeEvaluacion:
    evaluacion_id: int
    software: str
    software_version: Optional[str]
    proveedor: Optional[str]
    organizacion: str
    decisor: str
    catalogo_version: str
    estado: str
    fecha_inicio: datetime
    fecha_fin: Optional[datetime]
    recomendacion: str
    explicacion: Optional[str]
    version_regla: str
    fecha_resultado: datetime
    resumen_foda: ResumenFoda = field(default_factory=ResumenFoda)
    factores: List[FactorInforme] = field(default_factory=list)
    documentos: List[DocumentoInforme] = field(default_factory=list)

    @property
    def software_completo(self) -> str:
        return f"{self.software} {self.software_version}".strip() if self.software_version else self.software

    @property
    def total_valoraciones(self) -> int:
        return sum(len(f.valoraciones) for f in self.factores)

    @property
    def total_evidencias(self) -> int:
        return sum(f.total_evidencias for f in self.factores)
