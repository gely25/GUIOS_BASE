"""Genera una constancia separada, exclusivamente para el benchmark sintético."""
import argparse
import json
from datetime import date
from pathlib import Path

from apps.external_services.clientes_ia import MODELOS_GEMMA, MODELOS_GOOGLE_CANDIDATOS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--salida', type=Path, required=True)
    parser.add_argument('--confirmo-nivel-gratuito', action='store_true')
    args = parser.parse_args()
    if not args.confirmo_nivel_gratuito:
        parser.error('Confirme que la clave usa un proyecto Free Tier sin facturación ni excedentes.')
    hoy = date.today().isoformat()
    entradas = [{
        'proveedor': 'gemini', 'modelo': modelo, 'plan': 'gemini-free-tier', 'uso': 'benchmark',
        'fuente_oficial': 'https://ai.google.dev/gemini-api/docs/pricing' + (
            '#gemma-4' if modelo in MODELOS_GEMMA else '#gemini-3.1-flash-lite'
        ),
        'verificado': hoy, 'vence': hoy, 'sin_cargos_ni_excedentes': True,
    } for modelo in MODELOS_GOOGLE_CANDIDATOS]
    try:
        with args.salida.open('x', encoding='utf-8') as archivo:
            json.dump(entradas, archivo, indent=2)
    except OSError:
        parser.error('No se pudo crear la constancia. Indique un archivo nuevo.')
    print('Constancia del operador creada para los tres candidatos. Vigencia: hoy.')


if __name__ == '__main__':
    main()
