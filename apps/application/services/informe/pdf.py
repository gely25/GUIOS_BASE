"""
Generación del informe PDF (HU14) con ReportLab.

Recibe un InformeEvaluacion ya armado y devuelve los bytes del PDF. No accede a la
base de datos ni calcula valores: solo da formato a lo que ya está guardado.
"""

from io import BytesIO
from typing import List, Optional
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as lienzo
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .modelos import InformeEvaluacion

COLOR_PRIMARIO = colors.HexColor("#1f2937")
COLOR_ACENTO = colors.HexColor("#0f766e")
COLOR_BORDE = colors.HexColor("#cbd5e1")
COLOR_FONDO_SUAVE = colors.HexColor("#f1f5f9")

# La fuente estándar del PDF (Helvetica) solo trae Latin-1: se cambian los signos
# tipográficos comunes por equivalentes y lo demás por «?», para no ver cuadros negros.
_EQUIVALENTES = {
    "\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'",
    "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u2265": ">=", "\u2264": "<=",
    "\u2022": "-", "\u00a0": " ", "\u200b": "",
}


def _latin1(valor) -> str:
    """Texto sin caracteres fuera de Latin-1 (sin escapar el marcado)."""
    if valor is None:
        return ""
    texto = str(valor)
    for origen, destino in _EQUIVALENTES.items():
        texto = texto.replace(origen, destino)
    return texto.encode("latin-1", "replace").decode("latin-1")


def texto_pdf(valor) -> str:
    """Texto seguro para un Paragraph: sin caracteres fuera de Latin-1 y con el marcado escapado."""
    return escape(_latin1(valor))


def _fecha(valor) -> str:
    if not valor:
        return "-"
    return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M")


def _num(valor, decimales: int = 0) -> str:
    if valor is None:
        return "-"
    # Coma decimal, igual que las pantallas del sistema (idioma es).
    return f"{valor:.{decimales}f}".replace(".", ",") if decimales else str(valor)


class _LienzoNumerado(lienzo.Canvas):
    """Pie de página con «Página x de y»: necesita conocer el total antes de dibujar."""

    titulo_pie = "GUIOS PRO"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas_guardadas = []

    def showPage(self):
        self._paginas_guardadas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas_guardadas)
        for estado in self._paginas_guardadas:
            self.__dict__.update(estado)
            self._dibujar_pie(total)
            super().showPage()
        super().save()

    def _dibujar_pie(self, total: int):
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        ancho, _ = A4
        self.drawString(2 * cm, 1.2 * cm, self.titulo_pie)
        self.drawRightString(ancho - 2 * cm, 1.2 * cm, f"Página {self._pageNumber} de {total}")


def _estilos():
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("titulo", parent=base["Title"], fontName="Helvetica-Bold", fontSize=20,
                                 textColor=COLOR_PRIMARIO, alignment=TA_LEFT, spaceAfter=4),
        "subtitulo": ParagraphStyle("subtitulo", parent=base["Normal"], fontSize=10,
                                    textColor=colors.HexColor("#64748b"), spaceAfter=14),
        "h1": ParagraphStyle("h1", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=13,
                             textColor=COLOR_ACENTO, spaceBefore=14, spaceAfter=6, keepWithNext=1),
        "h2": ParagraphStyle("h2", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=10.5,
                             textColor=COLOR_PRIMARIO, spaceBefore=8, spaceAfter=3, keepWithNext=1),
        "texto": ParagraphStyle("texto", parent=base["Normal"], fontSize=9.5, leading=13),
        "celda": ParagraphStyle("celda", parent=base["Normal"], fontSize=8.5, leading=11),
        "celda_negrita": ParagraphStyle("celda_negrita", parent=base["Normal"], fontName="Helvetica-Bold",
                                        fontSize=8.5, leading=11),
        "encabezado": ParagraphStyle("encabezado", parent=base["Normal"], fontName="Helvetica-Bold",
                                     fontSize=8.5, leading=11, textColor=colors.white),
        "nota": ParagraphStyle("nota", parent=base["Normal"], fontSize=8, leading=10.5,
                               textColor=colors.HexColor("#64748b")),
        "evidencia": ParagraphStyle("evidencia", parent=base["Normal"], fontSize=8.5, leading=11,
                                    leftIndent=12, textColor=colors.HexColor("#334155")),
    }


