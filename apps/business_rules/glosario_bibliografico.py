"""
Glosario fijo de términos por factor para buscar literatura (HU02).

La literatura científica sobre adopción de FLOSS está casi toda en inglés, así que cada
factor GUIOS tiene una lista de términos en inglés escrita a mano a partir del nombre del
factor y de sus subfactores (catálogo 2021). No se usa IA: la consulta es reproducible.

Python puro: no importa Django.
"""

from typing import Dict, Sequence, Tuple

# Contexto común: la publicación tiene que tratar de software libre / de código abierto.
CONTEXTO_FLOSS: Tuple[str, ...] = (
    'open source', 'free software', 'FLOSS', 'FOSS', 'open-source software',
)
TERMINO_ADOPCION = 'adoption'

GLOSARIO: Dict[str, Tuple[str, ...]] = {
    'Compatibilidad': ('compatibility', 'interoperability', 'software integration',
                       'open standards', 'file formats', 'cross-platform'),
    'Personalización': ('customization', 'customisation', 'extensibility', 'modularity',
                        'source code modification', 'plugins'),
    'Prueba': ('trialability', 'ease of deployment', 'software trial', 'pilot testing'),
    'Fiabilidad': ('reliability', 'stability', 'software security', 'robustness',
                   'access control'),
    'Reusabilidad': ('reusability', 'software reuse', 'component reuse', 'license compatibility'),
    'Usabilidad': ('usability', 'ease of use', 'user interface', 'user experience', 'learnability'),
    'Mantenibilidad': ('maintainability', 'software maintenance', 'active maintenance',
                       'project activity'),
    'Portabilidad': ('portability', 'mobile application', 'platform independence',
                     'database independence'),
    'Documentación': ('documentation', 'user documentation', 'developer documentation',
                      'user manual'),
    'Formación': ('training', 'user training', 'technical skills', 'learning curve', 'self-learning'),
    'Tiempo de adopción': ('adoption time', 'implementation time', 'deployment time',
                           'time to adopt', 'installation requirements'),
    'Casos de estudio de adopción FLOSS': ('case study', 'success story', 'adoption experience',
                                           'lessons learned'),
    'Centralidad de la tecnología de la información': ('IT centrality', 'IT infrastructure',
                                                       'centralized infrastructure',
                                                       'work environment'),
    'Apoyo de la alta dirección': ('top management support', 'management support',
                                   'executive support', 'leadership support'),
    'Bloqueo de proveedores': ('vendor lock-in', 'lock-in', 'vendor dependence',
                               'vendor independence'),
    'Soporte': ('technical support', 'community support', 'commercial support',
                'consultants', 'support services'),
    'Actitud hacia el cambio': ('resistance to change', 'attitude toward change',
                                'change management', 'user acceptance'),
    'Coste total de propiedad': ('total cost of ownership', 'TCO', 'hidden costs',
                                 'cost savings', 'licensing costs'),
}


def terminos_de(nombre_factor: str) -> Tuple[str, ...]:
    """Términos en inglés del factor; si el factor es nuevo y no está en el glosario, su nombre."""
    return GLOSARIO.get(nombre_factor, (nombre_factor,))


def _entre_comillas(terminos: Sequence[str]) -> str:
    return ' OR '.join(f'"{t}"' for t in terminos)


def construir_consulta(nombre_factor: str) -> str:
    """
    Consulta booleana para la fuente científica:
    (contexto FLOSS) AND adoption AND (términos del factor).
    """
    return '({}) AND {} AND ({})'.format(
        _entre_comillas(CONTEXTO_FLOSS), TERMINO_ADOPCION, _entre_comillas(terminos_de(nombre_factor)))
