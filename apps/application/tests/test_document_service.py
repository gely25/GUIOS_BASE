import io
from datetime import date

import docx
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from openpyxl import Workbook
import tempfile

from apps.application.services.document import DocumentService
from apps.data.models import (
    CatalogoVersion,
    Documento,
    Evaluacion,
    FragmentoDocumento,
    Organizacion,
    Software,
    Usuario,
)


class DocumentServiceTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organizacion.objects.create(nombre='UNEMI Test')
        cls.decisor = Usuario.objects.create_user(
            correo='jorge.test@guios.test',
            password='Clave-Segura-123',
            nombre='Jorge Test',
            rol=Usuario.DECISOR,
            organizacion=cls.org,
        )
        cls.catalogo = CatalogoVersion.objects.create(version='1.0-test', fecha_creacion=date.today())
        cls.software = Software.objects.create(nombre='LibreOffice Test')
        cls.evaluacion = Evaluacion.objects.create(
            organizacion=cls.org,
            usuario=cls.decisor,
            software=cls.software,
            catalogo=cls.catalogo,
        )

    def _crear_docx(self) -> SimpleUploadedFile:
        doc = docx.Document()
        doc.add_heading('1. Licenciamiento FLOSS', level=1)
        doc.add_paragraph('LibreOffice utiliza licencia MPL 2.0 sin costos de suscripción anual.')
        doc.add_heading('2. Compatibilidad', level=1)
        doc.add_paragraph('Soporta formatos abiertos ODF y exportación directa a PDF.')
        buf = io.BytesIO()
        doc.save(buf)
        return SimpleUploadedFile(
            'politica.docx',
            buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )

    def _crear_xlsx(self) -> SimpleUploadedFile:
        wb = Workbook()
        ws1 = wb.active
        ws1.title = 'Costos'
        ws1.append(['Concepto', 'Valor'])
        ws1.append(['Licencia', 0])
        ws2 = wb.create_sheet('Capacitacion')
        ws2.append(['Area', 'Horas'])
        ws2.append(['TIC', 20])
        buf = io.BytesIO()
        wb.save(buf)
        return SimpleUploadedFile(
            'presupuesto.xlsx',
            buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_procesar_docx_guarda_hash_y_secciones(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with override_settings(MEDIA_ROOT=tmp_dir):
                servicio = DocumentService()
                doc = servicio.procesar_carga(self.evaluacion, self.decisor, self._crear_docx(), version='v1')

                self.assertEqual(doc.tipo, 'DOCX')
                self.assertEqual(len(doc.hash_sha256), 64)
                secciones = list(
                    FragmentoDocumento.objects.filter(documento=doc).values_list('seccion', flat=True)
                )
                self.assertIn('1. Licenciamiento FLOSS', secciones)
                self.assertIn('2. Compatibilidad', secciones)

    def test_procesar_xlsx_guarda_nombres_de_hojas(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with override_settings(MEDIA_ROOT=tmp_dir):
                servicio = DocumentService()
                doc = servicio.procesar_carga(self.evaluacion, self.decisor, self._crear_xlsx())

                hojas = set(FragmentoDocumento.objects.filter(documento=doc).values_list('hoja', flat=True))
                self.assertEqual(hojas, {'Costos', 'Capacitacion'})

    def test_rechaza_extension_invalida_y_duplicados(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with override_settings(MEDIA_ROOT=tmp_dir):
                servicio = DocumentService()
                invalido = SimpleUploadedFile('foto.png', b'1234', content_type='image/png')
                with self.assertRaises(ValidationError):
                    servicio.procesar_carga(self.evaluacion, self.decisor, invalido)

                archivo1 = self._crear_docx()
                servicio.procesar_carga(self.evaluacion, self.decisor, archivo1)
                archivo2 = self._crear_docx()
                with self.assertRaises(ValidationError):
                    servicio.procesar_carga(self.evaluacion, self.decisor, archivo2)