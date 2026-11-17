"""
Rutas de vista previa del área de Administración - GUIOS PRO.

Cada historia de usuario agrega aquí su ruta cuando tenga vista.
"""

from django.urls import path

from .views.literatura import indicadores_literatura_view

urlpatterns = [
    path(
        'indicadores-literatura/',
        indicadores_literatura_view,
        name='admin-indicadores-literatura',
    ),
]
