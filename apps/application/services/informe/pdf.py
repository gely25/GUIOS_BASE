"""
Generación del informe PDF (HU14) con ReportLab.

Recibe un InformeEvaluacion ya armado y devuelve los bytes del PDF. No accede a la base de datos ni
calcula valores: da formato al contenido que arma `construir_documento()`, el mismo que muestra la
pantalla del Informe. Cuatro partes: resumen, resultados, detalle por factor y respaldo.
"""

import unicodedata
from io import BytesIO
from typing import Optional
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as lienzo
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .documento import DocumentoVista, construir_documento
from .modelos import InformeEvaluacion

INK = colors.HexColor("#292d2f")
GRIS = colors.HexColor("#6e777b")
GRIS_TEXTO = colors.HexColor("#4a4f52")
OCRE = colors.HexColor("#a66e33")
OCRE_CL = colors.HexColor("#f7eddd")
OCRE_BORDE = colors.HexColor("#ecd9bc")
BORDE = colors.HexColor("#e7d9c9")
LINEA = colors.HexColor("#eee2d3")
CABECERA = colors.HexColor("#f8f4ec")
SUAVE = colors.HexColor("#faf7f1")
PISTA = colors.HexColor("#f0ebe3")

COLOR_CLASE = {"F": "#7fbf8f", "O": "#8aa9e6", "D": "#e3c25c", "A": "#e58a84"}
CHIP = {  # fondo, texto
    "F": ("#e6f3e8", "#2e7443"), "O": ("#e3ecfb", "#2d4f9a"),
    "D": ("#fbf0cf", "#8a6414"), "A": ("#fbe3e1", "#9a3a34"), "": ("#eef0f1", "#505a60"),
}
TAG = {"info": ("#eef0f1", "#505a60"), "incumplimiento": ("#f3e6e0", "#8a4a2e")}
RESP = {"nose": ("#e9eef5", "#3d5a80"), "nocumple": ("#f3e6e0", "#8a4a2e"),
        "parcial": ("#f1ece3", "#4a4f52"), "cumple": ("#f1ece3", "#4a4f52"), "": ("#f1ece3", "#4a4f52")}

# La fuente estándar del PDF (Helvetica) solo trae Latin-1: se cambian los signos
# tipográficos comunes por equivalentes y lo demás por «?», para no ver cuadros negros.
_EQUIVALENTES = {
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "–": "-", "—": "-", "…": "...", "≥": ">=", "≤": "<=",
    "•": "-", " ": " ", "​": "",
}


def _latin1(valor) -> str:
    """Texto sin caracteres fuera de Latin-1 (sin escapar el marcado)."""
    if valor is None:
        return ""
    # NFC junta la letra con su tilde (a + ´ -> á); sin esto la tilde suelta salía como «?».
    texto = unicodedata.normalize("NFC", str(valor))
    for origen, destino in _EQUIVALENTES.items():
        texto = texto.replace(origen, destino)
    return texto.encode("latin-1", "replace").decode("latin-1")


def texto_pdf(valor) -> str:
    """Texto seguro para un Paragraph: sin caracteres fuera de Latin-1 y con el marcado escapado."""
    return escape(_latin1(valor))


def _fecha(valor, formato="%d/%m/%Y %H:%M") -> str:
    if not valor:
        return "-"
    return timezone.localtime(valor).strftime(formato)


_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _fecha_larga(valor) -> str:
    if not valor:
        return "-"
    local = timezone.localtime(valor)
    return f"{local.day} {_MESES[local.month - 1]} {local.year}"


# --- Piezas gráficas ------------------------------------------------------------------------

class _Encabezado(Flowable):
    """Título de sección con el número en un círculo."""

    def __init__(self, numero, texto, ancho):
        super().__init__()
        self.numero, self.texto, self.width, self.height = str(numero), _latin1(texto), ancho, 20
        self.keepWithNext = True

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(OCRE_CL)
        c.circle(9, 9, 9, stroke=0, fill=1)
        c.setFillColor(OCRE)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(9, 6, self.numero)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(26, 5, self.texto)


