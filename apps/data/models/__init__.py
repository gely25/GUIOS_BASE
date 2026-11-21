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
from .preguntas import PreguntaComplementaria
from .resultados import ResultadoEvaluacion
from .usuarios import Organizacion, Usuario

__all__ = [
    'BusquedaBibliografica', 'BusquedaPublicacion', 'Publicacion', 'PublicacionFactor',
    'CatalogoVersion', 'Dimension', 'Factor', 'IndicadorFactor', 'Subfactor',
    'Documento', 'Evidencia', 'FragmentoDocumento',
    'Evaluacion', 'EvaluacionFactor', 'Software', 'ValoracionSubfactor',
    'ResultadoEvaluacion', 'PreguntaComplementaria',
    'Organizacion', 'Usuario',
]

from .suficiencia import AnalisisSuficiencia
__all__.append('AnalisisSuficiencia')

from .lotes_hu09 import LoteHU09
__all__.append('LoteHU09')

from .suficiencia import HistorialSuficiencia
__all__.append('HistorialSuficiencia')

from .revision_humana import RevisionHumana
__all__.append('RevisionHumana')

from .revision_humana import BorradorRevisionHumana
__all__.append('BorradorRevisionHumana')

from .revision_humana import ReaperturaRevisionHumana
__all__.append('ReaperturaRevisionHumana')
