"""Proveedor opcional de IA para HU09/HU10 mediante Groq (servicio externo).

Solo se usa con LLM_PROVIDER=groq y GROQ_API_KEY definidos. Por defecto el sistema sigue usando Ollama local.
Al activarlo, el contexto del subfactor (fragmentos y respuestas del decisor) se envía a Groq.
"""
import http.client
import json

from django.conf import settings

from .ollama_preguntas import AnalisisNoDisponible

HOST = 'api.groq.com'
RUTA = '/openai/v1/chat/completions'
# Modelos con soporte de json_schema (el resto usa json_object).
CON_ESQUEMA = ('openai/gpt-oss-20b', 'openai/gpt-oss-120b', 'qwen/qwen3.8-27b', 'meta-models/muse-spark-open')


def activo():
    return getattr(settings, 'LLM_PROVIDER', 'ollama') == 'groq' and bool(getattr(settings, 'GROQ_API_KEY', ''))


def _peticion(cuerpo):
    conexion = http.client.HTTPSConnection(HOST, timeout=90)
    try:
        conexion.request('POST', RUTA, body=json.dumps(cuerpo, ensure_ascii=False).encode('utf-8'), headers={
            'Content-Type': 'application/json', 'Authorization': 'Bearer ' + settings.GROQ_API_KEY,
            'User-Agent': 'guios-pro/1.0'})
        respuesta = conexion.getresponse()
        return respuesta.status, respuesta.read(131073)
    finally:
        conexion.close()


def consultar(modelo, datos, esquema, instruccion):
    """Devuelve el objeto JSON del modelo. Nunca incluye la clave en los mensajes de error."""
    formatos = []
    if modelo in CON_ESQUEMA:
        formatos.append({'type': 'json_schema', 'json_schema': {'name': 'respuesta', 'strict': False, 'schema': esquema}})
    formatos.append({'type': 'json_object'})
    try:
        for i, formato in enumerate(formatos):
            sistema = instruccion if formato['type'] == 'json_schema' else (
                instruccion + ' Responde únicamente con un objeto JSON que cumpla este esquema: ' + json.dumps(esquema, ensure_ascii=False))
            estado, contenido = _peticion({
                'model': modelo, 'temperature': 0, 'max_completion_tokens': 2048, 'response_format': formato,
                'messages': [{'role': 'system', 'content': sistema}, {'role': 'user', 'content': datos}]})
            if estado == 400 and i < len(formatos) - 1:
                continue
            break
        if estado in (401, 403):
            raise AnalisisNoDisponible('La clave de Groq no es válida o no tiene permiso. Revise GROQ_API_KEY.')
        if estado == 429:
            raise AnalisisNoDisponible('Se alcanzó el límite de uso de Groq. Espere un momento y repita.')
        if estado != 200:
            raise AnalisisNoDisponible('Groq no pudo procesar la solicitud (código %s).' % estado)
        if len(contenido) > 131072:
            raise AnalisisNoDisponible('La respuesta del modelo supera el límite permitido.')
        eleccion = json.loads(contenido)['choices'][0]
        if eleccion.get('finish_reason') == 'length':
            raise AnalisisNoDisponible('El modelo no terminó el análisis. Repita la operación.')
        return json.loads(eleccion['message']['content'])
    except (OSError, http.client.HTTPException) as exc:
        raise AnalisisNoDisponible('No se pudo conectar con Groq o se agotó el tiempo de respuesta.') from exc
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise AnalisisNoDisponible('El modelo devolvió un formato inválido. No se guardó nada.') from exc