class _Letra(Flowable):
    """Círculo con la letra de la recomendación."""

    def __init__(self, letra, diametro=50):
        super().__init__()
        self.letra, self.d = _latin1(letra) or "-", diametro
        self.width = self.height = diametro

    def wrap(self, *_):
        return self.d, self.d

    def draw(self):
        c = self.canv
        c.setFillColor(OCRE)
        c.circle(self.d / 2, self.d / 2, self.d / 2, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 28)
        c.drawCentredString(self.d / 2, self.d / 2 - 10, self.letra)


class _Barra(Flowable):
    """Barra horizontal con segmentos de color (distribución FODA)."""

    def __init__(self, segmentos, ancho, alto=7):
        super().__init__()
        self.segmentos, self.width, self.height = segmentos, ancho, alto

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        ruta = c.beginPath()
        ruta.roundRect(0, 0, self.width, self.height, self.height / 2)
        c.clipPath(ruta, stroke=0, fill=0)
        c.setFillColor(PISTA)
        c.rect(0, 0, self.width, self.height, stroke=0, fill=1)
        x = 0
        for fraccion, color in self.segmentos:
            ancho = self.width * fraccion
            c.setFillColor(colors.HexColor(color))
            c.rect(x, 0, ancho, self.height, stroke=0, fill=1)
            x += ancho
        c.restoreState()


class _Leyenda(Flowable):
    def __init__(self, items, ancho):
        super().__init__()
        self.items, self.width, self.height = items, ancho, 12

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        x = 0
        for color, cantidad, etiqueta in self.items:
            c.setFillColor(colors.HexColor(color))
            c.circle(x + 3, 4, 3, stroke=0, fill=1)
            x += 10
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString(x, 1.5, str(cantidad))
            x += c.stringWidth(str(cantidad), "Helvetica-Bold", 7.5) + 3
            c.setFillColor(GRIS)
            c.setFont("Helvetica", 7.5)
            c.drawString(x, 1.5, _latin1(etiqueta))
            x += c.stringWidth(_latin1(etiqueta), "Helvetica", 7.5) + 14


class _Pista(Flowable):
    """Barra fina de cumplimiento (PM sobre 4)."""

    def __init__(self, porcentaje, color, ancho=2.3 * cm):
        super().__init__()
        self.fraccion, self.color, self.width, self.height = max(0, min(1, porcentaje / 100)), color, ancho, 4

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(PISTA)
        c.roundRect(0, 0, self.width, self.height, 2, stroke=0, fill=1)
        if self.fraccion > 0:
            c.setFillColor(colors.HexColor(self.color))
            c.roundRect(0, 0, max(self.width * self.fraccion, 3), self.height, 2, stroke=0, fill=1)


class _LienzoNumerado(lienzo.Canvas):
    """Encabezado y pie de cada página, con «Página x de y» (necesita el total antes de dibujar)."""

    titulo_pie = "GUIOS PRO"
    titulo_cab = "INFORME TECNICO"

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
            self._dibujar_marco(total)
            super().showPage()
        super().save()

    def _dibujar_marco(self, total: int):
        ancho, alto = A4
        izq, der = 1.9 * cm, ancho - 1.9 * cm
        self.setFillColor(INK)
        self.setFont("Helvetica-Bold", 10)
        self.drawString(izq, alto - 1.35 * cm, "GUIOS PRO")
        self.setFillColor(GRIS)
        self.setFont("Helvetica", 6.8)
        self.drawRightString(der, alto - 1.35 * cm, self.titulo_cab)
        self.setStrokeColor(INK)
        self.setLineWidth(1.4)
        self.line(izq, alto - 1.6 * cm, der, alto - 1.6 * cm)
        self.setStrokeColor(BORDE)
        self.setLineWidth(0.5)
        self.line(izq, 1.55 * cm, der, 1.55 * cm)
        self.setFillColor(GRIS)
        self.setFont("Helvetica", 7)
        self.drawString(izq, 1.1 * cm, self.titulo_pie)
        self.drawRightString(der, 1.1 * cm, f"Página {self._pageNumber} de {total}")


