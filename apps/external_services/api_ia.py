"""Proveedor HTTPS de IA generativa con protocolo Chat Completions compatible.

La IA recibe únicamente el contexto proporcionado por los servicios HU09/HU10.
La validación, autorización y persistencia siguen dentro de la aplicación.
"""
import json
import math
from copy import deepcopy
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from apps.external_services.ai_contracts import (
    ESQUEMA_BIBLIOGRAFIA, ESQUEMA_PREGUNTAS, ESQUEMA_SUFICIENCIA, ESQUEMA_VALORACION,
    INSTRUCCION_BIBLIOGRAFIA, INSTRUCCION_PREGUNTAS, INSTRUCCION_SUFICIENCIA,
    INSTRUCCION_VALORACION,
)
from apps.external_services.ai_errors import AnalisisNoDisponible

LIMITE_ENTRADA = 16000
LIMITE_RESPUESTA = 65536


def _cumple_esquema(valor, esquema):
    tipo = esquema.get('type')
    if tipo == 'object':
        if not isinstance(valor, dict):
            return False
        propiedades = esquema.get('properties', {})
        if any(campo not in valor for campo in esquema.get('required', [])):
            return False
        if esquema.get('additionalProperties') is False and set(valor) - set(propiedades):
            return False
        return all(_cumple_esquema(valor[campo], subesquema)
                   for campo, subesquema in propiedades.items() if campo in valor)
    if tipo == 'array':
        if not isinstance(valor, list):
            return False
        if len(valor) < esquema.get('minItems', 0) or len(valor) > esquema.get('maxItems', math.inf):
            return False
        return all(_cumple_esquema(item, esquema.get('items', {})) for item in valor)
    if tipo == 'string':
        if not isinstance(valor, str):
            return False
        if len(valor) < esquema.get('minLength', 0) or len(valor) > esquema.get('maxLength', math.inf):
            return False
    elif tipo == 'integer':
        if type(valor) is not int:
            return False
    elif tipo == 'number':
        if (isinstance(valor, bool) or not isinstance(valor, (int, float)) or
                isinstance(valor, float) and not math.isfinite(valor)):
            return False
    if 'enum' in esquema and valor not in esquema['enum']:
        return False
    if tipo in ('integer', 'number'):
        if valor < esquema.get('minimum', -math.inf) or valor > esquema.get('maximum', math.inf):
            return False
    return True


class APIJSON:
    """Cliente sin SDK ni credenciales fijas; no acepta URLs de los documentos."""

    def __init__(self, clave, modelo, base_url, timeout=25):
        self.clave = (clave or '').strip()
        self.modelo = (modelo or '').strip()
        self.base_url = (base_url or '').rstrip('/')
        self.timeout = min(max(int(timeout), 5), 90)
        url = urlsplit(self.base_url)
        if not self.clave or not self.modelo:
            raise AnalisisNoDisponible('Configure la clave y el modelo de la API de IA.')
        if (url.scheme != 'https' or not url.hostname or url.username or url.password or
                url.query or url.fragment or url.path.endswith('/chat/completions')):
            raise AnalisisNoDisponible('La URL base de IA debe ser HTTPS y terminar antes de /chat/completions.')

    def consultar(self, entrada, esquema, instruccion):
        datos = json.dumps(entrada, ensure_ascii=False)
        if len(datos.encode('utf-8')) > LIMITE_ENTRADA:
            raise AnalisisNoDisponible('El contexto supera el límite del piloto. Reduzca los fragmentos vinculados.')
        # El modo json_object exige JSON sintácticamente válido, pero no garantiza
        # sus campos. Especificamos el esquema esperado antes de
        # que los servicios apliquen su validación estricta, sin debilitarla.
        instrucciones = instruccion + ' Responde exclusivamente JSON válido.'
        if isinstance(esquema, dict) and esquema.get('type') == 'object':
            requeridas = esquema.get('required', [])
            instrucciones += (
                '\nCONTRATO OBLIGATORIO DE RESPUESTA: devuelve un único objeto JSON '
                'que contenga exactamente estas claves: '
                + ', '.join(requeridas) + '. '
                'No añadas claves ni comentarios. Respeta los tipos y límites de este esquema: '
                + json.dumps(esquema, ensure_ascii=False, separators=(',', ':'))
            )
        carga = {
            'model': self.modelo,
            'messages': [
                {'role': 'system', 'content': instrucciones},
                {'role': 'user', 'content': datos},
            ],
            'stream': False,
            'temperature': 0,
            'response_format': {'type': 'json_object'},
        }
        peticion = Request(
            self.base_url + '/chat/completions',
            data=json.dumps(carga, ensure_ascii=False).encode('utf-8'),
            # User-Agent propio: algunos proveedores (p. ej. Groq) bloquean el de urllib con HTTP 403.
            headers={'Authorization': 'Bearer ' + self.clave, 'Content-Type': 'application/json',
                     'Accept': 'application/json', 'User-Agent': 'GUIOS-PRO/1.0'},
            method='POST',
        )
        try:
            with urlopen(peticion, timeout=self.timeout) as respuesta:
                contenido = respuesta.read(LIMITE_RESPUESTA + 1)
            if len(contenido) > LIMITE_RESPUESTA:
                raise AnalisisNoDisponible('La respuesta de IA supera el límite permitido.')
            paquete = json.loads(contenido)
            respuesta = paquete['choices'][0]
            if respuesta.get('finish_reason') == 'length':
                raise AnalisisNoDisponible('La IA no terminó la respuesta. Repita el análisis.')
            texto = respuesta['message']['content']
            if not isinstance(texto, str):
                raise ValueError('Contenido inválido')
            texto = texto.strip()
            if texto.startswith('```'):
                lineas = texto.splitlines()
                texto = '\n'.join(lineas[1:-1]).strip()
            resultado = json.loads(texto)
            if not _cumple_esquema(resultado, esquema):
                raise AnalisisNoDisponible('La IA devolvió una respuesta fuera del esquema esperado.')
            return resultado
        except HTTPError as exc:
            # No mostrar cuerpos de respuesta ni encabezados de un proveedor externo.
            if exc.code in (401, 403):
                detalle = 'Credenciales de API rechazadas.'
            elif exc.code == 429:
                detalle = 'La API de IA alcanzó su límite de solicitudes.'
            else:
                detalle = f'La API de IA devolvió el estado HTTP {exc.code}.'
            raise AnalisisNoDisponible(detalle) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise AnalisisNoDisponible('No se pudo contactar con la API de IA. Continúe en modo manual.') from exc
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise AnalisisNoDisponible('La API devolvió datos inválidos. No se guardó la propuesta.') from exc


