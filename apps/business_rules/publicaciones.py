"""
Identidad de una publicación para no contarla dos veces (HU02).

Dos resultados son la misma publicación si tienen el mismo DOI normalizado; sin DOI,
si coinciden título normalizado y año. Python puro: no importa Django.
"""

import hashlib
import re

from apps.business_rules.coincidencia import normalizar

_PREFIJOS_DOI = re.compile(r'^(https?://(dx\.)?doi\.org/|doi:\s*)', re.IGNORECASE)


def normalizar_doi(doi):
    """'https://doi.org/10.1/ABC' -> '10.1/abc'. Devuelve None si no parece un DOI."""
    if not doi:
        return None
    limpio = _PREFIJOS_DOI.sub('', doi.strip()).strip().lower()
    return limpio if limpio.startswith('10.') and '/' in limpio else None


def huella_publicacion(doi, titulo, anio) -> str:
    """Clave de deduplicación (sha256 en hex, 64 caracteres)."""
    doi_n = normalizar_doi(doi)
    if doi_n:
        base = 'doi:' + doi_n
    else:
        titulo_n = normalizar(titulo)
        if not titulo_n:
            raise ValueError('Una publicación sin DOI necesita título.')
        base = f'titulo:{titulo_n}|{anio or ""}'
    return hashlib.sha256(base.encode('utf-8')).hexdigest()
