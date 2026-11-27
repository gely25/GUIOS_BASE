"""Transporte y autorización de gratuidad para la aplicación y el benchmark."""
import json
import re
from datetime import date
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from apps.external_services.ai_errors import RespuestaInvalida
from apps.external_services.api_ia import APIJSON, LIMITE_RESPUESTA


PROVEEDORES = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai",
               "ai.google.dev", "gemini-free-tier"),
    "groq": ("https://api.groq.com/openai/v1", "console.groq.com", "groq-free"),
    "cohere": ("https://api.cohere.com/v2", "docs.cohere.com", "cohere-trial"),
    "cloudflare": ("https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/v1",
                   "developers.cloudflare.com", "workers-free"),
    "openrouter": ("https://openrouter.ai/api/v1", "openrouter.ai", "openrouter-free"),
}
MODELOS_GEMMA = frozenset(("gemma-4-26b-a4b-it", "gemma-4-31b-it"))
MODELOS_GOOGLE_CANDIDATOS = (*sorted(MODELOS_GEMMA), "gemini-3.1-flash-lite")


def _google_nativo(proveedor, modelo):
    return proveedor == "gemini" and modelo in MODELOS_GOOGLE_CANDIDATOS


def autorizar(proveedor, modelo, entradas, hoy, *, benchmark=False, registro=PROVEEDORES):
    """Comprueba una revisión local del modelo y la cuenta, sin consultar APIs."""
    _, dominio, plan = registro[proveedor]
    for entrada in entradas:
        if (entrada.get("proveedor"), entrada.get("modelo")) != (proveedor, modelo):
            continue
        uso = entrada.get("uso", "operativo")
        if uso != "operativo" and not (benchmark and uso == "benchmark"):
            continue
        fuente = urlsplit(entrada.get("fuente_oficial", ""))
        verificado = date.fromisoformat(entrada.get("verificado", ""))
        vence = date.fromisoformat(entrada.get("vence", ""))
        if (fuente.scheme != "https" or fuente.netloc != dominio
                or not verificado <= hoy <= vence
                or entrada.get("plan") != plan
                or entrada.get("sin_cargos_ni_excedentes") is not True):
            continue
        endpoint = entrada.get("endpoint_openrouter", "")
        if proveedor == "openrouter" and (
            not modelo.endswith(":free") or modelo.startswith(("openai/", "openrouter/"))
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./-]*", endpoint)
            or endpoint.lower().split("/")[0] == "openai"
        ):
            continue
        return endpoint
    raise ValueError("Autorización gratuita ausente, inválida o vencida.")


