import time

from django.conf import settings

from apps.external_services.ai_errors import AnalisisNoDisponible
from apps.external_services.api_ia import APIJSON


MODELOS = ("gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
ESQUEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ok"],
    "properties": {"ok": {"type": "boolean"}},
}

for modelo in MODELOS:
    t = time.time()
    try:
        cliente = APIJSON(
            settings.GUIOS_AI_GEMINI_API_KEY,
            modelo,
            "https://generativelanguage.googleapis.com/v1beta/openai",
            settings.GUIOS_AI_TIMEOUT,
        )
        respuesta = cliente.consultar(
            {"solicitud": 'Devuelve {"ok": true}.'},
            ESQUEMA,
            "Responde con el objeto JSON de prueba solicitado.",
        )
        print(modelo, "OK", respuesta, round(time.time() - t, 1), "s")
    except AnalisisNoDisponible as error:
        print(modelo, "FALLA", str(error))