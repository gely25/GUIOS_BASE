"""Genera una constancia local para el benchmark sintético de Typhoon."""
import argparse
import json
from datetime import date
from pathlib import Path

from benchmarks.clientes_ia import TYPHOON_MODELO


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--salida', type=Path, required=True)
    parser.add_argument('--confirmo-nivel-gratuito', action='store_true')
    args = parser.parse_args()
    if not args.confirmo_nivel_gratuito:
        parser.error('Confirme que la clave corresponde a la API experimental gratuita de Typhoon.')
    hoy = date.today().isoformat()
    entrada = dict(proveedor='typhoon', modelo=TYPHOON_MODELO, plan='typhoon-free-benchmark',
                   uso='benchmark', fuente_oficial='https://docs.opentyphoon.ai/en/faq/',
                   verificado=hoy, vence=hoy, sin_cargos_ni_excedentes=True)
    try:
        with args.salida.open('x', encoding='utf-8') as archivo:
            json.dump([entrada], archivo, indent=2)
    except OSError:
        parser.error('No se pudo crear la constancia. Indique un archivo nuevo.')
    print('Constancia del operador para Typhoon creada. Vigencia: hoy, solo benchmark sintético.')


if __name__ == '__main__':
    main()
