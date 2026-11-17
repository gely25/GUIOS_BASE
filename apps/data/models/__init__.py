"""
Modelos de la capa de datos - GUIOS PRO.

Un archivo por grupo del modelo entidad-relación (sección 6.1 del diseño):
catálogo, usuarios, evaluaciones, bibliografía, documentos y resultados.
Los nombres de tabla y de columna siguen el esquema acordado por el grupo.
"""

from .bibliografia import BusquedaBibliografica, BusquedaPublicacion, Publicacion, PublicacionFactor
from .catalogo import CatalogoVersion, Dimension, Factor, IndicadorFactor, Subfactor
from .documentos import Documento, Evidencia, FragmentoDocumento
from .evaluaciones import Evaluacion, EvaluacionFactor, Software, ValoracionSubfactor
from .resultados import ResultadoEvaluacion
from .usuarios import Organizacion, Usuario

__all__ = [
    'BusquedaBibliografica', 'BusquedaPublicacion', 'Publicacion', 'PublicacionFactor',
    'CatalogoVersion', 'Dimension', 'Factor', 'IndicadorFactor', 'Subfactor',
    'Documento', 'Evidencia', 'FragmentoDocumento',
    'Evaluacion', 'EvaluacionFactor', 'Software', 'ValoracionSubfactor',
    'ResultadoEvaluacion',
    'Organizacion', 'Usuario',
]
