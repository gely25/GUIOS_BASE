"""
Sugerencia de factores por palabras clave (HU02, sin IA).

Compara el título y el resumen de una publicación con los términos de cada factor
(glosario en inglés + nombre del factor en español). Es una regla determinista: la
misma publicación siempre produce las mismas sugerencias. Las sugerencias no cuentan
para el TC hasta que el administrador las aprueba.

Python puro: no importa Django.
"""

import re
import unicodedata
from decimal import Decimal
from typing import Dict, Hashable, Iterable, List, NamedTuple

PUNTOS_TITULO = 2
PUNTOS_RESUMEN = 1
UMBRAL = 2            # una coincidencia en el título o dos en el resumen
PUNTOS_MAXIMOS = 6    # a partir de aquí la pertinencia es 100


class Sugerencia(NamedTuple):
    clave: Hashable
    pertinencia: Decimal  # 0 a 100
    justificacion: str


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y con un solo espacio entre palabras."""
    sin_acentos = ''.join(
        c for c in unicodedata.normalize('NFKD', texto or '') if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', sin_acentos.lower()).split())


def _contiene(texto_normalizado: str, termino_normalizado: str) -> bool:
    return bool(termino_normalizado) and f' {termino_normalizado} ' in f' {texto_normalizado} '


def puntuar(titulo: str, resumen: str, terminos: Iterable[str]):
    """Devuelve (puntos, términos en el título, términos solo en el resumen)."""
    titulo_n, resumen_n = normalizar(titulo), normalizar(resumen)
    en_titulo, en_resumen = [], []
    vistos = set()
    for termino in terminos:
        clave = normalizar(termino)
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        if _contiene(titulo_n, clave):
            en_titulo.append(termino)
        elif _contiene(resumen_n, clave):
            en_resumen.append(termino)
    puntos = PUNTOS_TITULO * len(en_titulo) + PUNTOS_RESUMEN * len(en_resumen)
    return puntos, en_titulo, en_resumen


def sugerir_factores(titulo: str, resumen: str, terminos_por_factor: Dict[Hashable, Iterable[str]]) -> List[Sugerencia]:
    """Factores cuyos términos aparecen lo suficiente en la publicación, de mayor a menor pertinencia."""
    sugerencias = []
    for clave, terminos in terminos_por_factor.items():
        puntos, en_titulo, en_resumen = puntuar(titulo, resumen, terminos)
        if puntos < UMBRAL:
            continue
        partes = []
        if en_titulo:
            partes.append('título: ' + ', '.join(en_titulo))
        if en_resumen:
            partes.append('resumen: ' + ', '.join(en_resumen))
        pertinencia = Decimal(min(puntos, PUNTOS_MAXIMOS) * 100) / Decimal(PUNTOS_MAXIMOS)
        sugerencias.append(Sugerencia(
            clave=clave,
            pertinencia=pertinencia.quantize(Decimal('0.01')),
            justificacion='Coincidencia por palabras clave en ' + '; '.join(partes) + '.',
        ))
    sugerencias.sort(key=lambda s: (-s.pertinencia, str(s.clave)))
    return sugerencias
