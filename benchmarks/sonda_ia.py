"""Sonda manual de un solo caso sintético para diagnosticar acceso gratuito."""
import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError

from dotenv import dotenv_values

from apps.external_services.ai_errors import AnalisisNoDisponible
from apps.external_services.api_ia import APIPreguntas
from apps.external_services.clientes_ia import ClienteProveedor
from benchmarks.clientes_ia import obtener_metadatos, validar_endpoint_openrouter
from benchmarks.ia import ENV_PROYECTO, configurar


_MENSAJES_GROQ = {
    'model_permission_blocked_org': 'El modelo está bloqueado por la organización de Groq.',
    'model_permission_blocked_project': 'El modelo está bloqueado por el proyecto de la clave de Groq.',
    'model_terms_required': 'El modelo requiere aceptar sus condiciones en Groq.',
    'model_not_found': 'Groq no encuentra el modelo para esta solicitud.',
    'model_decommissioned': 'Groq indica que el modelo fue retirado.',
    'invalid_api_key': 'Groq rechazó la clave.',
    'unsupported_country': 'El proveedor indica que la región no tiene acceso.',
}


def _cuota_openrouter(clave, timeout):
    datos = obtener_metadatos('https://openrouter.ai/api/v1/key', timeout, clave)['data']
    contador = datos.get('free_model_daily_requests') or {}
    restante = contador.get('remaining')
    for nombre in ('limit', 'remaining'):
        valor = contador.get(nombre)
        if type(valor) is int and valor >= 0:
            print(f'Cuota diaria gratuita ({nombre}): {valor}')
    if type(restante) is not int:
        print('La API de clave no informó el saldo diario gratuito.')
        return None
    return restante


def _resumir_http(proveedor, error):
    with error:
        try:
            objeto = json.loads(error.read(8192))
            datos = objeto.get('error') or {}
            meta = datos.get('metadata') or {}
            if not isinstance(meta, dict):
                meta = {}
        except (ValueError, OSError, AttributeError):
            datos, meta = {}, {}
        estado = error.code
        print(f'HTTP {estado}')
        headers = error.headers or {}
        for nombre in ('Retry-After', 'X-RateLimit-Limit', 'X-RateLimit-Remaining', 'X-RateLimit-Reset'):
            valor = headers.get(nombre, '')
            if valor.isascii() and valor.isdecimal() and len(valor) <= 20:
                print(f'{nombre}: {valor}')
        if proveedor == 'groq' and isinstance(datos.get('code'), str):
            codigo = datos['code']
            if codigo in _MENSAJES_GROQ:
                print(f'{codigo}: {_MENSAJES_GROQ[codigo]}')
                return
        if proveedor == 'openrouter' and estado == 429:
            if meta.get('provider_code') is not None:
                print('429 del proveedor ascendente. Puede ser límite o saturación del endpoint.')
            elif headers.get('X-RateLimit-Limit') and headers.get('X-RateLimit-Reset'):
                print('429 de la plataforma OpenRouter. Consulte el contador y el reinicio del límite.')
            else:
                print('429 de origen indeterminado. La respuesta no identifica el límite aplicado.')
            return
        print('No se reconoció un código de error seguro. Consulte los permisos y el acceso de red.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('proveedor', choices=('cloudflare', 'groq', 'openrouter'))
    parser.add_argument('--autorizacion', required=True, type=Path)
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument('--cuota', action='store_true', help='Consulta solo el contador de la clave de OpenRouter.')
    modo.add_argument('--ejecutar', action='store_true', help='Envía una única solicitud sintética.')
    args = parser.parse_args()
    if args.cuota and args.proveedor != 'openrouter':
        parser.error('--cuota requiere openrouter.')
    try:
        entradas = json.loads(args.autorizacion.read_text(encoding='utf-8-sig'))
        variables = {**dotenv_values(ENV_PROYECTO, encoding='utf-8-sig', interpolate=False), **os.environ}
        configuracion = configurar([args.proveedor], 'real', entradas, variables)[args.proveedor]
    except (TypeError, ValueError, AttributeError, OSError):
        parser.error('Revise las variables y la autorización gratuita vigente del modelo configurado.')
    if not (args.cuota or args.ejecutar):
        print('Configuración y manifestación de gratuidad válidas. No se realizaron llamadas.')
        return
    modelo, clave, timeout, _, endpoint = configuracion
    try:
        if args.proveedor == 'openrouter':
            restante = _cuota_openrouter(clave, timeout)
            if args.cuota:
                return
            if restante == 0:
                print('Cuota diaria agotada. Se omite la inferencia.')
                return 1
            validar_endpoint_openrouter(modelo, endpoint, timeout)
        cliente = ClienteProveedor(args.proveedor, *configuracion)
        cliente.max_tokens_salida = 128
        cliente.tokens_reservados = 8192
        APIPreguntas(cliente)({'max_preguntas': 1, 'subfactor': 'Disponibilidad de manual de uso'})
        print('Inferencia aceptada y contrato válido. No se realizó ningún reintento.')
    except (HTTPError, AnalisisNoDisponible) as exc:
        error = exc if isinstance(exc, HTTPError) else exc.__cause__
        if isinstance(error, HTTPError):
            _resumir_http(args.proveedor, error)
        else:
            print('La sonda no obtuvo un contrato válido o tuvo un problema de conexión.')
        return 1
    except (URLError, OSError, TypeError, KeyError, ValueError, AttributeError):
        print('No se pudieron comprobar los metadatos o la cuota. No se reintenta.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