def _estilos():
    base = getSampleStyleSheet()

    def e(nombre, **kw):
        return ParagraphStyle(nombre, parent=base["Normal"], **kw)

    return {
        "titulo": e("titulo", fontName="Helvetica-Bold", fontSize=21, leading=24, textColor=INK, alignment=TA_LEFT),
        "software": e("software", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=OCRE, spaceAfter=6),
        "meta_k": e("meta_k", fontSize=6.3, leading=8, textColor=GRIS),
        "meta_v": e("meta_v", fontName="Helvetica-Bold", fontSize=8.8, leading=11, textColor=INK),
        "texto": e("texto", fontSize=8.8, leading=12.2, textColor=INK),
        "intro": e("intro", fontSize=8.8, leading=12.2, textColor=GRIS_TEXTO, spaceAfter=8),
        "reco_t": e("reco_t", fontName="Helvetica-Bold", fontSize=13.5, leading=16, textColor=INK, spaceAfter=3),
        "reco_p": e("reco_p", fontSize=9, leading=12.4, textColor=colors.HexColor("#3d4245")),
        "cifra": e("cifra", fontName="Helvetica-Bold", fontSize=19, leading=21, textColor=INK),
        "cifra_t": e("cifra_t", fontSize=7.6, leading=9.5, textColor=GRIS),
        "th": e("th", fontName="Helvetica-Bold", fontSize=7.4, leading=9, textColor=colors.HexColor("#677078")),
        "th_n": e("th_n", fontName="Helvetica-Bold", fontSize=7.4, leading=9, textColor=colors.HexColor("#677078"), alignment=TA_RIGHT),
        "celda": e("celda", fontSize=8.3, leading=10.5, textColor=INK),
        "celda_n": e("celda_n", fontSize=8.3, leading=10.5, textColor=INK, alignment=TA_RIGHT),
        "celda_mono": e("celda_mono", fontName="Courier", fontSize=7.4, leading=9.5, textColor=GRIS_TEXTO),
        "nota": e("nota", fontSize=7.3, leading=9.6, textColor=GRIS, spaceBefore=5),
        "q_t": e("q_t", fontName="Helvetica-Bold", fontSize=9.6, leading=12, textColor=INK),
        "q_e": e("q_e", fontSize=7.4, leading=9.5, textColor=GRIS, spaceAfter=4),
        "q_f": e("q_f", fontSize=8.1, leading=10.2, textColor=INK),
        "q_v": e("q_v", fontSize=7.4, leading=10.2, textColor=GRIS, alignment=TA_RIGHT),
        "leer_t": e("leer_t", fontName="Helvetica-Bold", fontSize=7.9, leading=10, textColor=INK),
        "leer_p": e("leer_p", fontSize=7.6, leading=9.8, textColor=GRIS_TEXTO),
        "fh": e("fh", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=INK, spaceBefore=8, spaceAfter=4, keepWithNext=1),
        "ev_t": e("ev_t", fontName="Helvetica-Bold", fontSize=8.5, leading=10.8, textColor=INK),
        "ev_s": e("ev_s", fontSize=7.3, leading=9.6, textColor=GRIS),
        "ev_j": e("ev_j", fontSize=7.8, leading=10, textColor=GRIS_TEXTO),
        "ev_q": e("ev_q", fontSize=8, leading=10.4, textColor=colors.HexColor("#3d4245")),
        "ev_o": e("ev_o", fontSize=7.1, leading=9.2, textColor=GRIS),
    }


def _chip(texto, fondo_texto) -> str:
    fondo, color = fondo_texto
    return f'<font backColor="{fondo}" color="{color}"><b>&nbsp;{texto_pdf(texto)}&nbsp;</b></font>'


def _etiqueta_pequena(texto, fondo_texto) -> str:
    fondo, color = fondo_texto
    return f'<font size="6.6" backColor="{fondo}" color="{color}"><b>&nbsp;{texto_pdf(texto)}&nbsp;</b></font>'


def _tabla(filas, anchos, *, alinear=None, extra=None) -> Table:
    tabla = Table(filas, colWidths=anchos, repeatRows=1)
    comandos = [
        ("BACKGROUND", (0, 0), (-1, 0), CABECERA),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, LINEA),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDE),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]
    tabla.setStyle(TableStyle(comandos + (extra or [])))
    return tabla


def _caja(contenido, ancho, *, fondo=None, borde=BORDE, radio=8, pad=9, franja=None, alto=None) -> Table:
    """Recuadro de esquinas redondeadas con contenido adentro."""
    tabla = Table([[contenido]], colWidths=[ancho], rowHeights=[alto] if alto else None)
    comandos = [
        ("BOX", (0, 0), (-1, -1), 0.7, borde),
        ("ROUNDEDCORNERS", [radio] * 4),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), pad - 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad - 1),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    if fondo is not None:
        comandos.append(("BACKGROUND", (0, 0), (-1, -1), fondo))
    if franja is not None:
        comandos.append(("LINEABOVE", (0, 0), (-1, 0), 3, colors.HexColor(franja)))
    tabla.setStyle(TableStyle(comandos))
    return tabla


