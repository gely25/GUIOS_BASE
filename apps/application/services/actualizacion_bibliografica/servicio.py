"""
Servicio de actualización bibliográfica (HU02).

Capa: application. Para cada factor activo del catálogo consulta la fuente
bibliográfica (OpenAlex), guarda la búsqueda, las publicaciones y su relación
con el factor, y permite obtener el TC actualizado.

TC (Total de Citas/Referencias) = número de publicaciones distintas, del
periodo analizado, relacionadas con el factor (así se usa en la tesis GUIOS).
Este servicio NO calcula r, IL ni IS: eso vive en apps/business_rules y lo
orquesta indicadores_literatura.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Sequence

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.data.models.bibliografia import (
    BusquedaBibliografica,
    BusquedaPublicacion,
    Publicacion,
    PublicacionFactor,
)
from apps.data.models.catalogo import Factor
from apps.external_services.openalex import OpenAlexError

from .consultas import construir_consulta

ANIO_INICIO_POR_DEFECTO = 2020
ANIO_FIN_POR_DEFECTO = 2025
LIMITE_POR_DEFECTO = 50

EN_PROCESO = "EN_PROCESO"
COMPLETADA = "COMPLETADA"
SIN_RESULTADOS = "SIN_RESULTADOS"
ERROR = "ERROR"


class Buscador(Protocol):
    """Lo que el servicio necesita de la fuente (OpenAlexClient lo cumple)."""

    def buscar(self, texto: str, anio_inicio: int, anio_fin: int, limite: int) -> Sequence:
        ...


@dataclass
class ResultadoFactor:
    factor_id: int
    factor: str
    consulta: str
    estado: str
    encontradas: int = 0
    nuevas: int = 0
    error: Optional[str] = None


@dataclass
class ResultadoActualizacion:
    anio_inicio: int
    anio_fin: int
    factores: List[ResultadoFactor] = field(default_factory=list)
    tc_por_factor: Dict[int, int] = field(default_factory=dict)

    @property
    def hubo_errores(self) -> bool:
        return any(f.estado == ERROR for f in self.factores)

    @property
    def total_publicaciones_nuevas(self) -> int:
        return sum(f.nuevas for f in self.factores)


@dataclass
class TotalFactor:
    """Total de publicaciones que la fuente encuentra para un factor (no se guarda nada)."""

    factor_id: int
    factor: str
    consulta: str
    total: Optional[int] = None
    error: Optional[str] = None


def total_citas_por_factor(anio_inicio: int, anio_fin: int) -> Dict[int, int]:
    """TC por factor_id: publicaciones distintas del periodo relacionadas con el factor."""
    filas = (
        PublicacionFactor.objects
        .filter(publicacion__anio__range=(anio_inicio, anio_fin))
        .values("factor_id")
        .annotate(total=Count("publicacion_id", distinct=True))
    )
    return {fila["factor_id"]: fila["total"] for fila in filas}


def _enlace(pub) -> Optional[str]:
    """Enlace de la publicación: `url` y, si falta, el identificador de OpenAlex."""
    return getattr(pub, "url", None) or getattr(pub, "openalex_id", None) or None


class ActualizacionBibliografica:
    """Ejecuta la búsqueda bibliográfica de todos los factores activos."""

    def __init__(self, buscador: Buscador, fuente: str = "OpenAlex"):
        self._buscador = buscador
        self._fuente = fuente

    def actualizar(
        self,
        anio_inicio: int = ANIO_INICIO_POR_DEFECTO,
        anio_fin: int = ANIO_FIN_POR_DEFECTO,
        limite: int = LIMITE_POR_DEFECTO,
    ) -> ResultadoActualizacion:
        if anio_inicio > anio_fin:
            raise ValueError("El año de inicio no puede ser mayor que el año de fin.")
        if limite < 1:
            raise ValueError("El límite de resultados debe ser al menos 1.")

        resultado = ResultadoActualizacion(anio_inicio=anio_inicio, anio_fin=anio_fin)
        factores = Factor.objects.filter(activo=True).order_by("dimension_id", "factor_id")
        for factor in factores:
            resultado.factores.append(self._buscar_factor(factor, anio_inicio, anio_fin, limite))
        resultado.tc_por_factor = total_citas_por_factor(anio_inicio, anio_fin)
        return resultado

    def totales_por_factor(
        self,
        anio_inicio: int = ANIO_INICIO_POR_DEFECTO,
        anio_fin: int = ANIO_FIN_POR_DEFECTO,
    ) -> List[TotalFactor]:
        """
        Pregunta a la fuente cuántas publicaciones hay por factor en el periodo.
        Solo consulta: no guarda búsquedas ni publicaciones. El buscador debe tener `contar`.
        """
        if anio_inicio > anio_fin:
            raise ValueError("El año de inicio no puede ser mayor que el año de fin.")
        totales: List[TotalFactor] = []
        for factor in Factor.objects.filter(activo=True).order_by("dimension_id", "factor_id"):
            consulta = construir_consulta(factor.nombre)
            fila = TotalFactor(factor_id=factor.factor_id, factor=factor.nombre, consulta=consulta)
            try:
                fila.total = self._buscador.contar(consulta, anio_inicio, anio_fin)
            except OpenAlexError as exc:
                fila.error = str(exc)
            totales.append(fila)
        return totales

    def _buscar_factor(self, factor: Factor, anio_inicio: int, anio_fin: int, limite: int) -> ResultadoFactor:
        consulta = construir_consulta(factor.nombre)
        busqueda = BusquedaBibliografica.objects.create(
            consulta=consulta, fuente=self._fuente,
            anio_inicio=anio_inicio, anio_fin=anio_fin, estado=EN_PROCESO,
        )
        res = ResultadoFactor(factor_id=factor.factor_id, factor=factor.nombre,
                              consulta=consulta, estado=EN_PROCESO)

        # La llamada a la red va fuera de la transacción: si falla, queda el registro con ERROR.
        try:
            encontradas = list(self._buscador.buscar(consulta, anio_inicio, anio_fin, limite))
        except OpenAlexError as exc:
            busqueda.estado = ERROR
            busqueda.save(update_fields=["estado"])
            res.estado, res.error = ERROR, str(exc)
            return res

        ahora = timezone.now()
        guardadas = 0
        with transaction.atomic():
            for posicion, pub in enumerate(encontradas, start=1):
                publicacion, creada = self._guardar_publicacion(pub)
                if publicacion is None:
                    continue
                guardadas += 1
                res.nuevas += int(creada)
                BusquedaPublicacion.objects.get_or_create(
                    busqueda=busqueda, publicacion=publicacion,
                    defaults={"posicion": posicion, "fecha_recuperacion": ahora, "seleccionada": True},
                )
                PublicacionFactor.objects.get_or_create(
                    publicacion=publicacion, factor=factor,
                    defaults={"justificacion": f"Recuperada con la consulta: {consulta}"},
                )
            busqueda.estado = COMPLETADA if guardadas else SIN_RESULTADOS
            busqueda.save(update_fields=["estado"])

        res.encontradas = guardadas
        res.estado = busqueda.estado
        return res

    def _guardar_publicacion(self, pub):
        """Crea o reutiliza la publicación. Evita duplicados por DOI o, sin DOI, por enlace."""
        doi = getattr(pub, "doi", None) or None
        enlace = _enlace(pub)
        datos = {
            "titulo": getattr(pub, "titulo", "") or "(sin título)",
            "anio": getattr(pub, "anio", None),
            "url": enlace,
            "fuente": self._fuente,
        }
        if doi:
            return Publicacion.objects.get_or_create(doi=doi, defaults=datos)
        if enlace:
            return Publicacion.objects.get_or_create(doi__isnull=True, url=enlace, defaults=datos)
        return None, False  # sin DOI ni enlace no se puede identificar: se omite
