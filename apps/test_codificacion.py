"""Evita que vuelva el BOM (lo agrega PowerShell 5 al guardar) en archivos de texto del proyecto."""

import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EXTENSIONES = {'.py', '.html', '.css', '.js', '.md', '.txt', '.json', '.yml', '.yaml', '.toml', '.ini'}
CARPETAS = ('apps', 'config')


class SinBomTests(unittest.TestCase):

    def archivos_de_texto(self):
        return list(RAIZ.glob('*.md')) + [
            p for carpeta in CARPETAS for p in (RAIZ / carpeta).rglob('*')
            if p.is_file() and p.suffix in EXTENSIONES and '__pycache__' not in p.parts]

    def test_ningun_archivo_de_texto_empieza_con_bom(self):
        archivos = self.archivos_de_texto()
        con_bom = [str(p.relative_to(RAIZ)) for p in archivos
                   if p.read_bytes()[:3] == b'\xef\xbb\xbf']
        self.assertEqual(con_bom, [], 'Archivos con BOM (guardar como UTF-8 sin BOM): %s' % con_bom)


    def test_archivos_de_texto_tienen_codificacion_utf8_valida(self):
        invalidos = []
        for archivo in self.archivos_de_texto():
            try:
                archivo.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                invalidos.append(str(archivo.relative_to(RAIZ)))
        self.assertEqual(
            invalidos,
            [],
            'Archivos que no se pueden leer como UTF-8: %s' % invalidos,
        )
