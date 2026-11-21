import io
import tempfile
from datetime import date

import docx
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.application.services.document import DocumentService
from apps.application.services.retrieval import RetrievalService
from apps.data.models import (
    CatalogoVersion,
    Dimension,
    Documento,
    Evaluacion,
    Factor,
    FragmentoDocumento,
    Organizacion,
    Software,
    Subfactor,
    Usuario,
)
from apps.data.models.documentos import DIMENSIONES_EMBEDDING


class RetrievalServiceTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organizacion.objects.create(nombre='UNEMI Test HU08')
        cls.decisor = Usuario.objects.create_user(
            correo='jorge.hu08@guios.test',
            password='Clave-Segura-123',
            nombre='Jorge Prueba',
            rol=Usuario.DECISOR,
            organizacion=cls.org,
        )
        cls.catalogo = CatalogoVersion.objects.create(
            version='1.0-hu08',
            fecha_creacion=date.today(),
        )
        cls.software = Software.objects.create(nombre='LibreOffice Calc')
        cls.evaluacion_a = Evaluacion.objects.create(
            organizacion=cls.org,
            usuario=cls.decisor,
            software=cls.software,
            catalogo=cls.catalogo,
        )
        cls.evaluacion_b = Evaluacion.objects.create(
            organizacion=cls.org,
            usuario=cls.decisor,
            software=cls.software,
            catalogo=cls.catalogo,
        )

    def setUp(self):
        self.retrieval = RetrievalService()

    def test_embedding_tiene_1536_dimensiones_y_norma_unitaria(self):
        vec_1 = self.retrieval.generar_embedding('Licencia pública general GNU y código abierto')
        vec_2 = self.retrieval.generar_embedding('Licencia pública general GNU y código abierto')

        self.assertEqual(len(vec_1), DIMENSIONES_EMBEDDING)
        self.assertEqual(vec_1, vec_2)
        norma_cuadrada = sum(x * x for x in vec_1)
        self.assertAlmostEqual(norma_cuadrada, 1.0, places=5)

    def test_carga_documental_indexa_embeddings_automaticamente(self):
        doc_mem = docx.Document()
        doc_mem.add_heading('Seguridad y Autenticación', level=1)
        doc_mem.add_paragraph(
            'El sistema soporta autenticación multifactor, cifrado TLS 1.3 y control de acceso basado en roles.'
        )
        buffer = io.BytesIO()
        doc_mem.save(buffer)
        archivo = SimpleUploadedFile(
            'seguridad.docx',
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                documento = DocumentService().procesar_carga(
                    evaluacion=self.evaluacion_a,
                    usuario=self.decisor,
                    archivo=archivo,
                )

        fragmentos = list(documento.fragmentos.all())
        self.assertGreaterEqual(len(fragmentos), 1)
        for frag in fragmentos:
            self.assertIsNotNone(frag.embedding)
            self.assertEqual(len(frag.embedding), DIMENSIONES_EMBEDDING)

    def test_buscar_evidencia_ordena_por_similitud_semantica_en_pgvector(self):
        doc = Documento.objects.create(
            evaluacion=self.evaluacion_a,
            usuario=self.decisor,
            nombre='ficha_tecnica_libreoffice.pdf',
            tipo='PDF',
            ubicacion='evaluaciones/1/ficha.pdf',
        )
        frag_licencia = FragmentoDocumento.objects.create(
            documento=doc,
            pagina=1,
            contenido='El software se distribuye bajo licencia libre MPLv2 sin costo de regalías.',
        )
        frag_hardware = FragmentoDocumento.objects.create(
            documento=doc,
            pagina=4,
            contenido='Requisitos de hardware: mínimo 4 GB de memoria RAM, procesador dual core y 2 GB de disco.',
        )
        frag_soporte = FragmentoDocumento.objects.create(
            documento=doc,
            pagina=7,
            contenido='La comunidad internacional publica actualizaciones de seguridad trimestrales.',
        )
        self.retrieval.indexar_fragmentos([frag_licencia, frag_hardware, frag_soporte], guardar=True)

        resultados = self.retrieval.buscar_evidencia(
            evaluacion_id=self.evaluacion_a.evaluacion_id,
            consulta='cuanta memoria RAM y procesador necesita el sistema',
            top_k=2,
        )

        self.assertEqual(len(resultados), 2)
        self.assertEqual(resultados[0]['fragmento_id'], frag_hardware.fragmento_id)
        self.assertEqual(resultados[0]['ubicacion_referencia'], 'Página 4')
        self.assertEqual(resultados[0]['documento_nombre'], 'ficha_tecnica_libreoffice.pdf')
        self.assertGreater(resultados[0]['similitud'], resultados[1]['similitud'])

    def test_buscar_evidencia_aisla_fragmentos_por_evaluacion(self):
        doc_b = Documento.objects.create(
            evaluacion=self.evaluacion_b,
            usuario=self.decisor,
            nombre='otro_proyecto.pdf',
            tipo='PDF',
            ubicacion='evaluaciones/2/otro.pdf',
        )
        frag_b = FragmentoDocumento.objects.create(
            documento=doc_b,
            pagina=2,
            contenido='Presupuesto anual aprobado de 50000 dólares para licenciamiento empresarial.',
        )
        self.retrieval.indexar_fragmentos([frag_b], guardar=True)

        resultados_a = self.retrieval.buscar_evidencia(
            evaluacion_id=self.evaluacion_a.evaluacion_id,
            consulta='presupuesto anual licenciamiento',
        )
        self.assertEqual(resultados_a, [])

    def test_buscar_evidencia_consulta_vacia_lanza_error(self):
        with self.assertRaises(ValidationError):
            self.retrieval.buscar_evidencia(
                evaluacion_id=self.evaluacion_a.evaluacion_id,
                consulta='   ',
            )

    def test_comando_generar_embeddings_indexa_pendientes(self):
        doc = Documento.objects.create(
            evaluacion=self.evaluacion_a,
            usuario=self.decisor,
            nombre='manual_legacy.pdf',
            tipo='PDF',
            ubicacion='evaluaciones/1/legacy.pdf',
        )
        FragmentoDocumento.objects.create(
            documento=doc,
            pagina=1,
            contenido='Compatibilidad total con formatos abiertos ODF, DOCX y XLSX.',
            embedding=None,
        )

        call_command('generar_embeddings', evaluacion_id=self.evaluacion_a.evaluacion_id)

        estado = self.retrieval.estado_indexacion(self.evaluacion_a.evaluacion_id)
        self.assertEqual(estado['pendientes'], 0)
        self.assertEqual(estado['indexados'], 1)

    def test_buscar_por_subfactor_recupera_evidencia_de_evaluacion_activa(self):
     dim = Dimension.objects.create(nombre='Económica')
     factor = Factor.objects.create(
         dimension=dim,
         nombre='Costo de licenciamiento',
         alcance=Factor.EXTERNO,
         activo=True,
     )
     subfactor_costo = Subfactor.objects.create(
         factor=factor,
         descripcion='Costo anual de licencia por equipo y restricciones de auditoría',
         activo=True,
     )

     doc_a = Documento.objects.create(
         evaluacion=self.evaluacion_a,
         usuario=self.decisor,
         nombre='costos_libreoffice.xlsx',
         tipo='XLSX',
         ubicacion='evaluaciones/1/costos.xlsx',
     )
     frag_costo = FragmentoDocumento.objects.create(
         documento=doc_a,
         hoja='Licencias',
         contenido='Costo de licencia anual por equipo: 0 USD bajo licencia libre sin auditoría.',
     )
     frag_otro = FragmentoDocumento.objects.create(
         documento=doc_a,
         hoja='Capacitación',
         contenido='El departamento de TIC impartirá 16 horas de capacitación interna.',
     )
     self.retrieval.indexar_fragmentos([frag_costo, frag_otro], guardar=True)

     # Fragmento en otra evaluación que NO debe mezclarse
     doc_b = Documento.objects.create(
         evaluacion=self.evaluacion_b,
         usuario=self.decisor,
         nombre='costos_otra_eval.xlsx',
         tipo='XLSX',
         ubicacion='evaluaciones/2/costos_b.xlsx',
     )
     frag_b = FragmentoDocumento.objects.create(
         documento=doc_b,
         hoja='Licencias',
         contenido='Costo de licencia anual por equipo: 500 USD.',
     )
     self.retrieval.indexar_fragmentos([frag_b], guardar=True)

     resultados = self.retrieval.buscar_por_subfactor(
         evaluacion_id=self.evaluacion_a.evaluacion_id,
         subfactor_id=subfactor_costo.subfactor_id,
         top_k=2,
     )

     self.assertEqual(len(resultados), 2)
     self.assertEqual(resultados[0]['fragmento_id'], frag_costo.fragmento_id)
     self.assertEqual(resultados[0]['subfactor_id'], subfactor_costo.subfactor_id)
     self.assertTrue(all(r['documento_id'] == doc_a.documento_id for r in resultados))

    def test_buscar_por_subfactor_inexistente_lanza_error(self):
        with self.assertRaises(ValidationError):
            self.retrieval.buscar_por_subfactor(
                evaluacion_id=self.evaluacion_a.evaluacion_id,
                subfactor_id=999999,
            )