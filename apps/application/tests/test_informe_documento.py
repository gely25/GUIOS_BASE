"""Pruebas del contenido común del informe (HU14): lo que comparten la pantalla y el PDF."""

from datetime import datetime, timezone as zona
from decimal import Decimal
from io import BytesIO

from django.test import SimpleTestCase
from pypdf import PdfReader

from apps.application.services.informe import (
    DocumentoInforme,
    EvidenciaInforme,
    FactorInforme,
    InformeEvaluacion,
    ResumenFoda,
    ValoracionInforme,
    construir_documento,
    generar_pdf,
    texto_pdf,
)
from apps.application.services.informe.documento import MAX_ATENDER, letra_de

AHORA = datetime(2026, 11, 24, 16, 0, tzinfo=zona.utc)


def _factor(nombre, foda, pm, respuestas, *, ir=3, alcance="externo", sugerida=3, decisor=3, evidencias=()):
    valoraciones = []
    for i, valor in enumerate(respuestas):
        valoraciones.append(ValoracionInforme(
            subfactor=f"{nombre}: criterio {i + 1}", valor_ia=None, valor_confirmado=valor,
            estado_validacion="CONFIRMADA", justificacion_decisor="Valoración manual del decisor: Cumple (sin propuesta de IA).",
            evidencias=list(evidencias) if i == 0 else []))
    return FactorInforme(
        dimension="Tecnológica", factor=nombre, alcance=alcance, importancia_sugerida=sugerida,
        importancia_decisor=decisor, importancia_relativa=ir, ponderacion_media=Decimal(pm),
        clasificacion_foda=foda, valoraciones=valoraciones)


def _informe(factores, recomendacion="Es posible adoptar, con matices"):
    cuenta = {"Fortaleza": 0, "Oportunidad": 0, "Debilidad": 0, "Amenaza": 0}
    for f in factores:
        cuenta[f.clasificacion_foda] += 1
    return InformeEvaluacion(
        evaluacion_id=35, software="LibreOffice", software_version="24.8",
        proveedor="The Document Foundation",
        organizacion="Organización Demo", decisor="Decisor Demo", catalogo_version="v1-2021", estado="EN_PROCESO",
        fecha_inicio=AHORA, fecha_fin=None, recomendacion=recomendacion, explicacion=None, version_regla="1.0",
        fecha_resultado=AHORA, sector="Educación", tamano="Mediana",
        objetivo_adopcion="Modernizar gestión documental", descripcion_software="Suite de oficina libre",
        resumen_foda=ResumenFoda(cuenta["Fortaleza"], cuenta["Oportunidad"], cuenta["Debilidad"], cuenta["Amenaza"]),
        factores=factores,
        documentos=[DocumentoInforme("guia.pdf", "PDF", None, "ab" * 32, AHORA)])


