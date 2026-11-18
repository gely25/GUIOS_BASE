"""
Vistas de acceso (capa de presentación).

Solo reciben la solicitud y devuelven la pantalla; la autenticación la hace Django
contra la tabla `usuario`. No hay cálculos ni consultas directas aquí.
"""

from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy

from apps.presentation.forms import AccesoForm

INICIO_POR_ROL = {
    'ADMINISTRADOR': 'presentation:admin-inicio',
    'DECISOR': 'presentation:decisor-inicio',
}


class AccesoView(LoginView):
    template_name = 'presentation/acceso/login.html'
    authentication_form = AccesoForm
    redirect_authenticated_user = True
    extra_context = {'titulo': 'Iniciar sesión'}

    def get_success_url(self):
        # Respeta ?next= si es seguro; si no, lleva a la pantalla de inicio del rol.
        destino = self.get_redirect_url()
        if destino:
            return destino
        return reverse_lazy(INICIO_POR_ROL.get(self.request.user.rol, 'presentation:home'))


home_view = AccesoView.as_view()
