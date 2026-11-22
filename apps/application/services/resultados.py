"""
Capa: application. Datos de la pantalla de Resultados (HU12 y HU14).

Solo lee lo que ya quedó guardado: la PM y la clasificación FODA calculadas por HU12, y la
recomendación y la explicación si ya existen (otras historias). No calcula nada.
Siempre filtra por el usuario: un decisor solo ve sus propias evaluaciones.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from django.db.models import Exists, OuterRef

from apps.data.models import Evaluacion, EvaluacionFactor, ValoracionSubfactor

from .informe.modelos import CLASES_FODA, InformeNoDisponible

_VALIDAS = ('CONFIRMADA', 'MODIFICADA')


@dataclass
class FactorResultado:
    dimension: str
    factor: str
    ir: Optional[int]
    pm: Decimal
    foda: Optional[str]
    valores: List[int] = field(default_factory=list)

    @property
    def porcentaje(self) -> int:
        """Largo de la barra del perfil de cumplimiento (escala de 0 a 4)."""
        return int(min(max(self.pm, Decimal(0)), Decimal(4)) / Decimal(4) * 100)

    @property
    def confirmadas_texto(self) -> str:
        if not self.valores:
            return '—'
        if len(self.valores) <= 4:
            return ' y '.join(str(v) for v in self.valores) if len(self.valores) <= 2 \
                else ', '.join(str(v) for v in self.valores)
        return f'{len(self.valores)} valoraciones'


@dataclass
class ResultadosEvaluacion:
    evaluacion_id: int
    software: str
    version: Optional[str]
    organizacion: str
    fecha_corte: Optional[object]
    confirmadas: int
    total: int
    factores: List[FactorResultado]
    recomendacion: Optional[str] = None
    explicacion: Optional[str] = None
    version_regla: Optional[str] = None

    @property
    def codigo(self) -> str:
        return f'EV-{self.evaluacion_id:03d}'

    @property
    def software_completo(self) -> str:
        return f'{self.software} {self.version}'.strip() if self.version else self.software

    @property
    def completa(self) -> bool:
        return self.total > 0 and self.confirmadas == self.total

    @property
    def cuadrantes(self):
        """(clase FODA, factores de esa clase) en el orden de la matriz: F, O, D, A."""
        return [(clase, [f for f in self.factores if f.foda == clase]) for clase in CLASES_FODA]

    @property
    def tiene_recomendacion(self) -> bool:
        return bool((self.recomendacion or '').strip())


class ResultadosService:
    """Lectura de PM, FODA y (si existen) recomendación de una evaluación."""

    @staticmethod
    def cargar(usuario, evaluacion_id: Optional[int] = None) -> ResultadosEvaluacion:
        """
        Resultados de la evaluación indicada, o de la más reciente con PM calculada.
        Lanza InformeNoDisponible si no existe, no es del usuario o aún no tiene PM.
        """
        con_pm = EvaluacionFactor.objects.filter(
            evaluacion=OuterRef('pk'), relevante=True, ponderacion_media__isnull=False)
        consulta = (Evaluacion.objects.filter(usuario=usuario)
                    .annotate(tiene_pm=Exists(con_pm)).filter(tiene_pm=True)
                    .select_related('organizacion', 'software'))
        if evaluacion_id is not None:
            consulta = consulta.filter(evaluacion_id=evaluacion_id)
        evaluacion = consulta.order_by('-evaluacion_id').first()
        if evaluacion is None:
            raise InformeNoDisponible('No hay una evaluación con PM calculada para mostrar.')

        factores_bd = list(EvaluacionFactor.objects.filter(
            evaluacion=evaluacion, relevante=True, ponderacion_media__isnull=False,
        ).select_related('factor__dimension').order_by('factor__dimension_id', 'factor_id'))
        valoraciones = list(ValoracionSubfactor.objects.filter(
            evaluacion_factor__evaluacion=evaluacion, evaluacion_factor__relevante=True,
            evaluacion_factor__importancia_relativa__in=(2, 3, 4)).order_by('subfactor_id'))
        confirmadas = [v for v in valoraciones if v.estado_validacion in _VALIDAS and v.valor_confirmado]
        por_factor = {}
        for v in confirmadas:
            por_factor.setdefault(v.evaluacion_factor_id, []).append(v.valor_confirmado)
        fechas = [v.fecha_validacion for v in confirmadas if v.fecha_validacion]

        resultado = getattr(evaluacion, 'resultado', None)
        return ResultadosEvaluacion(
            evaluacion_id=evaluacion.evaluacion_id, software=evaluacion.software.nombre,
            version=evaluacion.software.version, organizacion=evaluacion.organizacion.nombre,
            fecha_corte=max(fechas) if fechas else None,
            confirmadas=len(confirmadas), total=len(valoraciones),
            factores=[FactorResultado(
                dimension=ef.factor.dimension.nombre, factor=ef.factor.nombre,
                ir=ef.importancia_relativa, pm=ef.ponderacion_media, foda=ef.clasificacion_foda,
                valores=por_factor.get(ef.evaluacion_factor_id, [])) for ef in factores_bd],
            recomendacion=resultado.recomendacion if resultado else None,
            explicacion=resultado.explicacion if resultado else None,
            version_regla=resultado.version_regla if resultado else None)