class ContenidoDelInformeTests(SimpleTestCase):

    def test_factor_que_baja_por_no_se_se_marca_como_falta_de_informacion(self):
        doc = construir_documento(_informe([_factor("Fiabilidad", "Amenaza", "2.00", [2, 2, 2, 2, 2])]), AHORA)
        fila = doc.atender[0]
        self.assertEqual(fila.tag, "info")
        self.assertEqual(fila.etiqueta_tag, "Falta de información")
        self.assertEqual(fila.motivo, "Las 5 respuestas fueron «No sé».")

    def test_factor_con_no_cumple_se_marca_como_incumplimiento(self):
        doc = construir_documento(_informe([_factor("Formación", "Debilidad", "2.00", [1, 3, 1, 3], alcance="interno")]), AHORA)
        fila = doc.atender[0]
        self.assertEqual(fila.tag, "incumplimiento")
        self.assertEqual(fila.motivo, "De 4 respuestas: 2 «No cumple», 2 «Cumple parcialmente».")
        self.assertIn("organización", fila.accion)

    def test_respuestas_mezcladas_y_respuesta_unica(self):
        doc = construir_documento(_informe([
            _factor("Personalización", "Amenaza", "2.67", [2, 3, 3, 2, 3, 3]),
            _factor("Mantenibilidad", "Amenaza", "2.00", [2], ir=2)]), AHORA)
        por_nombre = {f.factor: f for f in doc.atender}
        self.assertEqual(por_nombre["Personalización"].motivo, "De 6 respuestas: 2 «No sé», 4 «Cumple parcialmente».")
        self.assertEqual(por_nombre["Mantenibilidad"].motivo, "La única respuesta fue «No sé».")

    def test_la_sintesis_aclara_cuando_todo_baja_por_falta_de_informacion(self):
        doc = construir_documento(_informe([
            _factor("Fiabilidad", "Amenaza", "2.00", [2, 2]),
            _factor("Compatibilidad", "Oportunidad", "4.00", [4]),
            _factor("Prueba", "Oportunidad", "3.00", [3])]), AHORA)
        self.assertEqual(doc.letra, "B")
        self.assertIn("2 de los 3 factores relevantes juegan a favor", doc.sintesis)
        self.assertIn("solo por falta de información", doc.sintesis)
        self.assertEqual((doc.a_favor, doc.en_contra, doc.total), (2, 1, 3))

    def test_sin_factores_en_contra_no_hay_nada_que_atender(self):
        doc = construir_documento(_informe([_factor("Compatibilidad", "Oportunidad", "4.00", [4])],
                                           recomendacion="Adoptar el FLOSS seleccionado"), AHORA)
        self.assertEqual(doc.letra, "A")
        self.assertEqual(doc.atender, [])
        self.assertIn("no se detectaron debilidades ni amenazas", doc.sintesis)

    def test_letra_de_la_recomendacion(self):
        self.assertEqual(letra_de("Es posible adoptar, con matices"), "B")
        self.assertEqual(letra_de("Se sugiere analizar la adopción y debería ser pospuesta"), "C")
        self.assertEqual(letra_de("Recomendación B: es posible adoptar."), "B")
        self.assertEqual(letra_de("Otra cosa"), "")

    def test_atender_va_por_importancia_y_tiene_tope(self):
        factores = [_factor(f"F{i:02d}", "Amenaza", "2.00", [2], ir=2) for i in range(MAX_ATENDER + 3)]
        factores.append(_factor("Crítico", "Debilidad", "1.00", [1], ir=4, alcance="interno"))
        doc = construir_documento(_informe(factores), AHORA)
        self.assertEqual(doc.atender[0].factor, "Crítico")
        self.assertEqual(len(doc.atender), MAX_ATENDER)
        self.assertEqual(doc.atender_extra, 4)

    def test_marca_la_importancia_ajustada_por_el_decisor(self):
        doc = construir_documento(_informe([_factor("Mantenibilidad", "Amenaza", "2.00", [2], sugerida=3, decisor=4)]), AHORA)
        self.assertTrue(doc.atender[0].ajustada)
        self.assertTrue(doc.filas[0].ajustada)
        self.assertTrue(doc.hay_ajustes)

    def test_cuadrantes_separan_internos_y_externos(self):
        doc = construir_documento(_informe([
            _factor("Apoyo", "Fortaleza", "4.00", [4], alcance="interno"),
            _factor("Compatibilidad", "Oportunidad", "4.00", [4])]), AHORA)
        titulos = {c.clave: (c.titulo, c.etiqueta, len(c.factores)) for c in doc.cuadrantes}
        self.assertEqual(titulos["F"], ("Fortalezas · 1", "Interno · va bien", 1))
        self.assertEqual(titulos["O"], ("Oportunidades · 1", "Externo · va bien", 1))
        self.assertEqual(titulos["D"][2] + titulos["A"][2], 0)

    def test_evidencia_toma_las_respuestas_mas_bajas_y_las_evidencias_mas_relevantes(self):
        evidencias = [EvidenciaInforme("a.pdf", 1, None, None, "poco relevante", Decimal("0.05")),
                      EvidenciaInforme("b.pdf", 2, None, None, "muy   relevante\ncon espacios", Decimal("0.30")),
                      EvidenciaInforme("c.pdf", 3, None, None, "intermedia", Decimal("0.10"))]
        doc = construir_documento(_informe([_factor("Fiabilidad", "Amenaza", "2.00", [2, 3, 3, 3], evidencias=evidencias)]), AHORA)
        bloque = doc.evidencia[0]
        self.assertEqual(len(bloque.respuestas), 2)
        self.assertEqual(bloque.omitidas, 2)
        primera = bloque.respuestas[0]
        self.assertEqual(primera.respuesta, "No sé")
        self.assertEqual([e.documento for e in primera.evidencias], ["b.pdf", "c.pdf"])
        self.assertEqual(primera.evidencias[0].fragmento, "muy relevante con espacios")
        self.assertEqual(primera.evidencias[0].relevancia, "0,30")

    def test_la_justificacion_automatica_del_decisor_no_se_repite(self):
        doc = construir_documento(_informe([_factor("Fiabilidad", "Amenaza", "2.00", [2])]), AHORA)
        self.assertEqual(doc.evidencia[0].respuestas[0].justificacion, "")
        self.assertTrue(doc.evidencia[0].respuestas[0].sin_evidencia)

    def test_la_huella_se_acorta(self):
        doc = construir_documento(_informe([_factor("Fiabilidad", "Amenaza", "2.00", [2])]), AHORA)
        self.assertEqual(doc.fuentes[0].huella, "abababababab…abababab")

    def test_contexto_de_ficha_se_normaliza_y_recorta(self):
        informe = _informe([_factor("Fiabilidad", "Amenaza", "2.00", [2])])
        informe.objetivo_adopcion = "x" * 240

        doc = construir_documento(informe, AHORA)

        self.assertEqual(len(doc.objetivo_adopcion), 220)
        self.assertTrue(doc.objetivo_adopcion.endswith("…"))


