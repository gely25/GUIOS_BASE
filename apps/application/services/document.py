"""
Servicio de Aplicación: DocumentService.

Capa: application. Carga de documentos PDF, DOCX y XLSX, extracción de texto y fragmentos (HU07).
"""

import hashlib
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openpyxl import load_workbook
from pypdf import PdfReader
import docx

from apps.data.models import Documento, Evaluacion, FragmentoDocumento, Usuario


class DocumentService:
    """Carga de documentos PDF, DOCX y XLSX, extracción de texto y fragmentos (HU07)."""

    EXTENSIONES_PERMITIDAS = {'.pdf': 'PDF', '.docx': 'DOCX', '.xlsx': 'XLSX'}
    TAMANO_MAXIMO_BYTES = 20 * 1024 * 1024  # 20 MB

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 120):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=['\n\n', '\n', '. ', ' ', ''],
        )

    @property
    def media_root(self) -> Path:
        root = getattr(settings, 'MEDIA_ROOT', None)
        return Path(root) if root else Path(settings.BASE_DIR) / 'media'

    @staticmethod
    def calcular_sha256(archivo) -> str:
        hasher = hashlib.sha256()
        archivo.seek(0)
        for bloque in iter(lambda: archivo.read(8192), b''):
            hasher.update(bloque)
        archivo.seek(0)
        return hasher.hexdigest()

    def _validar_archivo(self, archivo) -> str:
        if not archivo:
            raise ValidationError('Debes seleccionar un archivo para cargar.')

        nombre = getattr(archivo, 'name', '')
        ext = os.path.splitext(nombre)[1].lower()
        if ext not in self.EXTENSIONES_PERMITIDAS:
            raise ValidationError(
                f'Formato no permitido ({ext or "sin extensión"}). Solo se aceptan PDF, DOCX y XLSX.'
            )

        if getattr(archivo, 'size', 0) <= 0:
            raise ValidationError('El archivo está vacío.')

        if getattr(archivo, 'size', 0) > self.TAMANO_MAXIMO_BYTES:
            raise ValidationError('El archivo supera el tamaño máximo permitido de 20 MB.')

        return self.EXTENSIONES_PERMITIDAS[ext]

    def _extraer_pdf(self, ruta_archivo: Path) -> List[Dict]:
        reader = PdfReader(str(ruta_archivo))
        bloques = []
        for idx, page in enumerate(reader.pages, start=1):
            texto = (page.extract_text() or '').strip()
            if texto:
                bloques.append({
                    'texto': texto,
                    'pagina': idx,
                    'seccion': None,
                    'hoja': None,
                })
        return bloques

    def _extraer_docx(self, ruta_archivo: Path) -> List[Dict]:
        doc = docx.Document(str(ruta_archivo))
        bloques = []
        seccion_actual = 'General'
        buffer_parrafos = []

        for parrafo in doc.paragraphs:
            texto = parrafo.text.strip()
            if not texto:
                continue
            estilo = (parrafo.style.name or '').lower() if parrafo.style else ''
            if estilo.startswith('heading') or estilo.startswith('título') or estilo.startswith('titulo'):
                if buffer_parrafos:
                    bloques.append({
                        'texto': '\n'.join(buffer_parrafos),
                        'pagina': None,
                        'seccion': seccion_actual[:255],
                        'hoja': None,
                    })
                    buffer_parrafos = []
                seccion_actual = texto
            else:
                buffer_parrafos.append(texto)

        if buffer_parrafos:
            bloques.append({
                'texto': '\n'.join(buffer_parrafos),
                'pagina': None,
                'seccion': seccion_actual[:255],
                'hoja': None,
            })

        # Extraer tablas de Word si existen
        for idx_tabla, tabla in enumerate(doc.tables, start=1):
            filas = []
            for row in tabla.rows:
                celdas = [c.text.strip() for c in row.cells if c.text.strip()]
                if celdas:
                    filas.append(' | '.join(celdas))
            if filas:
                bloques.append({
                    'texto': '\n'.join(filas),
                    'pagina': None,
                    'seccion': f'Tabla {idx_tabla}'[:255],
                    'hoja': None,
                })

        return bloques

    def _extraer_xlsx(self, ruta_archivo: Path) -> List[Dict]:
        wb = load_workbook(filename=str(ruta_archivo), data_only=True, read_only=True)
        bloques = []
        try:
            for nombre_hoja in wb.sheetnames:
                ws = wb[nombre_hoja]
                filas_texto = []
                for fila in ws.iter_rows(values_only=True):
                    valores = [str(v).strip() for v in fila if v is not None and str(v).strip() != '']
                    if valores:
                        filas_texto.append(' | '.join(valores))
                if filas_texto:
                    bloques.append({
                        'texto': '\n'.join(filas_texto),
                        'pagina': None,
                        'seccion': None,
                        'hoja': str(nombre_hoja)[:255],
                    })
        finally:
            wb.close()
        return bloques

    def _extraer_bloques(self, tipo: str, ruta_archivo: Path) -> List[Dict]:
        try:
            if tipo == 'PDF':
                return self._extraer_pdf(ruta_archivo)
            if tipo == 'DOCX':
                return self._extraer_docx(ruta_archivo)
            if tipo == 'XLSX':
                return self._extraer_xlsx(ruta_archivo)
        except Exception as exc:
            raise ValidationError(f'No se pudo leer el contenido del archivo {tipo}: {exc}')
        raise ValidationError(f'Tipo de documento no soportado: {tipo}')

    @transaction.atomic
    def procesar_carga(
        self,
        evaluacion: Evaluacion,
        usuario: Usuario,
        archivo,
        version: Optional[str] = None,
    ) -> Documento:
        """Valida, almacena, extrae texto y guarda fragmentos de un documento."""
        tipo = self._validar_archivo(archivo)
        hash_archivo = self.calcular_sha256(archivo)

        if Documento.objects.filter(evaluacion=evaluacion, hash_sha256=hash_archivo).exists():
            raise ValidationError('Este documento ya fue cargado previamente en la misma evaluación (hash duplicado).')

        nombre_original = os.path.basename(archivo.name)[:255]
        nombre_seguro = re.sub(r'[^A-Za-z0-9._-]', '_', nombre_original)
        carpeta_relativa = Path('evaluaciones') / str(evaluacion.evaluacion_id)
        carpeta_absoluta = self.media_root / carpeta_relativa
        carpeta_absoluta.mkdir(parents=True, exist_ok=True)

        nombre_disco = f'{hash_archivo[:12]}_{nombre_seguro}'
        ruta_relativa = (carpeta_relativa / nombre_disco).as_posix()
        ruta_absoluta = self.media_root / ruta_relativa

        archivo.seek(0)
        with open(ruta_absoluta, 'wb') as destino:
            for bloque in archivo.chunks():
                destino.write(bloque)

        try:
            bloques = self._extraer_bloques(tipo, ruta_absoluta)
            if not bloques:
                raise ValidationError(
                    'El documento no contiene texto extraíble (por ejemplo, un PDF escaneado como imagen o un archivo en blanco).'
                )

            documento = Documento.objects.create(
                evaluacion=evaluacion,
                usuario=usuario,
                nombre=nombre_original,
                tipo=tipo,
                ubicacion=ruta_relativa,
                version=(version or '').strip() or None,
                hash_sha256=hash_archivo,
            )

            fragmentos_a_crear = []
            for bloque in bloques:
                sub_textos = self.splitter.split_text(bloque['texto'])
                for texto_frag in sub_textos:
                    limpio = texto_frag.strip()
                    if limpio:
                        fragmentos_a_crear.append(
                            FragmentoDocumento(
                                documento=documento,
                                pagina=bloque['pagina'],
                                seccion=bloque['seccion'],
                                hoja=bloque['hoja'],
                                contenido=limpio,
                            )
                        )

            if not fragmentos_a_crear:
                raise ValidationError('No se pudieron generar fragmentos válidos a partir del documento.')

            FragmentoDocumento.objects.bulk_create(fragmentos_a_crear)
            return documento
        except Exception:
            if ruta_absoluta.exists():
                ruta_absoluta.unlink()
            raise

    @transaction.atomic
    def eliminar_documento(self, documento: Documento) -> None:
        """Elimina el registro, sus fragmentos y el archivo físico en disco."""
        ruta_absoluta = self.media_root / documento.ubicacion
        documento.delete()
        if ruta_absoluta.exists():
            ruta_absoluta.unlink()

    def ruta_absoluta_documento(self, documento: Documento) -> Path:
        return self.media_root / documento.ubicacion