"""
Rutas de la capa de presentación - GUIOS PRO.

Ruta pública de acceso e inclusión de las rutas de vista previa por área.
"""

from django.urls import include, path

from .views import home_view

app_name = 'presentation'

urlpatterns = [
    path('', home_view, name='home'),
    path('vista-previa/decisor/', include('apps.presentation.urls_decisor')),
    path('vista-previa/administracion/', include('apps.presentation.urls_admin')),
]
