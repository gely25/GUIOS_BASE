"""
Vistas de acceso (capa de presentación).

Solo reciben la solicitud y devuelven la pantalla; la autenticación la hace Django
contra la tabla `usuario`. No hay cálculos ni consultas directas aquí.
"""

from urllib.parse import urlparse

from django.contrib.auth.views import LoginView
from django.urls import Resolver404, resolve, reverse

from apps.application.services.login_throttle import LoginThrottle
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

    def _identidad_intento(self):
        # No se confía en X-Forwarded-For enviado por el cliente.
        return (self.request.META.get('REMOTE_ADDR') or 'desconocida',
                self.request.POST.get('username', ''))

    def post(self, request, *args, **kwargs):
        if LoginThrottle.bloqueado(*self._identidad_intento()):
            # Formulario sin datos: no vuelve a autenticar ni repite la clave.
            formulario = self.get_form_class()(request=request)
            respuesta = self.render_to_response(
                self.get_context_data(form=formulario, acceso_limitado=True),
                status=429,
            )
            respuesta['Retry-After'] = str(LoginThrottle.VENTANA)
            return respuesta
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        LoginThrottle.fallo(*self._identidad_intento())
        return super().form_invalid(form)

    def form_valid(self, form):
        LoginThrottle.exito(*self._identidad_intento())
        return super().form_valid(form)

    def get_success_url(self):
        # Respeta ?next= solo si es seguro y el rol puede abrirlo; si no, va a su inicio.
        rol = self.request.user.rol
        destino = self.get_redirect_url()
        if destino and _destino_permitido(rol, destino):
            return destino
        return reverse('presentation:' + (menu.inicio_de(rol) or 'home'))


home_view = AccesoView.as_view()
