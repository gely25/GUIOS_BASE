"""Proveedor HTTPS de IA generativa con protocolo Chat Completions compatible.

La IA recibe únicamente el contexto proporcionado por los servicios HU09/HU10.
La validación, autorización y persistencia siguen dentro de la aplicación.
"""
import json
from copy import deepcopy
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from apps.external_services.ollama_preguntas import (
    AnalisisNoDisponible, ESQUEMA as ESQUEMA_PREGUNTAS, INSTRUCCION as INSTRUCCION_PREGUNTAS,
)
from apps.external_services.ollama_suficiencia import ESQUEMA as ESQUEMA_SUFICIENCIA, INSTRUCCION as INSTRUCCION_SUFICIENCIA
from apps.external_services.ollama_valoracion import ESQUEMA as ESQUEMA_VALORACION, INSTRUCCION as INSTRUCCION_VALORACION

LIMITE_ENTRADA = 16000
LIMITE_RESPUESTA = 65536


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
        # sus campos. Especificamos el esquema esperado para HU09/HU10 antes de
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
            headers={'Authorization': 'Bearer ' + self.clave, 'Content-Type': 'application/json', 'Accept': 'application/json'},
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
            if not isinstance(resultado, dict):
                raise ValueError('Se esperaba un objeto JSON')
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
        return self.cliente.consultar(entrada, ESQUEMA_SUFICIENCIA, INSTRUCCION_SUFICIENCIA)


class APIValoracion:
    def __init__(self, cliente):
        self.cliente = cliente

    def __call__(self, entrada):
        return self.cliente.consultar(entrada, ESQUEMA_VALORACION, INSTRUCCION_VALORACION)
