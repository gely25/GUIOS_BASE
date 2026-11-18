"""
Control de acceso por rol (HU01) - capa de presentación.

Revisa TODAS las rutas de la app `presentation` (GET y POST) contra el catálogo
de `business_rules.menu`. Lo que el catálogo no declara se niega, así una vista
nueva nunca queda abierta por olvido.
"""

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render, resolve_url

from apps.business_rules import menu


class PermisosPorRolMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        coincidencia = request.resolver_match
        if coincidencia is None or coincidencia.namespace != 'presentation':
            return None
        if coincidencia.url_name in menu.RUTAS_PUBLICAS:
            return None

        usuario = request.user
        rol = usuario.rol if usuario.is_authenticated else None
        decision = menu.decidir_acceso(rol, coincidencia.url_name)

        if decision == menu.PERMITIR:
            return None
        if decision == menu.PEDIR_LOGIN:
            return redirect_to_login(request.get_full_path(), resolve_url(settings.LOGIN_URL))
        return render(request, 'presentation/comun/acceso_denegado.html', status=403)
