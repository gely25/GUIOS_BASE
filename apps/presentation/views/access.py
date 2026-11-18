"""
Vistas de acceso (capa de presentación).

Solo reciben la solicitud y devuelven la pantalla; la autenticación la hace Django
contra la tabla `usuario`. No hay cálculos ni consultas directas aquí.
"""

from urllib.parse import urlparse

from django.contrib.auth.views import LoginView
from django.urls import Resolver404, resolve, reverse

from apps.business_rules import menu
from apps.presentation.forms import AccesoForm


def _destino_permitido(rol, destino):
    """True si `destino` es una pantalla de la app que ese rol puede abrir."""
    try:
        coincidencia = resolve(urlparse(destino).path)
    except Resolver404:
        return False
    return (coincidencia.namespace == 'presentation'
            and menu.decidir_acceso(rol, coincidencia.url_name) == menu.PERMITIR)


class AccesoView(LoginView):
    template_name = 'presentation/acceso/login.html'
    authentication_form = AccesoForm
    redirect_authenticated_user = True
    extra_context = {'titulo': 'Iniciar sesión'}

    def get_success_url(self):
        # Respeta ?next= solo si es seguro y el rol puede abrirlo; si no, va a su inicio.
        rol = self.request.user.rol
        destino = self.get_redirect_url()
        if destino and _destino_permitido(rol, destino):
            return destino
        return reverse('presentation:' + (menu.inicio_de(rol) or 'home'))


home_view = AccesoView.as_view()