class SinRedirecciones(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def enviar(url, carga, clave, timeout):
    destino = urlsplit(url)
    nativo_google = (destino.hostname == "generativelanguage.googleapis.com"
                     and destino.path.endswith(":generateContent"))
    autenticacion = {"x-goog-api-key": clave} if nativo_google else {"Authorization": "Bearer " + clave}
    peticion = Request(
        url, data=json.dumps(carga, ensure_ascii=False).encode("utf-8"),
        headers={**autenticacion, "Content-Type": "application/json",
                 "Accept": "application/json"},
        method="POST",
    )
    with build_opener(SinRedirecciones()).open(peticion, timeout=timeout) as respuesta:
        contenido = respuesta.read(LIMITE_RESPUESTA + 1)
    if len(contenido) > LIMITE_RESPUESTA:
        raise RespuestaInvalida("La respuesta supera el límite permitido.")
    return json.loads(contenido)


def preparar_peticion(proveedor, carga, endpoint, max_tokens_salida):
    if _google_nativo(proveedor, carga["model"]):
        modelo = carga["model"]
        sistema, entrada = carga["messages"]
        generacion = {"temperature": carga["temperature"]}
        if modelo not in MODELOS_GEMMA:
            generacion["responseMimeType"] = "application/json"
        if max_tokens_salida is not None:
            generacion["maxOutputTokens"] = max_tokens_salida
        carga.clear()
        carga.update(
            systemInstruction={"parts": [{"text": sistema["content"]}]},
            contents=[{"role": "user", "parts": [{"text": entrada["content"]}]}],
            generationConfig=generacion,
        )
        return f"/models/{modelo}:generateContent"
    ruta = "/chat" if proveedor == "cohere" else "/chat/completions"
    if proveedor == "openrouter":
        carga["provider"] = {
            "only": [endpoint], "allow_fallbacks": False,
            "max_price": {"prompt": 0, "completion": 0, "request": 0},
        }
    if max_tokens_salida is not None:
        campo = "max_completion_tokens" if proveedor == "groq" else "max_tokens"
        carga[campo] = max_tokens_salida
    return ruta


def bytes_contexto(carga):
    # El proveedor tokeniza los mensajes decodificados, no el sobre JSON de HTTP.
    return sum(len(mensaje["content"].encode("utf-8")) for mensaje in carga["messages"])


class ClienteProveedor(APIJSON):
    proveedores = PROVEEDORES

    def __init__(self, proveedor, modelo, clave, timeout, cuenta="", endpoint="", transporte=enviar):
        base = self.proveedores[proveedor][0].format(cuenta=cuenta)
        if _google_nativo(proveedor, modelo):
            base = base.removesuffix("/openai")
        super().__init__(clave, modelo, base, timeout)
        self.proveedor = proveedor
        self.endpoint = endpoint
        self.transporte = transporte
        self.uso = {}
        self.resultado_json = None
        self.json_valido = False
        self.max_tokens_salida = None
        self.tokens_reservados = None
        self.margen_tokens_entrada = None

    def _solicitar(self, carga):
        contexto = bytes_contexto(carga) if self.margen_tokens_entrada is not None else None
        ruta = preparar_peticion(
            self.proveedor, carga, self.endpoint, self.max_tokens_salida,
        )
        if self.max_tokens_salida is not None:
            bytes_entrada = (len(json.dumps(carga, ensure_ascii=False).encode("utf-8"))
                             if contexto is None else contexto + self.margen_tokens_entrada)
            if bytes_entrada + self.max_tokens_salida > self.tokens_reservados:
                raise RespuestaInvalida("La entrada supera la reserva conservadora de tokens de este modelo.")
        paquete = self.transporte(self.base_url + ruta, carga, self.clave, self.timeout)
        if _google_nativo(self.proveedor, self.modelo):
            uso = paquete.get("usageMetadata") or {}
            self.uso = {"tokens_entrada": uso.get("promptTokenCount"),
                        "tokens_salida": uso.get("candidatesTokenCount"),
                        "tokens_totales": uso.get("totalTokenCount")}
            candidato = paquete["candidates"][0]
            if candidato.get("finishReason") != "STOP":
                raise RespuestaInvalida("El modelo de Google no devolvió una respuesta completa.")
            texto = "".join(parte["text"] for parte in candidato["content"]["parts"]
                            if "text" in parte and not parte.get("thought"))
            return {"choices": [{"message": {"content": texto}}]}
        uso = paquete.get("usage") or {}
        if self.proveedor == "cohere":
            tokens = uso.get("tokens") or {}
            self.uso = {"tokens_entrada": tokens.get("input_tokens"),
                        "tokens_salida": tokens.get("output_tokens")}
            texto = "".join(
                parte["text"] for parte in paquete["message"]["content"] if parte["type"] == "text"
            )
            motivo = "length" if paquete.get("finish_reason") == "MAX_TOKENS" else None
            return {"choices": [{"message": {"content": texto}, "finish_reason": motivo}]}
        self.uso = {"tokens_entrada": uso.get("prompt_tokens"),
                    "tokens_salida": uso.get("completion_tokens"),
                    "tokens_totales": uso.get("total_tokens")}
        return paquete

    def _decodificar(self, texto):
        resultado = super()._decodificar(texto)
        self.resultado_json = resultado
        self.json_valido = True
        return resultado
