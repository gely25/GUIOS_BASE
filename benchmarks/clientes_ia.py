"""Transporte común con registro adicional exclusivo del benchmark."""
import json
from decimal import Decimal, InvalidOperation
from http.client import HTTPException
from urllib.parse import quote
from urllib.request import Request, build_opener

from apps.external_services.ai_errors import RespuestaInvalida
from apps.external_services.clientes_ia import (
    PROVEEDORES as PROVEEDORES_OPERATIVOS, ClienteProveedor, SinRedirecciones, autorizar as autorizar_proveedor,
    bytes_contexto,
)


TYPHOON_MODELO = 'typhoon-v2.5-30b-a3b-instruct'
PROVEEDORES = {**PROVEEDORES_OPERATIVOS,
               'typhoon': ('https://api.opentyphoon.ai/v1', 'docs.opentyphoon.ai', 'typhoon-free-benchmark')}


def autorizar(proveedor, modelo, entradas, hoy, *, benchmark=False):
    if proveedor == 'typhoon':
        entradas = [entrada for entrada in entradas if entrada.get('uso') == 'benchmark']
        if modelo != TYPHOON_MODELO:
            raise ValueError('Modelo Typhoon no habilitado para este benchmark.')
    return autorizar_proveedor(proveedor, modelo, entradas, hoy, benchmark=benchmark, registro=PROVEEDORES)


def obtener_metadatos(url, timeout, clave=None):
    cabeceras = {'Accept': 'application/json'}
    if clave:
        cabeceras['Authorization'] = 'Bearer ' + clave
    with build_opener(SinRedirecciones()).open(Request(url, headers=cabeceras), timeout=timeout) as respuesta:
        contenido = respuesta.read(65537)
    if len(contenido) > 65536:
        raise ValueError('La respuesta de metadatos supera el límite permitido.')
    return json.loads(contenido)


def validar_endpoint_openrouter(modelo, endpoint, timeout):
    partes = modelo.split('/')
    if len(partes) != 2 or any(x in ('', '.', '..') for x in partes):
        raise ValueError('Identificador de modelo inválido.')
    ruta = '/'.join(quote(x, safe=':') for x in partes)
    try:
        datos = obtener_metadatos(f'https://openrouter.ai/api/v1/models/{ruta}/endpoints', timeout)['data']
        if datos.get('id') == modelo:
            for candidato in datos.get('endpoints', []):
                if (candidato.get('tag'), candidato.get('model_id')) != (endpoint, modelo):
                    continue
                precio = candidato.get('pricing', {})
                if {'prompt', 'completion'} <= precio.keys() and all(
                    Decimal(str(valor)) == 0 for campo, valor in precio.items() if campo != 'discount'
                ):
                    return
    except (OSError, HTTPException, ValueError, AttributeError, TypeError, KeyError, InvalidOperation) as error:
        raise ValueError('No se pudo verificar el precio del endpoint autorizado.') from error
    raise ValueError('El endpoint autorizado no publica precios de cero para el modelo.')


class ClienteBenchmark(ClienteProveedor):
    proveedores = PROVEEDORES

    def _solicitar(self, carga):
        if self.proveedor == 'typhoon':
            # La referencia pública no documenta response_format. El contrato se mantiene en el prompt.
            carga.pop('response_format', None)
            carga['max_tokens'] = 1024
            if bytes_contexto(carga) + 256 + 1024 > 8192:
                raise RespuestaInvalida('El caso supera la reserva conservadora para Typhoon.')
        return super()._solicitar(carga)