class PdfDelInformeTests(SimpleTestCase):

    def _texto(self, pdf: bytes) -> str:
        return "\n".join(pagina.extract_text() for pagina in PdfReader(BytesIO(pdf)).pages)

    def test_el_pdf_trae_el_mismo_contenido_que_la_pantalla(self):
        informe = _informe([
            _factor("Fiabilidad", "Amenaza", "2.00", [2, 2, 2]),
            _factor("Formación", "Debilidad", "2.00", [1, 3], alcance="interno"),
            _factor("Compatibilidad", "Oportunidad", "4.00", [4])])
        pdf = generar_pdf(informe, AHORA)
        self.assertTrue(pdf.startswith(b"%PDF"))
        texto = self._texto(pdf)
        for esperado in ("Evaluación de adopción FLOSS", "Es posible adoptar, con matices", "Qué atender primero",
                         "Falta de información", "Incumplimiento", "Las 3 respuestas fueron", "Resultados por factor",
                         "Fuentes documentales", "Trazabilidad", "guia.pdf", "Contexto de la evaluación",
                         "Educación", "Mediana", "Modernizar gestión documental", "The Document Foundation",
                         "Suite de oficina libre", "no intervienen en los cálculos"):
            self.assertIn(esperado, texto)
        self.assertNotIn("EN_PROCESO", texto)
        self.assertNotIn("Versión del catálogo", texto)

    def test_el_pdf_tiene_las_cuatro_partes_en_paginas_separadas(self):
        pdf = generar_pdf(_informe([_factor("Compatibilidad", "Oportunidad", "4.00", [4])]), AHORA)
        paginas = [p.extract_text() for p in PdfReader(BytesIO(pdf)).pages]
        self.assertGreaterEqual(len(paginas), 4)
        self.assertIn("Recomendación", paginas[0])
        self.assertIn("dónde está bien", paginas[1])
        self.assertIn("Resultados por factor", paginas[2])
        self.assertIn("Evidencia", paginas[3])

    def test_una_tilde_suelta_se_une_a_su_letra(self):
        self.assertEqual(texto_pdf("fácilmente"), "fácilmente")