class APIPreguntas:
    def __init__(self, cliente):
        self.cliente = cliente

    def __call__(self, entrada):
        cupo = entrada.get('max_preguntas', 3)
        if type(cupo) is not int or not 1 <= cupo <= 3:
            raise AnalisisNoDisponible('Cupo de preguntas inválido.')
        esquema = deepcopy(ESQUEMA_PREGUNTAS)
        esquema['properties']['preguntas']['maxItems'] = cupo
        resultado = self.cliente.consultar(entrada, esquema, INSTRUCCION_PREGUNTAS)
        if set(resultado) != {'preguntas'} or not isinstance(resultado['preguntas'], list):
            raise AnalisisNoDisponible('La API devolvió un formato inválido de preguntas.')
        preguntas = resultado['preguntas']
        if len(preguntas) > cupo or any(not isinstance(p, str) or not p.strip() or len(p.strip()) > 1000
                                      or not p.strip().endswith('?') for p in preguntas):
            raise AnalisisNoDisponible('La API devolvió preguntas inválidas.')
        return preguntas


class APISuficiencia:
    def __init__(self, cliente):
        self.cliente = cliente

    def __call__(self, entrada):
        esquema = deepcopy(ESQUEMA_SUFICIENCIA)
        ids = [fuente['id'] for fuente in entrada.get('fuentes', []) if fuente.get('id')]
        esquema['properties']['referencias']['items']['enum'] = ids
        resultado = self.cliente.consultar(entrada, esquema, INSTRUCCION_SUFICIENCIA)
        referencias = resultado['referencias']
        preguntas = resultado['preguntas']
        if any(not pregunta.strip() or not pregunta.strip().endswith('?') for pregunta in preguntas):
            raise AnalisisNoDisponible('La API devolvió preguntas inválidas para HU09.')
        if resultado['estado'] == 'SUFICIENTE' and (not referencias or preguntas):
            raise AnalisisNoDisponible('La API devolvió una suficiencia sin fuentes válidas.')
        return resultado


class APIBibliografia:
    def __init__(self, cliente):
        self.cliente = cliente

    def __call__(self, entrada):
        esquema = deepcopy(ESQUEMA_BIBLIOGRAFIA)
        ids = [publicacion['id'] for publicacion in entrada.get('publicaciones', [])]
        esquema['properties']['sugerencias']['items']['properties']['publicacion_id']['enum'] = ids
        resultado = self.cliente.consultar(entrada, esquema, INSTRUCCION_BIBLIOGRAFIA)
        sugerencias = resultado['sugerencias']
        publicacion_ids = [sugerencia['publicacion_id'] for sugerencia in sugerencias]
        if len(publicacion_ids) != len(set(publicacion_ids)):
            raise AnalisisNoDisponible('La API repitió publicaciones en las sugerencias.')
        return resultado


class APIValoracion:
    def __init__(self, cliente):
        self.cliente = cliente

    def __call__(self, entrada):
        esquema = deepcopy(ESQUEMA_VALORACION)
        ids = [fuente['id'] for fuente in entrada.get('fuentes', []) if fuente.get('id')]
        esquema['properties']['referencias']['items']['enum'] = ids
        return self.cliente.consultar(entrada, esquema, INSTRUCCION_VALORACION)
