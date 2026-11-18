"""Evita que vuelva el BOM (lo agrega PowerShell 5 al guardar) en archivos de texto del proyecto."""

import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EXTENSIONES = {'.py', '.html', '.css', '.md', '.txt'}
CARPETAS = ('apps', 'config')


class SinBomTests(unittest.TestCase):

    def test_ningun_archivo_de_texto_empieza_con_bom(self):
        archivos = list(RAIZ.glob('*.md')) + [
            p for carpeta in CARPETAS for p in (RAIZ / carpeta).rglob('*')
            if p.is_file() and p.suffix in EXTENSIONES and '__pycache__' not in p.parts]
        con_bom = [str(p.relative_to(RAIZ)) for p in archivos
                   if p.read_bytes()[:3] == b'\xef\xbb\xbf']
        self.assertEqual(con_bom, [], 'Archivos con BOM (guardar como UTF-8 sin BOM): %s' % con_bom)