# --- Documento ------------------------------------------------------------------------------

def _pagina_resumen(doc: DocumentoVista, est, p, ancho):
    h = []
    h.append(Paragraph(texto_pdf("Evaluación de adopción FLOSS"), est["titulo"]))
    h.append(Paragraph(texto_pdf(doc.software), est["software"]))
    meta = [[Paragraph(_latin1(k), est["meta_k"]) for k in ("ORGANIZACIÓN", "DECISOR", "EMITIDO", "REGLA DE RECOMENDACIÓN")],
            [Paragraph(texto_pdf(v), est["meta_v"]) for v in
             (doc.organizacion, doc.decisor, _fecha_larga(doc.emitido), f"v{doc.version_regla}")]]
    t = Table(meta, colWidths=[ancho / 4] * 4)
    t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.5, BORDE), ("LINEBELOW", (0, -1), (-1, -1), 0.5, BORDE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, 0), 7),
                           ("BOTTOMPADDING", (0, -1), (-1, -1), 7), ("TOPPADDING", (0, 1), (-1, 1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, 0), 1)]))
    h += [t, Spacer(1, 14)]

    if any((doc.sector, doc.tamano, doc.objetivo_adopcion, doc.proveedor, doc.descripcion_software)):
        contexto = Table([
            [Paragraph(f"<b>Sector</b><br/>{texto_pdf(doc.sector or 'No especificado')}", est["celda"]),
             Paragraph(f"<b>Tamaño de la organización</b><br/>{texto_pdf(doc.tamano or 'No especificado')}", est["celda"])],
            [Paragraph(f"<b>Objetivo de adopción</b><br/>{texto_pdf(doc.objetivo_adopcion or 'No especificado')}", est["celda"]),
             Paragraph(f"<b>Proveedor</b><br/>{texto_pdf(doc.proveedor or 'No especificado')}", est["celda"])],
            [Paragraph(f"<b>Descripción del software</b><br/>{texto_pdf(doc.descripcion_software or 'No especificado')}", est["celda"]), ""],
        ], colWidths=[ancho / 2, ancho / 2])
        contexto.setStyle(TableStyle([
            ("SPAN", (0, 2), (1, 2)), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#faf7f1")),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDE), ("INNERGRID", (0, 0), (-1, -1), 0.3, LINEA),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        h += [Paragraph("Contexto de la evaluación", est["reco_t"]), contexto,
              p("Datos declarados en la ficha inicial como referencia para el decisor; no intervienen en los cálculos ni en la recomendación.", "nota"),
              Spacer(1, 8)]

    h += [_Encabezado(1, "Recomendación", ancho), Spacer(1, 6)]
    reco = Table([[_Letra(doc.letra), [p(doc.titulo_recomendacion, "reco_t"), p(doc.sintesis, "reco_p")]]],
                 colWidths=[1.9 * cm, ancho - 1.9 * cm])
    reco.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), OCRE_CL), ("BOX", (0, 0), (-1, -1), 0.7, OCRE_BORDE),
        ("ROUNDEDCORNERS", [10, 10, 10, 10]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 11), ("BOTTOMPADDING", (0, 0), (-1, -1), 11)]))
    h += [reco, Spacer(1, 8)]

    hueco = 0.25 * cm
    ancho_c = (ancho - 2 * hueco) / 3
    cifras = [(doc.a_favor, "factores a favor (fortalezas y oportunidades)"),
              (doc.en_contra, "factores por atender (debilidades y amenazas)"),
              (doc.total, "factores relevantes analizados")]
    celdas = []
    for i, (n, texto) in enumerate(cifras):
        celdas.append(_caja([p(str(n), "cifra"), p(texto, "cifra_t")], ancho_c, pad=8, alto=1.7 * cm))
        if i < 2:
            celdas.append("")
    fila = Table([celdas], colWidths=[ancho_c, hueco, ancho_c, hueco, ancho_c])
    fila.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    h += [fila, Spacer(1, 9)]

    total = sum(c for _, _, c, _ in doc.proporciones) or 1
    h.append(_Barra([(c / total, COLOR_CLASE[k]) for k, _, c, _ in doc.proporciones if c], ancho))
    h.append(Spacer(1, 4))
    h.append(_Leyenda([(COLOR_CLASE[k], c, plural) for k, plural, c, _ in doc.proporciones], ancho))
    h.append(Spacer(1, 14))

    h += [_Encabezado(2, "Qué atender primero", ancho), Spacer(1, 6)]
    if doc.atender:
        anchos = [3.5 * cm, 2.8 * cm, 2.0 * cm, 1.2 * cm]
        anchos.append(ancho - sum(anchos))
        filas = [[p("Factor", "th"), p("Hallazgo", "th"), p("Importancia", "th_n"), p("PM", "th_n"),
                  p("Por qué y qué hacer", "th")]]
        for f in doc.atender:
            sub = f.dimension + (" · importancia ajustada por el decisor" if f.ajustada else "")
            hallazgo = _chip(f.nombre_clase, CHIP[f.clase])
            if f.etiqueta_tag:
                hallazgo += "<br/>" + _etiqueta_pequena(f.etiqueta_tag, TAG[f.tag])
            filas.append([
                Paragraph(f"<b>{texto_pdf(f.factor)}</b><br/><font size=\"7\" color=\"#6e777b\">{texto_pdf(sub)}</font>", est["celda"]),
                Paragraph(hallazgo, est["celda"]),
                p(f"{f.ir}/4", "celda_n"), p(f.pm, "celda_n"),
                Paragraph(f"{texto_pdf(f.motivo)}<br/><font size=\"7.4\" color=\"#4a4f52\">{texto_pdf(f.accion)}</font>", est["celda"]),
            ])
        h.append(_tabla(filas, anchos))
        extra = f"; {doc.atender_extra} más aparecen en el detalle" if doc.atender_extra else ""
        h.append(p("Se muestran los factores en contra, ordenados por importancia" + extra + ". "
                   "«Falta de información» significa que el factor baja por respuestas «No sé», no porque el "
                   "software incumpla. PM: ponderación media (más alta es mejor).", "nota"))
    else:
        h.append(p("Ningún factor relevante quedó como debilidad o amenaza."))
    return h


