"""
Rutas de la capa de presentación - GUIOS PRO.

Acceso (login/logout) e inclusión de las rutas por área.
"""

from django.contrib.auth.views import LogoutView
from django.urls import include, path, reverse_lazy

from .views import home_view

app_name = 'presentation'

urlpatterns = [
    path('', home_view, name='home'),
    path('salir/', LogoutView.as_view(next_page=reverse_lazy('presentation:home')), name='logout'),
    path('vista-previa/decisor/', include('apps.presentation.urls_decisor')),
    path('vista-previa/administracion/', include('apps.presentation.urls_admin')),
]
