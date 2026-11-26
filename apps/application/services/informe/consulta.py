"""
Lectura de una evaluación finalizada para el informe (HU14).

Único punto de acceso a datos del informe. Solo lee: no calcula ni modifica nada.
Siempre filtra por el usuario: un decisor solo puede ver sus propias evaluaciones.
"""

from collections import defaultdict
from typing import Optional

from apps.data.models import (
    Documento,
    Evaluacion,
    EvaluacionFactor,
    Evidencia,
    ValoracionSubfactor,
)

from .modelos import (
    AMENAZA,
    DEBILIDAD,
    FORTALEZA,
    OPORTUNIDAD,
    DocumentoInforme,
    EvidenciaInforme,
    FactorInforme,
    InformeEvaluacion,
    InformeNoDisponible,
    ResumenFoda,
    ValoracionInforme,
)

LARGO_MAXIMO_FRAGMENTO = 400


def _recortar(texto: Optional[str], largo: int = LARGO_MAXIMO_FRAGMENTO) -> str:
    limpio = " ".join((texto or "").split())
    return limpio if len(limpio) <= largo else limpio[: largo - 1].rstrip() + "…"


def cargar_informe(usuario, evaluacion_id: Optional[int] = None) -> InformeEvaluacion:
    """
    Informe de la evaluación indicada, o de la más reciente con resultado si no se indica.
    Lanza InformeNoDisponible si no hay evaluación del usuario con resultado.
    """
    consulta = (
        Evaluacion.objects
        .filter(usuario=usuario, resultado__isnull=False)
        .select_related("organizacion", "usuario", "software", "catalogo", "resultado")
    )
    if evaluacion_id is not None:
        consulta = consulta.filter(evaluacion_id=evaluacion_id)
    evaluacion = None
    for candidata in consulta.order_by("-resultado__fecha_generacion", "-evaluacion_id"):
        if (candidata.resultado.recomendacion or "").strip():
            evaluacion = candidata
            break
    if evaluacion is None:
        raise InformeNoDisponible("No hay una evaluación con resultado para mostrar.")

    resultado = evaluacion.resultado
    factores_bd = list(
        EvaluacionFactor.objects
        .filter(evaluacion=evaluacion, relevante=True)
        .select_related("factor__dimension")
        .order_by("factor__dimension_id", "factor_id")
    )

    valoraciones_por_factor = defaultdict(list)
    valoraciones_bd = (
        ValoracionSubfactor.objects
        .filter(evaluacion_factor__in=factores_bd)
        .select_related("subfactor")
        .order_by("subfactor_id")
    )
    evidencias_por_valoracion = defaultdict(list)
    for ev in (Evidencia.objects
               .filter(valoracion__in=valoraciones_bd)
               .select_related("fragmento__documento")
               .order_by("-relevancia", "evidencia_id")):
        frag = ev.fragmento
        evidencias_por_valoracion[ev.valoracion_id].append(EvidenciaInforme(
            documento=frag.documento.nombre,
            pagina=frag.pagina,
            seccion=frag.seccion,
            hoja=frag.hoja,
            fragmento=_recortar(frag.contenido),
            relevancia=ev.relevancia,
            justificacion=ev.justificacion,
        ))
    for val in valoraciones_bd:
        valoraciones_por_factor[val.evaluacion_factor_id].append(ValoracionInforme(
            subfactor=val.subfactor.descripcion,
            valor_ia=val.valor_ia,
            valor_confirmado=val.valor_confirmado,
            estado_validacion=val.estado_validacion,
            justificacion_ia=val.justificacion_ia,
            justificacion_decisor=val.justificacion_decisor,
            evidencias=evidencias_por_valoracion.get(val.valoracion_id, []),
        ))

    factores = [
        FactorInforme(
            dimension=ef.factor.dimension.nombre,
            factor=ef.factor.nombre,
            alcance=ef.factor.alcance,
            importancia_sugerida=ef.importancia_sugerida,
            importancia_decisor=ef.importancia_decisor,
            importancia_relativa=ef.importancia_relativa,
            ponderacion_media=ef.ponderacion_media,
            clasificacion_foda=ef.clasificacion_foda,
            valoraciones=valoraciones_por_factor.get(ef.evaluacion_factor_id, []),
        )
        for ef in factores_bd
    ]

    conteo = {FORTALEZA: 0, OPORTUNIDAD: 0, DEBILIDAD: 0, AMENAZA: 0}
    sin_clasificar = 0
    for f in factores:
        if f.clasificacion_foda in conteo:
            conteo[f.clasificacion_foda] += 1
        else:
            sin_clasificar += 1

    documentos = [
        DocumentoInforme(d.nombre, d.tipo, d.version, d.hash_sha256, d.fecha_carga)
        for d in Documento.objects.filter(evaluacion=evaluacion).order_by("fecha_carga", "documento_id")
    ]

    return InformeEvaluacion(
        evaluacion_id=evaluacion.evaluacion_id,
        software=evaluacion.software.nombre,
        software_version=evaluacion.software.version,
        proveedor=evaluacion.software.proveedor,
        organizacion=evaluacion.organizacion.nombre,
        decisor=evaluacion.usuario.nombre,
        catalogo_version=evaluacion.catalogo.version,
        estado=evaluacion.estado,
        fecha_inicio=evaluacion.fecha_inicio,
        fecha_fin=evaluacion.fecha_fin,
        recomendacion=resultado.recomendacion,
        explicacion=resultado.explicacion,
        version_regla=resultado.version_regla,
        fecha_resultado=resultado.fecha_generacion,
        sector=evaluacion.organizacion.sector,
        tamano=evaluacion.organizacion.tamano,
        objetivo_adopcion=evaluacion.organizacion.objetivo_adopcion,
        descripcion_software=evaluacion.software.descripcion,
        resumen_foda=ResumenFoda(
            fortalezas=conteo[FORTALEZA], oportunidades=conteo[OPORTUNIDAD],
            debilidades=conteo[DEBILIDAD], amenazas=conteo[AMENAZA], sin_clasificar=sin_clasificar),
        factores=factores,
        documentos=documentos,
    )
