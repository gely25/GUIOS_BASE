"""
Cliente de OpenAlex (https://openalex.org): catálogo abierto de literatura científica.

No necesita API key; con `BIBLIOGRAPHIC_API_KEY` se usa una propia (gratuita) en lugar del
cupo diario compartido. Solo usa la biblioteca estándar.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

from .base import ErrorFuenteCientifica, ResultadoPublicacion

URL_POR_DEFECTO = 'https://api.openalex.org'
_POR_PAGINA_MAX = 200
_CAMPOS = 'id,doi,title,publication_year,abstract_inverted_index,primary_location'


def reconstruir_resumen(indice_invertido) -> Optional[str]:
    """OpenAlex entrega el resumen como {palabra: [posiciones]}; se vuelve a armar el texto."""
    if not indice_invertido:
        return None
    posiciones = {}
    for palabra, lugares in indice_invertido.items():
        for lugar in lugares:
            posiciones[lugar] = palabra
    return ' '.join(posiciones[i] for i in sorted(posiciones)) or None


def convertir(obra) -> Optional[ResultadoPublicacion]:
    titulo = (obra.get('title') or '').strip()
    if not titulo:
        return None
    ubicacion = obra.get('primary_location') or {}
    return ResultadoPublicacion(
        titulo=titulo,
        anio=obra.get('publication_year'),
        doi=obra.get('doi'),
        url=ubicacion.get('landing_page_url') or obra.get('doi') or obra.get('id'),
        resumen=reconstruir_resumen(obra.get('abstract_inverted_index')),
    )


class OpenAlexFuente:
    nombre = 'OpenAlex'

    def __init__(self, url_base=URL_POR_DEFECTO, api_key=None, timeout=20, reintentos=2, abrir=None):
        self.url_base = (url_base or URL_POR_DEFECTO).rstrip('/')
        self.api_key = api_key or None
        self.timeout = timeout
        self.reintentos = reintentos
        self._abrir = abrir or urllib.request.urlopen

    def _url(self, consulta, anio_inicio, anio_fin, por_pagina, pagina):
        parametros = {
            'search': consulta,
            'filter': f'from_publication_date:{anio_inicio}-01-01,to_publication_date:{anio_fin}-12-31',
            'per-page': por_pagina,
            'page': pagina,
            'select': _CAMPOS,
        }
        if self.api_key:
            parametros['api_key'] = self.api_key
        return f'{self.url_base}/works?{urllib.parse.urlencode(parametros)}'

    def _pedir(self, url):
        peticion = urllib.request.Request(url, headers={'User-Agent': 'GUIOS-PRO/1.0', 'Accept': 'application/json'})
        ultimo_error = None
        for intento in range(self.reintentos + 1):
            try:
                with self._abrir(peticion, timeout=self.timeout) as respuesta:
                    return json.loads(respuesta.read().decode('utf-8'))
            except urllib.error.HTTPError as error:
                ultimo_error = error
                if error.code not in (429, 500, 502, 503, 504):
                    break
            except (urllib.error.URLError, TimeoutError, ValueError) as error:
                ultimo_error = error
            if intento < self.reintentos:
                time.sleep(2 ** intento)
        raise ErrorFuenteCientifica(f'OpenAlex no respondió correctamente: {ultimo_error}')

    def buscar(self, consulta, anio_inicio, anio_fin, maximo) -> List[ResultadoPublicacion]:
        resultados, pagina = [], 1
        por_pagina = max(1, min(maximo, _POR_PAGINA_MAX))
        while len(resultados) < maximo:
            datos = self._pedir(self._url(consulta, anio_inicio, anio_fin, por_pagina, pagina))
            obras = datos.get('results')
            if not isinstance(obras, list):
                raise ErrorFuenteCientifica('OpenAlex devolvió una respuesta sin resultados.')
            resultados.extend(r for r in map(convertir, obras) if r is not None)
            if len(obras) < por_pagina:
                break
            pagina += 1
        return resultados[:maximo]
