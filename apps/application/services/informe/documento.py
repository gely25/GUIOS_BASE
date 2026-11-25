"""
Contenido del informe (HU14) listo para mostrarse.

Un solo constructor alimenta la pantalla del Informe y el PDF, así los dos dicen lo mismo y en el
mismo orden. No calcula IS, IR, PM ni FODA: parte de lo ya guardado y solo ordena, cuenta y redacta.

Los textos de «qué hacer» (ACCIONES) son del equipo y están pendientes de validación con el docente,
igual que la regla de recomendación A/B/C.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from .modelos import AMENAZA, DEBILIDAD, FORTALEZA, OPORTUNIDAD, FactorInforme, InformeEvaluacion

RESPUESTAS = {1: "No cumple", 2: "No sé", 3: "Cumple parcialmente", 4: "Cumple"}

CLAVE_FODA = {FORTALEZA: "F", OPORTUNIDAD: "O", DEBILIDAD: "D", AMENAZA: "A"}
PLURAL = {"F": "Fortalezas", "O": "Oportunidades", "D": "Debilidades", "A": "Amenazas"}
SINGULAR = {"F": FORTALEZA, "O": OPORTUNIDAD, "D": DEBILIDAD, "A": AMENAZA}

TAG_INFORMACION = "info"
TAG_INCUMPLIMIENTO = "incumplimiento"
ETIQUETA_TAG = {TAG_INFORMACION: "Falta de información", TAG_INCUMPLIMIENTO: "Incumplimiento"}

ACCIONES = {
    TAG_INFORMACION: "Comprobarlo y reunir evidencia antes de decidir.",
    DEBILIDAD: "Reforzarlo en su organización antes de adoptar.",
    AMENAZA: "Vigilarlo y planear cómo mitigarlo.",
}

MAX_ATENDER = 6
MAX_VALORACIONES_POR_FACTOR = 2
MAX_EVIDENCIAS_POR_VALORACION = 2
MAX_FRAGMENTO = 230

TEXTOS_METODO = (
    "Este informe resume la evaluación de {software} para {organizacion}. Los valores (importancia, PM, "
    "FODA y recomendación) los calculan las reglas del sistema a partir de las valoraciones que el "
    "decisor confirmó.",
    "La inteligencia artificial propone valoraciones y extrae fragmentos de los documentos, pero no "
    "calcula resultados ni cambia ningún valor: toda propuesta pasó por la revisión del decisor.",
    "La regla de recomendación (A, B, C) sigue la formalización del equipo del proyecto y está "
    "pendiente de validación con el docente.",
)

CUADRANTES = (
    ("F", "Interno · va bien"),
    ("D", "Interno · reforzar"),
    ("O", "Externo · va bien"),
    ("A", "Externo · vigilar"),
)


def _coma(valor, decimales=2) -> str:
    return f"{float(valor):.{decimales}f}".replace(".", ",")


def _limpio(texto: str, maximo: int = MAX_FRAGMENTO) -> str:
    plano = re.sub(r"\s+", " ", (texto or "")).strip()
    return plano if len(plano) <= maximo else plano[: maximo - 1].rstrip() + "…"


def _justificacion_util(texto: str) -> str:
    """La justificación solo se muestra si dice algo más que «Valoración manual del decisor: …»."""
    limpio = _limpio(texto, 200)
    return "" if limpio.lower().startswith("valoración manual del decisor") else limpio


def _hash_corto(valor: Optional[str]) -> str:
    if not valor:
        return "—"
    return valor if len(valor) <= 22 else f"{valor[:12]}…{valor[-8:]}"


@dataclass(frozen=True)
class FilaAtender:
    factor: str
    dimension: str
    clase: str          # F, O, D, A
    nombre_clase: str   # Fortaleza…
    ambito: str
    ir: Optional[int]
    pm: str
    tag: str            # info | incumplimiento | ""
    etiqueta_tag: str
    motivo: str
    accion: str
    ajustada: bool


@dataclass(frozen=True)
class FilaFactor:
    factor: str
    alcance: str
    ir: Optional[int]
    pm: str
    porcentaje: float
    clase: str
    nombre_clase: str
    tag: str
    etiqueta_tag: str
    ajustada: bool


@dataclass(frozen=True)
class Cuadrante:
    clave: str
    titulo: str
    etiqueta: str
    factores: list      # [(nombre, ir, pm)]


@dataclass(frozen=True)
class EvidenciaVista:
    documento: str
    ubicacion: str
    fragmento: str
    relevancia: str


@dataclass(frozen=True)
class RespuestaVista:
    subfactor: str
    respuesta: str
    clave: str          # nocumple | nose | parcial | cumple
    justificacion: str
    evidencias: list
    sin_evidencia: bool


@dataclass(frozen=True)
class EvidenciaFactor:
    factor: str
    clase: str
    nombre_clase: str
    respuestas: list
    omitidas: int


@dataclass(frozen=True)
class FuenteVista:
    nombre: str
    tipo: str
    fecha_carga: object
    huella: str


@dataclass
class DocumentoVista:
    evaluacion_id: int
    software: str
    organizacion: str
    decisor: str
    emitido: object
    version_regla: str
    fecha_resultado: object
    letra: str
    titulo_recomendacion: str
    sintesis: str
    a_favor: int
    en_contra: int
    total: int
    proporciones: list = field(default_factory=list)     # [(clase, plural, cantidad, porcentaje)]
    atender: List[FilaAtender] = field(default_factory=list)
    atender_extra: int = 0
    cuadrantes: List[Cuadrante] = field(default_factory=list)
    filas: List[FilaFactor] = field(default_factory=list)
    hay_ajustes: bool = False
    evidencia: List[EvidenciaFactor] = field(default_factory=list)
    fuentes: List[FuenteVista] = field(default_factory=list)
    total_valoraciones: int = 0
    total_evidencias: int = 0
    metodo: tuple = ()


def letra_de(recomendacion: str) -> str:
    """A, B o C a partir del texto guardado de la recomendación."""
    from apps.application.services.recomendacion import TEXTOS_RECOMENDACION

    for letra, texto in TEXTOS_RECOMENDACION.items():
        if (recomendacion or "").strip().lower() == texto.lower():
            return letra
    coincidencia = re.match(r"\s*Recomendaci[oó]n\s+([ABC])\b", recomendacion or "", re.IGNORECASE)
    return coincidencia.group(1).upper() if coincidencia else ""


def _conteo_respuestas(factor: FactorInforme) -> dict:
    conteo = {1: 0, 2: 0, 3: 0, 4: 0}
    for valoracion in factor.valoraciones:
        if valoracion.valor_confirmado in conteo:
            conteo[valoracion.valor_confirmado] += 1
    return conteo


def _tag(factor: FactorInforme) -> str:
    """Por qué un factor en contra baja: falta de información («No sé») o incumplimiento («No cumple»)."""
    if CLAVE_FODA.get(factor.clasificacion_foda) not in ("D", "A"):
        return ""
    conteo = _conteo_respuestas(factor)
    if conteo[1] > 0:
        return TAG_INCUMPLIMIENTO
    if conteo[2] > 0:
        return TAG_INFORMACION
    return ""


def _motivo(factor: FactorInforme) -> str:
    conteo = _conteo_respuestas(factor)
    total = sum(conteo.values())
    if total == 0:
        return "Sin respuestas confirmadas."
    inferiores = [(valor, n) for valor, n in conteo.items() if n and valor < 4]
    if len(inferiores) == 1 and inferiores[0][1] == total:
        etiqueta = RESPUESTAS[inferiores[0][0]]
        if total == 1:
            return f"La única respuesta fue «{etiqueta}»."
        return f"Las {total} respuestas fueron «{etiqueta}»."
    partes = ", ".join(f"{n} «{RESPUESTAS[valor]}»" for valor, n in inferiores)
    return f"De {total} respuestas: {partes}."


def _accion(factor: FactorInforme, tag: str) -> str:
    if tag == TAG_INFORMACION:
        return ACCIONES[TAG_INFORMACION]
    return ACCIONES.get(factor.clasificacion_foda, "")


def _ajustada(factor: FactorInforme) -> bool:
    return (factor.importancia_sugerida is not None and factor.importancia_decisor is not None
            and factor.importancia_sugerida != factor.importancia_decisor)


def _clave_orden(factor: FactorInforme):
    return (-(factor.importancia_relativa or 0), -float(factor.ponderacion_media or 0), factor.factor)


def _pm(valor) -> str:
    return _coma(valor) if valor is not None else "—"


def _sintesis(letra, a_favor, en_contra, total_clasificados, n_info, n_importantes=0) -> str:
    """Resumen de la recomendación. `n_importantes`: factores en contra con IR Importante o Fundamental."""
    if total_clasificados == 0:
        return "Esta evaluación no tiene factores relevantes clasificados."
    if en_contra == 0:
        texto = (f"Los {total_clasificados} factores relevantes juegan a favor: "
                 "no se detectaron debilidades ni amenazas.")
    elif letra == "C" and en_contra > a_favor:
        texto = (f"{a_favor} de los {total_clasificados} factores relevantes juegan a favor, pero los "
                 f"{en_contra} restantes los superan: conviene analizar la adopción y considerar posponerla "
                 "hasta resolverlos.")
    elif letra == "C":
        texto = (f"{a_favor} de los {total_clasificados} factores relevantes juegan a favor, pero "
                 + ("1 factor en contra es importante o fundamental" if n_importantes == 1
                    else f"{n_importantes} factores en contra son importantes o fundamentales")
                 + " para su organización: conviene analizar la adopción y considerar posponerla "
                 "hasta resolverlos.")
    else:
        texto = (f"{a_favor} de los {total_clasificados} factores relevantes juegan a favor. "
                 f"{'El restante no los supera' if en_contra == 1 else f'Los {en_contra} restantes no los superan'}"
                 + (" y solo afectan a factores opcionales" if n_importantes == 0 else "")
                 + ", así que la adopción es viable si se atiende primero.")
    if en_contra and n_info:
        if n_info == en_contra:
            texto += (" Además, " + ("ese factor baja" if en_contra == 1 else f"los {en_contra} bajan")
                      + " solo por falta de información («No sé»), no por un incumplimiento comprobado.")
        else:
            texto += (f" Además, {n_info} de esos {en_contra} bajan solo por falta de información "
                      "(«No sé»), no por un incumplimiento comprobado.")
    return texto


def _evidencia_de(factor: FactorInforme):
    """Las valoraciones más bajas del factor, cada una con sus evidencias más relevantes."""
    con_valor = [v for v in factor.valoraciones if v.valor_confirmado is not None]
    ordenadas = sorted(con_valor, key=lambda v: (v.valor_confirmado, v.subfactor))
    elegidas = ordenadas[:MAX_VALORACIONES_POR_FACTOR]
    respuestas = []
    for v in elegidas:
        evidencias = sorted(v.evidencias, key=lambda e: -(float(e.relevancia) if e.relevancia is not None else 0))
        respuestas.append(RespuestaVista(
            subfactor=v.subfactor,
            respuesta=RESPUESTAS.get(v.valor_confirmado, "—"),
            clave={1: "nocumple", 2: "nose", 3: "parcial", 4: "cumple"}.get(v.valor_confirmado, ""),
            justificacion=_justificacion_util(v.justificacion),
            evidencias=[EvidenciaVista(
                documento=e.documento, ubicacion=e.ubicacion, fragmento=_limpio(e.fragmento),
                relevancia=_coma(e.relevancia) if e.relevancia is not None else "") for e in
                evidencias[:MAX_EVIDENCIAS_POR_VALORACION]],
            sin_evidencia=not v.evidencias))
    return respuestas, max(0, len(con_valor) - len(elegidas))


def construir_documento(informe: InformeEvaluacion, emitido) -> DocumentoVista:
    factores = list(informe.factores)
    clasificados = [f for f in factores if f.clasificacion_foda in CLAVE_FODA]
    conteo = {clave: 0 for clave in PLURAL}
    for f in clasificados:
        conteo[CLAVE_FODA[f.clasificacion_foda]] += 1
    a_favor = conteo["F"] + conteo["O"]
    en_contra = conteo["D"] + conteo["A"]
    total_clasificados = len(clasificados)
    letra = letra_de(informe.recomendacion)

    en_contra_ordenados = sorted((f for f in clasificados if CLAVE_FODA[f.clasificacion_foda] in ("D", "A")),
                                 key=lambda f: (-(f.importancia_relativa or 0), float(f.ponderacion_media or 0), f.factor))
    n_info = sum(1 for f in en_contra_ordenados if _tag(f) == TAG_INFORMACION)
    n_importantes = sum(1 for f in en_contra_ordenados if (f.importancia_relativa or 0) >= 3)

    atender = []
    for f in en_contra_ordenados[:MAX_ATENDER]:
        tag = _tag(f)
        clave = CLAVE_FODA[f.clasificacion_foda]
        atender.append(FilaAtender(
            factor=f.factor, dimension=f.dimension, clase=clave, nombre_clase=f.clasificacion_foda,
            ambito=f.alcance_texto, ir=f.importancia_relativa, pm=_pm(f.ponderacion_media), tag=tag,
            etiqueta_tag=ETIQUETA_TAG.get(tag, ""), motivo=_motivo(f), accion=_accion(f, tag),
            ajustada=_ajustada(f)))

    cuadrantes = []
    for clave, etiqueta in CUADRANTES:
        miembros = sorted((f for f in clasificados if CLAVE_FODA[f.clasificacion_foda] == clave), key=_clave_orden)
        cuadrantes.append(Cuadrante(clave=clave, titulo=f"{PLURAL[clave]} · {len(miembros)}", etiqueta=etiqueta,
                                    factores=[(f.factor, f.importancia_relativa, _pm(f.ponderacion_media)) for f in miembros]))

    filas = []
    for f in sorted(factores, key=_clave_orden):
        clave = CLAVE_FODA.get(f.clasificacion_foda, "")
        tag = _tag(f)
        pm = float(f.ponderacion_media) if f.ponderacion_media is not None else 0.0
        filas.append(FilaFactor(
            factor=f.factor, alcance=f.alcance_texto, ir=f.importancia_relativa, pm=_pm(f.ponderacion_media),
            porcentaje=max(0.0, min(100.0, pm / 4 * 100)), clase=clave, nombre_clase=f.clasificacion_foda or "—",
            tag=tag, etiqueta_tag=ETIQUETA_TAG.get(tag, ""), ajustada=_ajustada(f)))

    evidencia = []
    por_nombre = {f.factor: f for f in factores}
    for fila in atender:
        respuestas, omitidas = _evidencia_de(por_nombre[fila.factor])
        evidencia.append(EvidenciaFactor(factor=fila.factor, clase=fila.clase, nombre_clase=fila.nombre_clase,
                                         respuestas=respuestas, omitidas=omitidas))

    proporciones = [(c, PLURAL[c], conteo[c], (conteo[c] / total_clasificados * 100) if total_clasificados else 0)
                    for c in ("F", "O", "D", "A")]

    return DocumentoVista(
        evaluacion_id=informe.evaluacion_id, software=informe.software_completo,
        organizacion=informe.organizacion, decisor=informe.decisor, emitido=emitido,
        version_regla=informe.version_regla, fecha_resultado=informe.fecha_resultado, letra=letra,
        titulo_recomendacion=informe.recomendacion, sintesis=_sintesis(letra, a_favor, en_contra, total_clasificados, n_info, n_importantes),
        a_favor=a_favor, en_contra=en_contra, total=len(factores), proporciones=proporciones,
        atender=atender, atender_extra=max(0, len(en_contra_ordenados) - MAX_ATENDER), cuadrantes=cuadrantes,
        filas=filas, hay_ajustes=any(f.ajustada for f in filas), evidencia=evidencia,
        fuentes=[FuenteVista(d.nombre, d.tipo, d.fecha_carga, _hash_corto(d.hash_sha256)) for d in informe.documentos],
        total_valoraciones=informe.total_valoraciones, total_evidencias=informe.total_evidencias,
        metodo=tuple(t.format(software=informe.software_completo, organizacion=informe.organizacion) for t in TEXTOS_METODO))
