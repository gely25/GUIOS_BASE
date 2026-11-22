"""
Cliente de OpenAlex (servicio externo) para la búsqueda bibliográfica (HU02).

Capa: servicios externos. Solo sabe hablar con la API y devolver publicaciones
ya normalizadas; no conoce Django ni la base de datos. La orquestación y el
guardado los hace `BibliographicService`.

Configuración (archivo .env, nunca en el código):
    BIBLIOGRAPHIC_API_KEY   clave gratuita de OpenAlex (openalex.org/settings/api)
    BIBLIOGRAPHIC_BASE_URL  https://api.openalex.org

Solo usa la librería estándar, así no se agregan dependencias nuevas.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, List, Optional

URL_BASE_POR_DEFECTO = "https://api.openalex.org"
MAX_POR_PAGINA = 100  # límite de OpenAlex para `per_page`
# Busca solo en título y resumen (no en el texto completo), para que el factor
# sea el tema del artículo y no una mención de paso. Admite AND/OR/NOT y "frases".
CAMPO_BUSQUEDA = "search.title_and_abstract"


class OpenAlexError(Exception):
    """Fallo al consultar OpenAlex. El mensaje nunca incluye la clave ni la URL."""


@dataclass(frozen=True)
class PublicacionExterna:
    """Publicación devuelta por la API, lista para guardarse en `Publicacion`."""

    titulo: str
    anio: Optional[int]
    doi: Optional[str]          # normalizado: "10.xxxx/yyyy", en minúsculas
    url: Optional[str]          # enlace del DOI o, si no hay, el de OpenAlex
    openalex_id: str            # identificador estable (sirve si no hay DOI)
    fuente: str = "OpenAlex"


def normalizar_doi(doi: Optional[str]) -> Optional[str]:
    """Quita el prefijo de enlace ('https://doi.org/') y pasa a minúsculas."""
    if not doi:
        return None
    limpio = doi.strip()
    for prefijo in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if limpio.lower().startswith(prefijo):
            limpio = limpio[len(prefijo):]
            break
    return limpio.lower() or None


class OpenAlexClient:
    FUENTE = "OpenAlex"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 20,
        abrir: Optional[Callable] = None,
    ):
        self._api_key = api_key if api_key is not None else os.environ.get("BIBLIOGRAPHIC_API_KEY", "")
        base = base_url or os.environ.get("BIBLIOGRAPHIC_BASE_URL") or URL_BASE_POR_DEFECTO
        self._base_url = base.rstrip("/")
        self._timeout = timeout
        # `abrir` permite reemplazar la red en las pruebas.
        self._abrir = abrir or urllib.request.urlopen

    def buscar(
        self,
        consulta: str,
        anio_inicio: int = 2020,
        anio_fin: int = 2025,
        max_resultados: int = 25,
    ) -> List[PublicacionExterna]:
        """Busca publicaciones por texto dentro del rango de años. Lista vacía si no hay resultados."""
        self._validar(consulta, anio_inicio, anio_fin)
        por_pagina = max(1, min(int(max_resultados), MAX_POR_PAGINA))
        peticion = self._peticion(consulta, anio_inicio, anio_fin, por_pagina, "id,doi,display_name,publication_year")
        datos = self._leer_json(peticion)
        return self._normalizar(datos.get("results") or [])

    def contar(self, consulta: str, anio_inicio: int = 2020, anio_fin: int = 2025) -> int:
        """Total de publicaciones que OpenAlex encuentra para la consulta en el rango de años."""
        self._validar(consulta, anio_inicio, anio_fin)
        peticion = self._peticion(consulta, anio_inicio, anio_fin, 1, "id")
        datos = self._leer_json(peticion)
        total = (datos.get("meta") or {}).get("count")
        if not isinstance(total, int) or total < 0:
            raise OpenAlexError("La respuesta de OpenAlex no incluye el total de resultados.")
        return total

    def _validar(self, consulta: str, anio_inicio: int, anio_fin: int) -> None:
        if not consulta or not consulta.strip():
            raise ValueError("La consulta no puede estar vacía.")
        if anio_inicio > anio_fin:
            raise ValueError("El año de inicio no puede ser mayor que el año final.")
        if not self._api_key:
            raise OpenAlexError("Falta BIBLIOGRAPHIC_API_KEY en el archivo .env.")

    def _peticion(self, consulta, anio_inicio, anio_fin, por_pagina, campos):
        parametros = urllib.parse.urlencode({
            CAMPO_BUSQUEDA: consulta.strip(),
            "filter": f"from_publication_date:{anio_inicio}-01-01,to_publication_date:{anio_fin}-12-31",
            "select": campos,
            "per_page": por_pagina,
            "api_key": self._api_key,
        })
        return urllib.request.Request(
            f"{self._base_url}/works?{parametros}", headers={"Accept": "application/json"}
        )

    def _leer_json(self, peticion) -> dict:
        try:
            with self._abrir(peticion, timeout=self._timeout) as respuesta:
                return json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise OpenAlexError("OpenAlex rechazó la clave (revisa BIBLIOGRAPHIC_API_KEY).") from None
            if error.code == 429:
                raise OpenAlexError("OpenAlex limitó las consultas; intenta más tarde.") from None
            raise OpenAlexError(f"OpenAlex respondió con el código {error.code}.") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise OpenAlexError("No se pudo conectar con OpenAlex.") from None
        except (ValueError, UnicodeDecodeError):
            raise OpenAlexError("La respuesta de OpenAlex no tiene el formato esperado.") from None

    def _normalizar(self, obras: list) -> List[PublicacionExterna]:
        publicaciones = []
        for obra in obras:
            titulo = (obra.get("display_name") or "").strip()
            identificador = obra.get("id")
            if not titulo or not identificador:
                continue  # sin título o sin identificador no se puede guardar
            doi = normalizar_doi(obra.get("doi"))
            publicaciones.append(PublicacionExterna(
                titulo=titulo,
                anio=obra.get("publication_year"),
                doi=doi,
                url=f"https://doi.org/{doi}" if doi else identificador,
                openalex_id=identificador,
                fuente=self.FUENTE,
            ))
        return publicaciones
