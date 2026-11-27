import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import override_settings


class IAConfiguradaPruebas:
    """Configura la autorización ficticia para pruebas que simulan un proveedor."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        carpeta = cls.enterClassContext(TemporaryDirectory())
        ruta = Path(carpeta) / 'autorizacion.json'
        modelo = settings.GUIOS_AI_GEMINI_MODEL
        hoy = date.today().isoformat()
        ruta.write_text(json.dumps([{
            'proveedor': 'gemini', 'modelo': modelo, 'plan': 'gemini-free-tier',
            'fuente_oficial': 'https://ai.google.dev/gemini-api/docs/pricing',
            'verificado': hoy, 'vence': hoy, 'sin_cargos_ni_excedentes': True,
        }]), encoding='utf-8')
        operaciones = ('bibliografia', 'preguntas', 'suficiencia', 'valoracion')
        cls.enterClassContext(override_settings(
            GUIOS_AI_AUTORIZACION_GRATUITA=ruta,
            GUIOS_AI_GEMINI_OPERACIONES=','.join(operaciones),
            GUIOS_AI_GEMINI_UNIDAD_CUOTA='gemini',
            GUIOS_AI_PERFILES_OPERACION=json.dumps({
                f'gemini/{modelo}': {op: {'validado': True} for op in operaciones},
            }),
            GUIOS_AI_POLITICAS_CUOTA=json.dumps({
                'gemini': {'rpm': 10, 'rpd': 10, 'tpm': None,
                           'max_tokens_salida': 200, 'tokens_por_intento': 5000},
            }),
        ))