def _tabla(filas, anchos, estilos, *, encabezado: bool = True, extra=None) -> Table:
    tabla = Table(filas, colWidths=anchos, repeatRows=1 if encabezado else 0)
    comandos = [
        ("GRID", (0, 0), (-1, -1), 0.4, COLOR_BORDE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if encabezado:
        comandos += [("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARIO)]
        comandos += [("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_FONDO_SUAVE])]
    comandos += extra or []
    tabla.setStyle(TableStyle(comandos))
    return tabla


def generar_pdf(informe: InformeEvaluacion, emitido: Optional[object] = None) -> bytes:
    """Bytes del informe PDF de la evaluación."""
    est = _estilos()
    p = lambda texto, estilo="texto": Paragraph(texto_pdf(texto), est[estilo])  # noqa: E731
    emitido = emitido or timezone.now()

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Informe GUIOS PRO - {informe.software_completo}",
        author="GUIOS PRO", subject="Informe de evaluacion de adopcion FLOSS")
    ancho_util = A4[0] - 4 * cm
    historia: List = []

    # --- Encabezado ---------------------------------------------------------
    historia.append(p("Informe de evaluación de adopción FLOSS", "titulo"))
    historia.append(p(f"GUIOS PRO · Evaluación n.º {informe.evaluacion_id} · Emitido el {_fecha(emitido)}", "subtitulo"))

    # --- Datos de la evaluación --------------------------------------------
    historia.append(p("1. Datos de la evaluación", "h1"))
    datos = [
        ("Software evaluado", informe.software_completo),
        ("Proveedor", informe.proveedor or "-"),
        ("Organización", informe.organizacion),
        ("Decisor", informe.decisor),
        ("Inicio de la evaluación", _fecha(informe.fecha_inicio)),
        ("Fin de la evaluación", _fecha(informe.fecha_fin)),
        ("Estado", informe.estado),
        ("Versión del catálogo", informe.catalogo_version),
    ]
    filas = [[p(k, "celda_negrita"), p(v, "celda")] for k, v in datos]
    historia.append(_tabla(filas, [5 * cm, ancho_util - 5 * cm], est, encabezado=False,
                           extra=[("BACKGROUND", (0, 0), (0, -1), COLOR_FONDO_SUAVE)]))

    # --- Recomendación y explicación ---------------------------------------
    historia.append(p("2. Recomendación", "h1"))
    caja = Table([[p(informe.recomendacion, "texto")]], colWidths=[ancho_util])
    caja.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, COLOR_ACENTO),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdfa")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    historia.append(caja)
    historia.append(p("Explicación", "h2"))
    if informe.explicacion and informe.explicacion.strip():
        for parrafo in [x for x in informe.explicacion.split("\n") if x.strip()]:
            historia.append(p(parrafo))
            historia.append(Spacer(1, 3))
    else:
        historia.append(p("Esta evaluación no tiene una explicación redactada."))
    historia.append(p(
        "La explicación redacta los resultados en lenguaje natural; no modifica ningún valor calculado "
        "por las reglas del sistema.", "nota"))

    # --- Resumen FODA -------------------------------------------------------
    historia.append(p("3. Resumen FODA de los factores relevantes", "h1"))
    cabecera = [p(t, "encabezado") for t in ("Fortalezas", "Oportunidades", "Debilidades", "Amenazas")]
    cantidades = [p(str(cantidad), "celda_negrita") for _nombre, cantidad in informe.resumen_foda.filas]
    historia.append(_tabla([cabecera, cantidades], [ancho_util / 4] * 4, est))
    if informe.resumen_foda.sin_clasificar:
        historia.append(Spacer(1, 3))
        historia.append(p(f"Factores sin clasificación FODA: {informe.resumen_foda.sin_clasificar}.", "nota"))

    # --- Factores relevantes -----------------------------------------------
    historia.append(p("4. Factores relevantes y valores obtenidos", "h1"))
    encabezados = ["Dimensión", "Factor", "Alcance", "IS", "ID", "IR", "PM", "FODA"]
    filas = [[p(t, "encabezado") for t in encabezados]]
    for f in informe.factores:
        filas.append([
            p(f.dimension, "celda"), p(f.factor, "celda_negrita"), p(f.alcance_texto, "celda"),
            p(_num(f.importancia_sugerida), "celda"), p(_num(f.importancia_decisor), "celda"),
            p(_num(f.importancia_relativa), "celda"), p(_num(f.ponderacion_media, 2), "celda"),
            p(f.clasificacion_foda or "-", "celda"),
        ])
    if len(filas) == 1:
        filas.append([p("Sin factores relevantes registrados.", "celda")] + [""] * 7)
    anchos = [2.6 * cm, 4.0 * cm, 2.3 * cm, 1.0 * cm, 1.0 * cm, 1.0 * cm, 1.3 * cm]
    anchos.append(ancho_util - sum(anchos))
    historia.append(_tabla(filas, anchos, est))
    historia.append(Spacer(1, 3))
    historia.append(p(
        "IS: importancia sugerida · ID: importancia del decisor · IR: importancia relativa · "
        "PM: ponderación media. Escala de 1 a 4.", "nota"))

    # --- Valoraciones y evidencias -----------------------------------------
    historia.append(p("5. Valoraciones y evidencias", "h1"))
    hay_valoraciones = False
    for f in informe.factores:
        if not f.valoraciones:
            continue
        hay_valoraciones = True
        bloque = [p(f"{f.factor} ({f.dimension})", "h2")]
        filas = [[p(t, "encabezado") for t in ("Subfactor", "IA", "Confirmado", "Estado")]]
        for v in f.valoraciones:
            filas.append([p(v.subfactor, "celda"), p(_num(v.valor_ia), "celda"),
                          p(_num(v.valor_confirmado), "celda"), p(v.estado_validacion, "celda")])
        bloque.append(_tabla(filas, [ancho_util - 7.5 * cm, 1.3 * cm, 2.2 * cm, 4.0 * cm], est))
        historia.append(KeepTogether(bloque[:2]))
        for v in f.valoraciones:
            if v.justificacion:
                historia.append(p(f"Justificación de «{v.subfactor[:70]}»: {v.justificacion}", "nota"))
            for ev in v.evidencias:
                ubic = f" ({ev.ubicacion})" if ev.ubicacion else ""
                rel = f" - relevancia {_num(ev.relevancia, 2)}" if ev.relevancia is not None else ""
                historia.append(p(f"Evidencia: {ev.documento}{ubic}{rel}. «{ev.fragmento}»", "evidencia"))
    if not hay_valoraciones:
        historia.append(p("No hay valoraciones registradas para los factores relevantes."))

    # --- Fuentes documentales ----------------------------------------------
    historia.append(p("6. Fuentes documentales", "h1"))
    if informe.documentos:
        filas = [[p(t, "encabezado") for t in ("Documento", "Tipo", "Versión", "Cargado", "Hash SHA-256")]]
        for d in informe.documentos:
            filas.append([p(d.nombre, "celda"), p(d.tipo, "celda"), p(d.version or "-", "celda"),
                          p(_fecha(d.fecha_carga), "celda"), p(d.hash_sha256 or "-", "celda")])
        historia.append(_tabla(filas, [4.2 * cm, 1.6 * cm, 1.8 * cm, 2.9 * cm, ancho_util - 10.5 * cm], est))
    else:
        historia.append(p("La evaluación no tiene documentos cargados."))

    # --- Trazabilidad -------------------------------------------------------
    historia.append(p("7. Trazabilidad", "h1"))
    traza = [
        ("Regla de recomendación (versión)", informe.version_regla),
        ("Resultado generado el", _fecha(informe.fecha_resultado)),
        ("Versión del catálogo", informe.catalogo_version),
        ("Valoraciones incluidas", str(informe.total_valoraciones)),
        ("Evidencias incluidas", str(informe.total_evidencias)),
        ("Informe emitido el", _fecha(emitido)),
    ]
    filas = [[p(k, "celda_negrita"), p(v, "celda")] for k, v in traza]
    historia.append(_tabla(filas, [6 * cm, ancho_util - 6 * cm], est, encabezado=False,
                           extra=[("BACKGROUND", (0, 0), (0, -1), COLOR_FONDO_SUAVE)]))

    class _Lienzo(_LienzoNumerado):
        titulo_pie = _latin1(f"GUIOS PRO · Informe de la evaluación n.º {informe.evaluacion_id}")

    documento.build(historia, canvasmaker=_Lienzo)
    return buffer.getvalue()
