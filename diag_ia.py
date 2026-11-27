"""Muestra la admisión configurada sin abrir conexiones con proveedores."""
import os

import django


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()

    from apps.external_services.proveedor_ia import leer_admision

    proveedores, _, _ = leer_admision()
    if not proveedores:
        print('No hay modelos admitidos por la configuración y el manifiesto local.')
        return 1
    for proveedor in proveedores:
        print(proveedor.identificador_config, ', '.join(sorted(proveedor.operaciones)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