def _pagina_resultados(doc: DocumentoVista, est, p, ancho):
    h = [_Encabezado(3, "Resultados: dónde está bien y dónde no", ancho), Spacer(1, 6),
         p("Los factores se agrupan según dependan de su organización (internos) o de terceros (externos), "
           "y según vayan bien o requieran atención.", "intro")]
    hueco = 0.3 * cm
    ancho_q = (ancho - hueco) / 2

    def cuadrante(q):
        filas = [[p(nombre, "q_f"), p(f"IR {ir} · {pm}", "q_v")] for nombre, ir, pm in q.factores] or [[p("Ninguno.", "q_e"), ""]]
        lista = Table(filas, colWidths=[ancho_q - 2 * 9 - 2.6 * cm, 2.6 * cm])
        lista.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.4, LINEA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                   ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        return _caja([p(q.titulo, "q_t"), p(q.etiqueta, "q_e"), lista], ancho_q, pad=9, franja=COLOR_CLASE[q.clave])

    q = {c.clave: cuadrante(c) for c in doc.cuadrantes}
    rejilla = Table([[q["F"], "", q["D"]], ["", "", ""], [q["O"], "", q["A"]]],
                    colWidths=[ancho_q, hueco, ancho_q], rowHeights=[None, hueco, None])
    rejilla.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    h += [rejilla, Spacer(1, 9)]

    ancho_l = (ancho - 2 * hueco) / 3
    leer = [("IR · importancia", "Qué tanto pesa el factor para su organización, de 1 a 4. Los de IR 1 no se incluyen."),
            ("PM · ponderación media", "Promedio de lo que usted confirmó, de 1 a 4. Una respuesta «No sé» baja la PM: "
                                      "cuenta como riesgo hasta comprobarse."),
            ("Regla A / B / C", "A: sin factores en contra. B: los hay, solo en factores opcionales y sin "
                                "superar a los positivos. C: alguno es importante o fundamental, o superan a los positivos.")]
    celdas = []
    for i, (t, texto) in enumerate(leer):
        celdas.append(_caja([p(t, "leer_t"), p(texto, "leer_p")], ancho_l, fondo=SUAVE, borde=SUAVE, radio=7, pad=8))
        if i < 2:
            celdas.append("")
    fila = Table([celdas], colWidths=[ancho_l, hueco, ancho_l, hueco, ancho_l])
    fila.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    h += [fila, Spacer(1, 16), _Encabezado(4, "Alcance y método", ancho), Spacer(1, 6)]
    for parrafo in doc.metodo:
        h += [p(parrafo, "texto"), Spacer(1, 5)]
    return h


