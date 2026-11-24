"""
Rutas de la capa de presentación - GUIOS PRO.

Acceso (login/logout) e inclusión de las rutas por área. El control de acceso por
rol lo hace PermisosPorRolMiddleware con el catálogo de business_rules.menu:
toda ruta nueva debe declararse allí o queda denegada.
"""

from django.contrib.auth.views import LogoutView
from django.urls import include, path, reverse_lazy

from .views import home_view, registro_view

app_name = 'presentation'

urlpatterns = [
    path('', home_view, name='home'),
    path('registro/', registro_view, name='registro'),
    path('salir/', LogoutView.as_view(next_page=reverse_lazy('presentation:home')), name='logout'),
    path('decisor/', include('apps.presentation.urls_decisor')),
    path('administracion/', include('apps.presentation.urls_admin')),
]
