"""Errores compartidos por los proveedores de IA."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import Enum


class AnalisisNoDisponible(Exception):
    """Ningún proveedor entregó una respuesta utilizable."""


class Motivo(str, Enum):
    NO_AUTENTICADO = '401'
    PROHIBIDO = '403'
    CUOTA = '429'
    SERVIDOR = '5xx'
    TIMEOUT = 'timeout'
    RED = 'red'
    RESPUESTA_INVALIDA = 'respuesta_invalida'
    HTTP = 'http'


class ErrorProveedor(AnalisisNoDisponible):
    def __init__(self, motivo, mensaje, estado_http=None, retry_after=None):
        super().__init__(mensaje)
        self.motivo = motivo
        self.estado_http = estado_http
        self.retry_after = retry_after

    @classmethod
    def desde_http(cls, error, mensaje):
        motivos = {401: Motivo.NO_AUTENTICADO, 403: Motivo.PROHIBIDO, 429: Motivo.CUOTA}
        motivo = motivos.get(error.code, Motivo.SERVIDOR if 500 <= error.code < 600 else Motivo.HTTP)
        valor = error.headers.get('Retry-After') if error.headers else None
        pausa = None
        if valor:
            try:
                pausa = int(valor) if valor.isdecimal() else max(
                    0, (parsedate_to_datetime(valor).replace(tzinfo=timezone.utc)
                        - datetime.now(timezone.utc)).total_seconds()
                )
            except (ValueError, TypeError, OverflowError):
                pass
        return cls(motivo, mensaje, error.code, pausa)


class RespuestaInvalida(ErrorProveedor):
    def __init__(self, mensaje):
        super().__init__(Motivo.RESPUESTA_INVALIDA, mensaje)
