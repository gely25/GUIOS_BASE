"""Enrutamiento concurrente hacia proveedores externos de IA."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import logging

from django.conf import settings

from apps.external_services.ai_errors import AnalisisNoDisponible
from apps.external_services.api_ia import (
    APIBibliografia, APIJSON, APIPreguntas, APISuficiencia, APIValoracion,
)

logger = logging.getLogger(__name__)
_EXECUTOR = ThreadPoolExecutor(max_workers=12, thread_name_prefix='guios-ai')
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


class ProveedoresParalelos:
    """Devuelve la primera respuesta que cumple el contrato del caso de uso."""

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

        tareas = {
            _EXECUTOR.submit(self._consultar, proveedor, entrada): proveedor
            for proveedor in proveedores
        }
        errores = []
        for tarea in as_completed(tareas):
            proveedor = tareas[tarea]
            try:
                resultado = tarea.result()
            except AnalisisNoDisponible as exc:
                errores.append(f'{proveedor.nombre}: {exc}')
                continue
            self.ultimo_proveedor = proveedor.nombre
            self.ultimo_modelo = proveedor.modelo
            for pendiente in tareas:
                if pendiente is not tarea:
                    pendiente.cancel()
            return resultado

        detalle = ' '.join(errores)
        raise AnalisisNoDisponible(
            'Ningún proveedor de IA devolvió una respuesta válida. ' + detalle
        )


def obtener_proveedor(tipo):
    """Crea un enrutador que solicita el mismo análisis a cada API configurada."""
    if tipo not in _ADAPTADORES:
        raise AnalisisNoDisponible('Tipo de análisis de IA no reconocido.')
    return ProveedoresParalelos(tipo)
