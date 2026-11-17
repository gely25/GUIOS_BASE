"""
Fuente de datos simulada del catálogo para los indicadores de literatura (HU-03).

Capa: application. Es el ÚNICO punto que sabe de dónde salen los datos.
Hoy devuelve datos SIMULADOS (las citas TC reales las entregará HU02 y el
catálogo vivirá en PostgreSQL). Cuando existan los modelos, solo hay que
reemplazar `cargar_datos_catalogo` por una lectura de la versión vigente del
catálogo; el cálculo, la vista y las pruebas no cambian.
"""

from typing import Sequence

from .modelos import FactorCatalogo

# NS e IE reproducen el catálogo original de 2021 (18 factores, 61
# subfactores, IE = 3). Las citas TC son inventadas: solo sirven para ver el
# flujo funcionando mientras HU02 y la base de datos no están listas.
_TECNOLOGICA = "Tecnológica"
_ORGANIZACIONAL = "Organizacional"
_ECONOMICA = "Económica"

_DATOS_SIMULADOS = (
    FactorCatalogo("Compatibilidad", _TECNOLOGICA, 8, 3, 3),
    FactorCatalogo("Personalización", _TECNOLOGICA, 6, 12, 3),
    FactorCatalogo("Prueba", _TECNOLOGICA, 1, 0, 3),
    FactorCatalogo("Fiabilidad", _TECNOLOGICA, 5, 20, 3),
    FactorCatalogo("Reusabilidad", _TECNOLOGICA, 2, 5, 3),
    FactorCatalogo("Usabilidad", _TECNOLOGICA, 4, 16, 3),
    FactorCatalogo("Mantenibilidad", _TECNOLOGICA, 1, 4, 3),
    FactorCatalogo("Portabilidad", _TECNOLOGICA, 2, 7, 3),
    FactorCatalogo("Documentación", _TECNOLOGICA, 11, 9, 3),
    FactorCatalogo("Formación", _ORGANIZACIONAL, 4, 14, 3),
    FactorCatalogo("Tiempo de adopción", _ORGANIZACIONAL, 2, 3, 3),
    FactorCatalogo("Casos de estudio de adopción FLOSS", _ORGANIZACIONAL, 1, 2, 3),
    FactorCatalogo("Centralidad de la tecnología de la información", _ORGANIZACIONAL, 2, 6, 3),
    FactorCatalogo("Apoyo de la alta dirección", _ORGANIZACIONAL, 1, 5, 3),
    FactorCatalogo("Bloqueo de proveedores", _ORGANIZACIONAL, 1, 1, 3),
    FactorCatalogo("Soporte", _ORGANIZACIONAL, 6, 30, 3),
    FactorCatalogo("Actitud hacia el cambio", _ORGANIZACIONAL, 2, 8, 3),
    FactorCatalogo("Coste total de propiedad", _ECONOMICA, 2, 10, 3),
)


def cargar_datos_catalogo() -> Sequence[FactorCatalogo]:
    """
    Entrega los factores de la versión vigente del catálogo con su NS, TC e IE.

    HOY: datos simulados. MAÑANA: lectura de PostgreSQL (tablas factor,
    dimension, subfactor e indicador_factor de la versión vigente).
    """
    return _DATOS_SIMULADOS
