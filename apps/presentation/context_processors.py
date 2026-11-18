"""
Contexto del menú lateral (capa de presentación).

Pide al catálogo (business_rules.menu) las opciones del rol y las traduce a URLs.
"""

from django.urls import reverse

from apps.business_rules import menu


def menu_lateral(request):
    coincidencia = getattr(request, 'resolver_match', None)
    ruta_actual = coincidencia.url_name if coincidencia else None
    usuario = getattr(request, 'user', None)
    rol = usuario.rol if usuario is not None and usuario.is_authenticated else None
    inicio = menu.inicio_de(rol)
    return {
        'menu_items': [
            {
                'etiqueta': m.etiqueta,
                'icono': m.icono,
                'url': reverse('presentation:' + m.ruta),
                'activo': ruta_actual == m.ruta or ruta_actual in m.alias,
            }
            for m in menu.menu_para(rol)
        ],
        'menu_seccion': menu.seccion_de(rol),
        'menu_inicio_url': reverse('presentation:' + (inicio or 'home')),
    }
