"""Pruebas del informe de una evaluación (HU14): datos, permisos y PDF."""

from django.test import SimpleTestCase, TestCase

from apps.application.services.informe import InformeNoDisponible, texto_pdf
from apps.application.services.report import ReportService

from .utilidades_informe import crear_decisor, crear_evaluacion


class CargarInformeTests(TestCase):
    def setUp(self):
        self.decisor = crear_decisor()
        self.evaluacion = crear_evaluacion(self.decisor)
        self.servicio = ReportService()

    def test_informe_trae_datos_de_la_evaluacion(self):
        informe = self.servicio.informe(self.decisor)
        self.assertEqual(informe.evaluacion_id, self.evaluacion.evaluacion_id)
        self.assertEqual(informe.software_completo, "LibreOffice 24.8")
        self.assertEqual(informe.organizacion, "Universidad de Prueba")
        self.assertEqual(informe.decisor, "Dario Decisor")
        self.assertEqual(informe.catalogo_version, "2021")
        self.assertEqual(informe.version_regla, "1.0")
        self.assertIn("Recomendación B", informe.recomendacion)

    def test_solo_incluye_factores_relevantes(self):
        informe = self.servicio.informe(self.decisor)
        self.assertEqual([f.factor for f in informe.factores], ["Compatibilidad", "Formación"])

    def test_los_valores_se_presentan_tal_como_estan_guardados(self):
        compat = self.servicio.informe(self.decisor).factores[0]
        self.assertEqual((compat.importancia_sugerida, compat.importancia_decisor, compat.importancia_relativa),
                         (3, 4, 4))
        self.assertEqual(str(compat.ponderacion_media), "3.50")
        self.assertEqual(compat.clasificacion_foda, "Oportunidad")

    def test_resumen_foda_cuenta_solo_factores_relevantes(self):
        resumen = self.servicio.informe(self.decisor).resumen_foda
        self.assertEqual((resumen.oportunidades, resumen.debilidades, resumen.amenazas, resumen.fortalezas),
                         (1, 1, 0, 0))

    def test_valoracion_con_evidencia_y_justificacion_del_decisor(self):
        valoracion = self.servicio.informe(self.decisor).factores[0].valoraciones[0]
        self.assertEqual((valoracion.valor_ia, valoracion.valor_confirmado), (3, 4))
        self.assertEqual(valoracion.justificacion, "Lo comprobé en la prueba piloto.")
        evidencia = valoracion.evidencias[0]
        self.assertEqual(evidencia.documento, "guia.pdf")
        self.assertEqual(evidencia.ubicacion, "p. 7, sección Formatos")
        self.assertEqual(evidencia.fragmento, "Soporta ODF y formatos de Microsoft Office.")

    def test_incluye_los_documentos_fuente_con_su_hash(self):
        documentos = self.servicio.informe(self.decisor).documentos
        self.assertEqual([(d.nombre, d.hash_sha256) for d in documentos], [("guia.pdf", "a" * 64)])

    def test_otro_decisor_no_puede_ver_la_evaluacion(self):
        otro = crear_decisor("otro@guios.test", "Otra Persona")
        with self.assertRaises(InformeNoDisponible):
            self.servicio.informe(otro, self.evaluacion.evaluacion_id)

    def test_decisor_sin_evaluaciones_no_tiene_informe(self):
        sin_nada = crear_decisor("sinnada@guios.test", "Sin Nada")
        with self.assertRaises(InformeNoDisponible):
            self.servicio.informe(sin_nada)

    def test_evaluacion_sin_resultado_no_tiene_informe(self):
        from apps.data.models import ResultadoEvaluacion
        ResultadoEvaluacion.objects.all().delete()
        with self.assertRaises(InformeNoDisponible):
            self.servicio.informe(self.decisor)

    def test_sin_id_toma_la_evaluacion_con_resultado_mas_reciente(self):
        self.assertEqual(self.servicio.informe(self.decisor).evaluacion_id, self.evaluacion.evaluacion_id)

    def test_nombre_de_archivo(self):
        informe = self.servicio.informe(self.decisor)
        self.assertEqual(ReportService.nombre_archivo(informe), f"informe-guios-libreoffice-{informe.evaluacion_id}.pdf")


class GenerarPdfTests(TestCase):
    def setUp(self):
        self.decisor = crear_decisor()
        crear_evaluacion(self.decisor)
        self.servicio = ReportService()

    def test_genera_un_pdf_valido(self):
        pdf = self.servicio.generar_pdf(self.servicio.informe(self.decisor))
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"%%EOF", pdf[-32:])
        self.assertGreater(len(pdf), 2000)

    def test_genera_pdf_sin_explicacion_ni_documentos(self):
        from apps.data.models import Documento, Evidencia, ResultadoEvaluacion
        Evidencia.objects.all().delete()   # la evidencia protege al fragmento: se borra primero
        Documento.objects.all().delete()
        ResultadoEvaluacion.objects.update(explicacion=None)
        pdf = self.servicio.generar_pdf(self.servicio.informe(self.decisor))
        self.assertTrue(pdf.startswith(b"%PDF"))


class TextoPdfTests(SimpleTestCase):
    def test_escapa_el_marcado(self):
        self.assertEqual(texto_pdf("a < b & <b>c</b>"), "a &lt; b &amp; &lt;b&gt;c&lt;/b&gt;")

    def test_cambia_signos_tipograficos_por_equivalentes(self):
        self.assertEqual(texto_pdf("\u201chola\u201d \u2013 PM \u2265 3\u2026"), '"hola" - PM &gt;= 3...')

    def test_conserva_acentos_y_enie(self):
        self.assertEqual(texto_pdf("Formación y diseño"), "Formación y diseño")

    def test_caracteres_fuera_de_latin1_no_rompen(self):
        self.assertEqual(texto_pdf("日本"), "??")

    def test_none_es_vacio(self):
        self.assertEqual(texto_pdf(None), "")
