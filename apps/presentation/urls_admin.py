"""
Rutas de vista previa del área de Administración - GUIOS PRO.

Los módulos que todavía no existen muestran «Módulo no disponible».
Cuando una historia de usuario tenga su vista, reemplaza modulo_pendiente_view
por la vista real en esa ruta.
"""

from django.urls import path

from .views import admin_home_view, modulo_pendiente_view
from .views.literatura import indicadores_literatura_view

urlpatterns = [
    path('', admin_home_view, name='admin-inicio'),
    path('usuarios-roles/', admin_home_view, name='admin-usuarios-roles'),
    path(
        'actualizacion-bibliografica/',
        modulo_pendiente_view,
        {
            'nombre_modulo': 'Actualización bibliográfica',
            'area': 'administracion',
            'referencia_figma': 'nodo 7:5175',
        },
        name='admin-actualizacion-bibliografica',
    ),
    path('indicadores-literatura/', indicadores_literatura_view, name='admin-indicadores-literatura'),
    path(
        'catalogo-metodologico/',
        modulo_pendiente_view,
        {
            'nombre_modulo': 'Catálogo metodológico',
            'area': 'administracion',
            'referencia_figma': 'nodo 7:5516',
        },
        name='admin-catalogo-metodologico',
    ),
]
