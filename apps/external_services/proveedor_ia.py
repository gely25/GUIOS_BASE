"""Enrutamiento por turnos, con respaldo, hacia proveedores externos de IA."""
from dataclasses import dataclass
import logging
from threading import Lock

from django.conf import settings

from apps.external_services.ai_errors import AnalisisNoDisponible
from apps.external_services.api_ia import (
    APIBibliografia, APIJSON, APIPreguntas, APISuficiencia, APIValoracion,
)

logger = logging.getLogger(__name__)
# Turno global compartido por todos los hilos del proceso: reparte las peticiones
# entre los proveedores configurados (Gemini, Groq, Gemini, ...).
_turno = 0
_turno_lock = Lock()
_URLS = {
    'Gemini': 'https://generativelanguage.googleapis.com/v1beta/openai',
    'OpenAI': 'https://api.openai.com/v1',
    'Groq': 'https://api.groq.com/openai/v1',
}
_ADAPTADORES = {
    'bibliografia': APIBibliografia,
    'preguntas': APIPreguntas,
    'suficiencia': APISuficiencia,
    'valoracion': APIValoracion,
}
_MAX_MODELO = 92


@dataclass(frozen=True)
class ProveedorConfigurado:
    nombre: str
    clave: str
    modelo: str
    base_url: str


def _leer_proveedores():
    disponibles = []
    incompletos = []
    for nombre in _URLS:
        prefijo = f'GUIOS_AI_{nombre.upper()}'
        clave = getattr(settings, f'{prefijo}_API_KEY', '').strip()
        modelo = getattr(settings, f'{prefijo}_MODEL', '').strip()
        if not clave and not modelo:
            continue
        if not clave or not modelo:
            incompletos.append(f'{nombre} requiere {prefijo}_API_KEY y {prefijo}_MODEL.')
            continue
        if len(modelo) > _MAX_MODELO:
            incompletos.append(f'{prefijo}_MODEL excede el máximo de {_MAX_MODELO} caracteres.')
            continue
        disponibles.append(ProveedorConfigurado(nombre, clave, modelo, _URLS[nombre]))
    return disponibles, incompletos


def modelo_activo():
    """Nombres de los proveedores configurados, para mostrarlos en la interfaz."""
    proveedores, _ = _leer_proveedores()
    return ' + '.join(proveedor.nombre for proveedor in proveedores)


def configurado():
    proveedores, _ = _leer_proveedores()
    return bool(proveedores)


def _siguiente_turno(cantidad):
    """Índice del proveedor que inicia la próxima petición; seguro entre hilos."""
    global _turno
    with _turno_lock:
        indice = _turno % cantidad
        _turno += 1
    return indice


class ProveedoresRespaldo:
    """Envía cada petición a un solo proveedor, elegido por turnos.

    Si ese proveedor falla (error HTTP, 429, timeout o respuesta fuera del
    contrato), reintenta con el siguiente de la lista hasta agotar los
    proveedores configurados. Así cada análisis consume cupo de una sola API.
    """

    def __init__(self, tipo):
        if tipo not in _ADAPTADORES:
            raise AnalisisNoDisponible('Tipo de análisis de IA no reconocido.')
        self.tipo = tipo
        self.ultimo_proveedor = None
        self.ultimo_modelo = None

    @property
    def ultimo_identificador(self):
        if not self.ultimo_proveedor or not self.ultimo_modelo:
            return None
        return f'{self.ultimo_proveedor}/{self.ultimo_modelo}'

    def _consultar(self, proveedor, entrada):
        cliente = APIJSON(
            proveedor.clave,
            proveedor.modelo,
            proveedor.base_url,
            settings.GUIOS_AI_TIMEOUT,
        )
        return _ADAPTADORES[self.tipo](cliente)(entrada)

    def __call__(self, entrada):
        proveedores, incompletos = _leer_proveedores()
        if not proveedores:
            if incompletos:
                raise AnalisisNoDisponible(' '.join(incompletos))
            raise AnalisisNoDisponible(
                'Configure al menos un proveedor con su clave y modelo. Puede continuar manualmente.'
            )
        if incompletos:
            logger.warning('Proveedores de IA omitidos por configuración incompleta: %s', ' '.join(incompletos))

        inicio = _siguiente_turno(len(proveedores))
        orden = proveedores[inicio:] + proveedores[:inicio]
        errores = []
        for proveedor in orden:
            try:
                resultado = self._consultar(proveedor, entrada)
            except AnalisisNoDisponible as exc:
                errores.append(f'{proveedor.nombre}: {exc}')
                logger.info('Proveedor de IA %s falló; se intenta el siguiente. %s', proveedor.nombre, exc)
                continue
            self.ultimo_proveedor = proveedor.nombre
            self.ultimo_modelo = proveedor.modelo
            return resultado

        # Se conserva el texto de cada error para que la página distinga 429/5xx y espere.
        raise AnalisisNoDisponible(
            'Ningún proveedor de IA devolvió una respuesta válida. ' + ' '.join(errores)
        )


def obtener_proveedor(tipo):
    """Crea un enrutador que reparte el análisis por turnos, con respaldo entre APIs."""
    if tipo not in _ADAPTADORES:
        raise AnalisisNoDisponible('Tipo de análisis de IA no reconocido.')
    return ProveedoresRespaldo(tipo)
