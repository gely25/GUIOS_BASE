"""
Servicio de Aplicación: ImportanciaFactoresService.

Capa: application. Paso 2 de la evaluación (HU06): el decisor fija la Importancia del
Decisor (ID) de cada factor del catálogo; la Importancia Relativa (IR) sale de combinar
ID e IS con la regla de business_rules, y los factores con IR = 1 quedan fuera de la
evaluación.
"""

from typing import Dict, List, NamedTuple, Optional

from django.db import transaction

from apps.business_rules.funcion_discreta import ETIQUETAS
from apps.business_rules.ir import calcular_ir, se_evalua
from apps.data.models import Evaluacion, EvaluacionFactor, IndicadorFactor, ValoracionSubfactor


class ImportanciaInvalidaError(ValueError):
    """Los datos enviados no son una valoración de importancias aceptable."""


class FilaImportancia(NamedTuple):
    factor_id: int
    nombre: str
    dimension: str
    is_: int
    id_: int
    ir: int
    relevante: bool


class ImportanciaFactoresService:
    """Lectura y registro de ID, IR y relevancia de los factores de una evaluación."""

    NIVELES = ETIQUETAS

    @staticmethod
    def evaluacion_del_decisor(usuario, evaluacion_id=None) -> Optional[Evaluacion]:
        """
        Evaluación EN_PROCESO del decisor: la indicada o, si no se indica, la más reciente.

        Devuelve None si no existe o no es suya; así un decisor no ve evaluaciones ajenas.
        """
        consulta = (
            Evaluacion.objects.filter(usuario=usuario, estado=Evaluacion.EN_PROCESO)
            .select_related('software', 'organizacion', 'catalogo')
            .order_by('-fecha_inicio', '-pk')
        )
        if evaluacion_id is None:
            return consulta.first()
        return consulta.filter(pk=evaluacion_id).first()

    def filas(self, evaluacion, ids: Optional[Dict[int, int]] = None) -> List[FilaImportancia]:
        """
        Factores del catálogo de la evaluación con su IS.

        ID = la enviada en `ids` (si es válida), la guardada o, si no hay, la IS.
        """
        enviadas = ids or {}
        guardadas = {
            ef.factor_id: ef.importancia_decisor
            for ef in EvaluacionFactor.objects.filter(evaluacion=evaluacion)
        }
        indicadores = (
            IndicadorFactor.objects.filter(catalogo=evaluacion.catalogo, importancia_sugerida__isnull=False)
            .select_related('factor__dimension')
            .order_by('factor__dimension__dimension_id', 'factor__factor_id')
        )
        filas = []
        for indicador in indicadores:
            sugerida = indicador.importancia_sugerida
            propuesta = enviadas.get(indicador.factor_id)
            if propuesta not in self.NIVELES:
                propuesta = guardadas.get(indicador.factor_id)
            decisor = propuesta or sugerida
            ir = calcular_ir(decisor, sugerida)
            filas.append(FilaImportancia(
                factor_id=indicador.factor_id,
                nombre=indicador.factor.nombre,
                dimension=indicador.factor.dimension.nombre,
                is_=sugerida,
                id_=decisor,
                ir=ir,
                relevante=se_evalua(ir),
            ))
        return filas

    def agrupadas(self, evaluacion, ids: Optional[Dict[int, int]] = None) -> List[dict]:
        """Las filas agrupadas por dimensión, conservando el orden del catálogo."""
        grupos: Dict[str, List[FilaImportancia]] = {}
        for fila in self.filas(evaluacion, ids):
            grupos.setdefault(fila.dimension, []).append(fila)
        return [
            {'dimension': nombre, 'filas': filas, 'relevantes': sum(1 for f in filas if f.relevante)}
            for nombre, filas in grupos.items()
        ]

    def tiene_importancias(self, evaluacion) -> bool:
        return EvaluacionFactor.objects.filter(evaluacion=evaluacion).exists()

    @transaction.atomic
    def guardar(self, evaluacion, ids: Dict[int, int]) -> List[FilaImportancia]:
        """
        Registra la ID de cada factor y calcula IR y relevancia.

        `ids` es {factor_id: ID}. Debe traer todos los factores del catálogo, con
        valores de 1 a 4, y al menos un factor debe quedar relevante (IR distinto de 1).
        Si la evaluación ya tiene valoraciones de subfactores no se puede cambiar, porque
        la relevancia de los factores ya condicionó esas valoraciones.
        """
        if ValoracionSubfactor.objects.filter(evaluacion_factor__evaluacion=evaluacion).exists():
            raise ImportanciaInvalidaError(
                'Esta evaluación ya tiene valoraciones de subfactores; '
                'la importancia de los factores ya no se puede cambiar.')

        filas = self.filas(evaluacion)
        if not filas:
            raise ImportanciaInvalidaError('El catálogo de esta evaluación no tiene factores.')

        resultado = []
        for fila in filas:
            valor = ids.get(fila.factor_id)
            if isinstance(valor, bool) or not isinstance(valor, int) or valor not in self.NIVELES:
                raise ImportanciaInvalidaError(f'Falta valorar el factor «{fila.nombre}».')
            ir = calcular_ir(valor, fila.is_)
            resultado.append(fila._replace(id_=valor, ir=ir, relevante=se_evalua(ir)))

        if not any(f.relevante for f in resultado):
            raise ImportanciaInvalidaError(
                'Al menos un factor debe quedar relevante para poder evaluar.')

        for fila in resultado:
            EvaluacionFactor.objects.update_or_create(
                evaluacion=evaluacion, factor_id=fila.factor_id,
                defaults={
                    'importancia_sugerida': fila.is_,
                    'importancia_decisor': fila.id_,
                    'importancia_relativa': fila.ir,
                    'relevante': fila.relevante,
                })
        return resultado