def _pagina_detalle(doc: DocumentoVista, est, p, ancho):
    h = [_Encabezado(5, "Resultados por factor", ancho), Spacer(1, 6),
         p(f"Los {doc.total} factores relevantes, de mayor a menor importancia. Dentro de cada nivel, de mayor a "
           "menor puntuación.", "intro")]
    anchos = [5.0 * cm, 2.6 * cm, 0.9 * cm, 1.2 * cm, 2.6 * cm]
    anchos.append(ancho - sum(anchos))
    filas = [[p("Factor", "th"), p("Alcance", "th"), p("IR", "th_n"), p("PM (1 a 4)", "th_n"), "", p("Hallazgo", "th")]]
    for f in doc.filas:
        hallazgo = _chip(f.nombre_clase, CHIP.get(f.clase, CHIP[""]))
        if f.etiqueta_tag:
            hallazgo += "<br/>" + _etiqueta_pequena(f.etiqueta_tag, TAG[f.tag])
        filas.append([p(f.factor + (" *" if f.ajustada else ""), "celda"), p(f.alcance, "celda"),
                      p("-" if f.ir is None else str(f.ir), "celda_n"), p(f.pm, "celda_n"),
                      _Pista(f.porcentaje, COLOR_CLASE.get(f.clase, "#b8b8b8")), Paragraph(hallazgo, est["celda"])])
    if len(filas) == 1:
        filas.append([p("Sin factores relevantes registrados.", "celda")] + [""] * 5)
    h.append(_tabla(filas, anchos, extra=[("SPAN", (3, 0), (4, 0)), ("LEFTPADDING", (4, 1), (4, -1), 8)]))
    if doc.hay_ajustes:
        h.append(p("* El decisor cambió la importancia sugerida de este factor; la importancia relativa final es la "
                   "que se muestra.", "nota"))
    return h


