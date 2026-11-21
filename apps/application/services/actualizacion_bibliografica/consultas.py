"""
Construcción de las consultas bibliográficas (HU02).

Los factores del catálogo están en español, pero OpenAlex responde mejor con
términos en inglés. Cada consulta exige DOS cosas a la vez:
  1. alguno de los términos del factor, y
  2. el contexto: software libre/FLOSS y adopción.
Se escribe con la sintaxis de OpenAlex: AND/OR en mayúsculas, "frases" entre
comillas y paréntesis. Si un factor no está en el diccionario (por ejemplo,
uno nuevo del catálogo), se usa su nombre tal cual como único término.
"""

from typing import Tuple

CONTEXTO = '("open source software" OR "free software" OR "FLOSS") AND adoption'

# Clave: nombre del factor tal como está en el catálogo (insensible a mayúsculas).
TERMINOS_POR_FACTOR = {
    "compatibilidad": ("compatibility", "interoperability"),
    "fiabilidad": ("reliability",),
    "mantenibilidad": ("maintainability",),
    "personalización": ("customization", "customisation"),
    "prueba": ("testability", "software testing"),
    "documentación": ("documentation",),
    "portabilidad": ("portability",),
    "reusabilidad": ("reusability", "software reuse"),
    "usabilidad": ("usability",),
    "apoyo de la alta dirección": ("top management support", "management support"),
    "formación": ("user training", "staff training"),
    "soporte": ("technical support", "vendor support", "community support"),
    "actitud hacia el cambio": ("attitude toward change", "resistance to change"),
    "bloqueo de proveedores": ("vendor lock-in", "vendor lock in"),
    "casos de estudio de adopción floss": ("case study",),
    "centralidad de la tecnología de la información": ("IT centrality", "information technology centrality"),
    "tiempo de adopción": ("adoption time", "time of adoption"),
    "coste total de propiedad": ("total cost of ownership", "TCO"),
}


def terminos_de(nombre_factor: str) -> Tuple[str, ...]:
    nombre = (nombre_factor or "").strip()
    if not nombre:
        raise ValueError("El factor no tiene nombre.")
    return TERMINOS_POR_FACTOR.get(nombre.lower(), (nombre,))


def construir_consulta(nombre_factor: str) -> str:
    """Consulta booleana: (términos del factor) AND (software libre) AND adoption."""
    terminos = " OR ".join(f'"{t.replace(chr(34), "")}"' for t in terminos_de(nombre_factor))
    return f"({terminos}) AND {CONTEXTO}"
