"""Selección de proveedor HU09/HU10 sin modificar las reglas de negocio."""
from django.conf import settings
from apps.external_services.api_ia import APIJSON, APIPreguntas, APISuficiencia, APIValoracion
from apps.external_services.ollama_preguntas import AnalisisNoDisponible, OllamaPreguntas
from apps.external_services.ollama_suficiencia import OllamaSuficiencia
from apps.external_services.ollama_valoracion import OllamaValoracion


def modelo_activo(hu10=False):
    if settings.GUIOS_AI_BACKEND == 'api':
        return settings.GUIOS_AI_MODEL
    return (settings.HU10_OLLAMA_MODEL or settings.HU09_OLLAMA_MODEL) if hu10 else settings.HU09_OLLAMA_MODEL


def configurado():
    if settings.GUIOS_AI_BACKEND == 'api':
        return bool(settings.GUIOS_AI_API_KEY and settings.GUIOS_AI_MODEL)
    return bool(settings.HU09_OLLAMA_MODEL)


def obtener_proveedor(tipo):
    """tipo: preguntas, suficiencia o valoracion. Exige configuración explícita."""
    if settings.GUIOS_AI_BACKEND == 'api':
        cliente = APIJSON(settings.GUIOS_AI_API_KEY, settings.GUIOS_AI_MODEL,
                          settings.GUIOS_AI_BASE_URL, settings.GUIOS_AI_TIMEOUT)
        return {'preguntas': APIPreguntas, 'suficiencia': APISuficiencia,
                'valoracion': APIValoracion}[tipo](cliente)
    if settings.GUIOS_AI_BACKEND != 'ollama':
        raise AnalisisNoDisponible('Proveedor de IA no reconocido.')
    modelo = modelo_activo(hu10=tipo == 'valoracion')
    if not modelo:
        raise AnalisisNoDisponible('La IA local no está configurada. Puede continuar en modo manual.')
    return {'preguntas': OllamaPreguntas, 'suficiencia': OllamaSuficiencia,
            'valoracion': OllamaValoracion}[tipo](modelo)