def _pagina_respaldo(doc: DocumentoVista, est, p, ancho):
    h = [_Encabezado(6, "Evidencia que respalda los hallazgos críticos", ancho), Spacer(1, 6),
         p("Por cada factor en contra se muestran las respuestas más bajas y sus evidencias más relevantes. El "
           f"expediente completo ({doc.total_valoraciones} valoraciones y {doc.total_evidencias} evidencias) queda "
           "guardado en el sistema.", "intro")]
    ancho_i = ancho - 2 * 9
    for f in doc.evidencia:
        h.append(Paragraph(f"{texto_pdf(f.factor)}  {_chip(f.nombre_clase, CHIP[f.clase])}", est["fh"]))
        for r in f.respuestas:
            cab = Table([[p(r.subfactor, "ev_t"), Paragraph(_chip(r.respuesta, RESP.get(r.clave, RESP[""])), est["celda_n"])]],
                        colWidths=[ancho_i - 3.4 * cm, 3.4 * cm])
            cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
            sub = "Su respuesta confirmada"
            if r.clave == "nose":
                sub += " · baja la puntuación del factor"
            if r.sin_evidencia:
                sub += " · sin evidencia documental asociada"
            contenido = [cab, Spacer(1, 2), p(sub, "ev_s")]
            if r.justificacion:
                contenido += [Spacer(1, 2), p(r.justificacion, "ev_j")]
            for e in r.evidencias:
                pie = e.documento + (f" · {e.ubicacion}" if e.ubicacion else "") + (
                    f" · relevancia {e.relevancia}" if e.relevancia else "")
                cita = Table([[[Paragraph(f"«{texto_pdf(e.fragmento)}»", est["ev_q"]), p(pie, "ev_s")]]],
                             colWidths=[ancho_i])
                cita.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, -1), 2, OCRE_CL), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                          ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                                          ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
                contenido += [Spacer(1, 4), cita]
            h += [KeepTogether([_caja(contenido, ancho, radio=8, pad=8)]), Spacer(1, 4)]
        if f.omitidas:
            h.append(p(f"Y {f.omitidas} respuesta{'s' if f.omitidas != 1 else ''} más de este factor en el expediente.", "ev_o"))
    if not doc.evidencia:
        h.append(p("No hay factores en contra que respaldar."))
    h += [Spacer(1, 6), _caja(Paragraph(
              "<b>Cómo leer esta sección.</b> " + texto_pdf(
                  "Cuando una valoración no tiene evidencia asociada, el informe lo indica en lugar de omitirla: es una "
                  "señal de que el dato depende solo del criterio del decisor. Las respuestas «No sé» no cuentan como "
                  "incumplimiento: indican que falta comprobar."), est["leer_p"]), ancho, fondo=SUAVE, borde=SUAVE, radio=7, pad=9),
          Spacer(1, 14)]
    anchos = [6.2 * cm, 1.6 * cm, 3.0 * cm]
    anchos.append(ancho - sum(anchos))
    filas = [[p("Documento", "th"), p("Tipo", "th"), p("Cargado", "th"), p("Huella SHA-256", "th")]]
    for d in doc.fuentes:
        filas.append([p(d.nombre, "celda"), p(d.tipo, "celda"), p(_fecha(d.fecha_carga), "celda"), p(d.huella, "celda_mono")])
    if len(filas) == 1:
        filas.append([p("La evaluación no tiene documentos cargados.", "celda"), "", "", ""])
    h += [KeepTogether([_Encabezado(7, "Fuentes documentales", ancho), Spacer(1, 6), _tabla(filas, anchos)]),
          Spacer(1, 14)]
    pares = [("Regla de recomendación", f"v{doc.version_regla}"), ("Resultado generado", _fecha(doc.fecha_resultado)),
             ("Valoraciones incluidas", str(doc.total_valoraciones)), ("Evidencias incluidas", str(doc.total_evidencias)),
             ("Documentos fuente", str(len(doc.fuentes))), ("Informe emitido", _fecha(doc.emitido))]
    filas = []
    for i in range(0, len(pares), 2):
        (k1, v1), (k2, v2) = pares[i], pares[i + 1]
        filas.append([p(k1, "celda"), Paragraph(f"<b>{texto_pdf(v1)}</b>", est["celda_n"]), "",
                      p(k2, "celda"), Paragraph(f"<b>{texto_pdf(v2)}</b>", est["celda_n"])])
    mitad = (ancho - 0.8 * cm) / 2
    t = Table(filas, colWidths=[mitad * 0.6, mitad * 0.4, 0.8 * cm, mitad * 0.6, mitad * 0.4])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (1, -1), 0.4, LINEA), ("LINEBELOW", (3, 0), (4, -1), 0.4, LINEA),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    h.append(KeepTogether([_Encabezado(8, "Trazabilidad", ancho), Spacer(1, 6), t]))
    return h


def generar_pdf(informe: InformeEvaluacion, emitido: Optional[object] = None) -> bytes:
    """Bytes del informe PDF de la evaluación."""
    emitido = emitido or timezone.now()
    doc = construir_documento(informe, emitido)
    est = _estilos()
    p = lambda texto, estilo="texto": Paragraph(texto_pdf(texto), est[estilo])  # noqa: E731

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=1.9 * cm, rightMargin=1.9 * cm, topMargin=2.1 * cm, bottomMargin=2.0 * cm,
        title=f"Informe GUIOS PRO - {informe.software_completo}",
        author="GUIOS PRO", subject="Informe de evaluacion de adopcion FLOSS")
    ancho = A4[0] - 3.8 * cm

    historia = []
    historia += _pagina_resumen(doc, est, p, ancho) + [PageBreak()]
    historia += _pagina_resultados(doc, est, p, ancho) + [PageBreak()]
    historia += _pagina_detalle(doc, est, p, ancho) + [PageBreak()]
    historia += _pagina_respaldo(doc, est, p, ancho)

    class _Lienzo(_LienzoNumerado):
        titulo_pie = _latin1(f"GUIOS PRO · Informe de la evaluación n.º {informe.evaluacion_id}")
        titulo_cab = _latin1(f"INFORME TÉCNICO · EVALUACIÓN N.º {informe.evaluacion_id}")

    documento.build(historia, canvasmaker=_Lienzo)
    return buffer.getvalue()
