"""
Contrato de una fuente científica (HU02).

Cualquier API (OpenAlex hoy, otra mañana) implementa `buscar` y devuelve
`ResultadoPublicacion`. Los servicios de aplicación solo conocen este contrato.
"""

from typing import List, NamedTuple, Optional, Protocol


class ResultadoPublicacion(NamedTuple):
    titulo: str
    anio: Optional[int]
    doi: Optional[str]
    url: Optional[str]
    resumen: Optional[str]


class ErrorFuenteCientifica(Exception):
    """La fuente no respondió o respondió algo que no se pudo leer."""


class FuenteCientifica(Protocol):
    nombre: str

    def buscar(self, consulta: str, anio_inicio: int, anio_fin: int, maximo: int) -> List[ResultadoPublicacion]:
        """Publicaciones del periodo que responden a la consulta, en orden de relevancia."""
        ...
