"""
Rutas de la capa de presentación - GUIOS PRO.

Ruta pública de acceso e inclusión de las rutas por área.
"""

from django.urls import include, path

from .views import home_view

app_name = 'presentation'

urlpatterns = [
    path('', home_view, name='home'),
    path('vista-previa/administracion/', include('apps.presentation.urls_admin')),
]
