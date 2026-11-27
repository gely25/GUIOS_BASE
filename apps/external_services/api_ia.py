"""Proveedor HTTPS de IA generativa con protocolo Chat Completions compatible.

La IA recibe únicamente el contexto proporcionado por los servicios HU09/HU10.
La validación, autorización y persistencia siguen dentro de la aplicación.
"""
import json
import math
from copy import deepcopy
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from apps.external_services.ai_contracts import (
    ESQUEMA_BIBLIOGRAFIA, ESQUEMA_PREGUNTAS, ESQUEMA_SUFICIENCIA, ESQUEMA_VALORACION,
    INSTRUCCION_BIBLIOGRAFIA, INSTRUCCION_PREGUNTAS, INSTRUCCION_SUFICIENCIA,
    INSTRUCCION_VALORACION,
)
from apps.external_services.ai_errors import AnalisisNoDisponible, ErrorProveedor, Motivo, RespuestaInvalida

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

    @staticmethod
    def preparar_carga(modelo, entrada, esquema, instruccion):
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
        return {
            'model': modelo,
            'messages': [
                {'role': 'system', 'content': instrucciones},
                {'role': 'user', 'content': datos},
            ],
            'stream': False,
            'temperature': 0,
            'response_format': {'type': 'json_object'},
        }

    def consultar(self, entrada, esquema, instruccion):
        carga = self.preparar_carga(self.modelo, entrada, esquema, instruccion)
        try:
            paquete = self._solicitar(carga)
            respuesta = paquete['choices'][0]
            if respuesta.get('finish_reason') == 'length':
                raise RespuestaInvalida('La IA no terminó la respuesta. Repita el análisis.')
            texto = respuesta['message']['content']
            if not isinstance(texto, str):
                raise ValueError('Contenido inválido')
            texto = texto.strip()
            if texto.startswith('```'):
                lineas = texto.splitlines()
                texto = '\n'.join(lineas[1:-1]).strip()
            resultado = self._decodificar(texto)
            if not _cumple_esquema(resultado, esquema):
                raise RespuestaInvalida('La IA devolvió una respuesta fuera del esquema esperado.')
            return resultado
        except HTTPError as exc:
            # No mostrar cuerpos de respuesta ni encabezados de un proveedor externo.
            if exc.code == 401:
                detalle = 'Credenciales de API rechazadas.'
            elif exc.code == 403:
                detalle = 'La API de IA denegó el acceso.'
            elif exc.code == 429:
                detalle = 'La API de IA alcanzó su límite de solicitudes.'
            else:
                detalle = f'La API de IA devolvió el estado HTTP {exc.code}.'
            raise ErrorProveedor.desde_http(exc, detalle) from exc
        except (URLError, TimeoutError, OSError, HTTPException) as exc:
            causa = getattr(exc, 'reason', exc)
            motivo = Motivo.TIMEOUT if isinstance(causa, TimeoutError) else Motivo.RED
            raise ErrorProveedor(motivo, 'No se pudo contactar con la API de IA. Continúe en modo manual.') from exc
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise RespuestaInvalida('La API devolvió datos inválidos. No se guardó la propuesta.') from exc

    def _solicitar(self, carga):
        peticion = Request(
            self.base_url + '/chat/completions',
            data=json.dumps(carga, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self.clave, 'Content-Type': 'application/json', 'Accept': 'application/json'},
            method='POST',
        )
        with urlopen(peticion, timeout=self.timeout) as respuesta:
            contenido = respuesta.read(LIMITE_RESPUESTA + 1)
        if len(contenido) > LIMITE_RESPUESTA:
            raise RespuestaInvalida('La respuesta de IA supera el límite permitido.')
        return json.loads(contenido)

    def _decodificar(self, texto):
        return json.loads(texto)


class APIPreguntas:
    def __init__(self, cliente):
        self.cliente = cliente

    @staticmethod
    def contrato(entrada):
        cupo = entrada.get('max_preguntas', 3)
        if type(cupo) is not int or not 1 <= cupo <= 3:
            raise AnalisisNoDisponible('Cupo de preguntas inválido.')
        esquema = deepcopy(ESQUEMA_PREGUNTAS)
        esquema['properties']['preguntas']['maxItems'] = cupo
        return esquema, INSTRUCCION_PREGUNTAS

    def __call__(self, entrada):
        resultado = self.cliente.consultar(entrada, *self.contrato(entrada))
        cupo = entrada.get('max_preguntas', 3)
        if set(resultado) != {'preguntas'} or not isinstance(resultado['preguntas'], list):
            raise RespuestaInvalida('La API devolvió un formato inválido de preguntas.')
        preguntas = resultado['preguntas']
        if len(preguntas) > cupo or any(not isinstance(p, str) or not p.strip() or len(p.strip()) > 1000
                                      or not p.strip().endswith('?') for p in preguntas):
            raise RespuestaInvalida('La API devolvió preguntas inválidas.')
        return preguntas


class APISuficiencia:
    def __init__(self, cliente):
        self.cliente = cliente

    @staticmethod
    def contrato(entrada):
        esquema = deepcopy(ESQUEMA_SUFICIENCIA)
        ids = [fuente['id'] for fuente in entrada.get('fuentes', []) if fuente.get('id')]
        esquema['properties']['referencias']['items']['enum'] = ids
        return esquema, INSTRUCCION_SUFICIENCIA

    def __call__(self, entrada):
        resultado = self.cliente.consultar(entrada, *self.contrato(entrada))
        referencias = resultado['referencias']
        preguntas = resultado['preguntas']
        if any(not pregunta.strip() or not pregunta.strip().endswith('?') for pregunta in preguntas):
            raise RespuestaInvalida('La IA devolvió preguntas inválidas durante el análisis de suficiencia.')
        if resultado['estado'] == 'SUFICIENTE' and (not referencias or preguntas):
            raise RespuestaInvalida('La API devolvió una suficiencia sin fuentes válidas.')
        return resultado


class APIBibliografia:
    def __init__(self, cliente):
        self.cliente = cliente

    @staticmethod
    def contrato(entrada):
        esquema = deepcopy(ESQUEMA_BIBLIOGRAFIA)
        ids = [publicacion['id'] for publicacion in entrada.get('publicaciones', [])]
        esquema['properties']['sugerencias']['items']['properties']['publicacion_id']['enum'] = ids
        return esquema, INSTRUCCION_BIBLIOGRAFIA

    def __call__(self, entrada):
        resultado = self.cliente.consultar(entrada, *self.contrato(entrada))
        sugerencias = resultado['sugerencias']
        publicacion_ids = [sugerencia['publicacion_id'] for sugerencia in sugerencias]
        if len(publicacion_ids) != len(set(publicacion_ids)):
            raise RespuestaInvalida('La API repitió publicaciones en las sugerencias.')
        return resultado


class APIValoracion:
    def __init__(self, cliente):
        self.cliente = cliente

    @staticmethod
    def contrato(entrada):
        esquema = deepcopy(ESQUEMA_VALORACION)
        ids = [fuente['id'] for fuente in entrada.get('fuentes', []) if fuente.get('id')]
        esquema['properties']['referencias']['items']['enum'] = ids
        return esquema, INSTRUCCION_VALORACION

    def __call__(self, entrada):
        return self.cliente.consultar(entrada, *self.contrato(entrada))
