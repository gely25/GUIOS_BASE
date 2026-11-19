"""Embeddings de preguntas HU09 exclusivamente por Ollama local."""
import http.client
import json
import math

from apps.external_services.ollama_preguntas import AnalisisNoDisponible


class OllamaEmbeddings:
    def __init__(self, modelo):
        if modelo not in ('bge-m3', 'bge-m3:latest'):
            raise AnalisisNoDisponible('Configure bge-m3 como modelo de embeddings local.')
        self.modelo = modelo

    def __call__(self, textos):
        if not textos:
            return []
        if len(textos) > 128 or any(not isinstance(t, str) or not t.strip() or len(t) > 1000 for t in textos):
            raise AnalisisNoDisponible('Se superó el límite de preguntas para comparación semántica.')
        cuerpo = json.dumps({'model': self.modelo, 'input': textos, 'truncate': False}, ensure_ascii=False).encode('utf-8')
        conexion = http.client.HTTPConnection('127.0.0.1', 11434, timeout=120)
        try:
            conexion.request('POST', '/api/embed', body=cuerpo, headers={'Content-Type': 'application/json'})
            respuesta = conexion.getresponse()
            if respuesta.status != 200:
                raise AnalisisNoDisponible('Embeddings no disponibles. Compruebe que bge-m3 esté instalado.')
            contenido = respuesta.read(8_000_001)
            if len(contenido) > 8_000_000:
                raise ValueError('Respuesta excesiva')
            vectores = json.loads(contenido)['embeddings']
            if not isinstance(vectores, list) or len(vectores) != len(textos):
                raise ValueError('Número de vectores inválido')
            for v in vectores:
                if not isinstance(v, list) or len(v) != 1024 or any(type(x) not in (int, float) or not math.isfinite(x) for x in v):
                    raise ValueError('Vector inválido')
                if not any(v):
                    raise ValueError('Vector nulo')
            return vectores
        except (OSError, http.client.HTTPException) as exc:
            raise AnalisisNoDisponible('No se pudo conectar con el modelo local de embeddings.') from exc
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise AnalisisNoDisponible('El proveedor de embeddings devolvió datos inválidos.') from exc
        finally:
            conexion.close()
