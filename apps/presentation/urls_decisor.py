"""
Rutas del Espacio del Decisor - GUIOS PRO.
"""

from django.urls import path
from .views import decisor_home_view, modulo_pendiente_view
from .views.preguntas import preguntas_view

urlpatterns = [
    path(
        '',
        decisor_home_view,
        name='decisor-inicio'
    ),
    path(
        'ficha-inicial/',
        modulo_pendiente_view,
        {
            'nombre_modulo': 'Ficha inicial de evaluación',
            'area': 'decisor',
            'referencia_figma': 'nodo 7:3102',
        },
        name='decisor-ficha-inicial'
    ),
    path(
        'importancia-factores/',
        modulo_pendiente_view,
        {
            'nombre_modulo': 'Importancia de factores',
            'area': 'decisor',
            'referencia_figma': 'nodo 7:3241',
            'descripcion_extra': 'Las dimensiones tecnológica, organizacional y económica pertenecen al mismo módulo.',
        },
        name='decisor-importancia-factores'
    ),
    path(
        'carga-documental/',
        modulo_pendiente_view,
        {
            'nombre_modulo': 'Carga documental',
            'area': 'decisor',
            'referencia_figma': 'nodo 7:3507',
        },
        name='decisor-carga-documental'
    ),
    path(
        'revision-valoraciones/',
        preguntas_view,
        name='decisor-revision-valoraciones'
    ),
    path(
        'resultados/',
        modulo_pendiente_view,
        {
            'nombre_modulo': 'Resultados',
            'area': 'decisor',
            'referencia_figma': 'nodo 7:4266',
        },
        name='decisor-resultados'
    ),
    path(
        'informe/',
        modulo_pendiente_view,
        {
            'nombre_modulo': 'Informe',
            'area': 'decisor',
            'referencia_figma': 'nodo 7:4464',
        },
        name='decisor-informe'
    ),
    path(
        'historial-evaluaciones/',
        modulo_pendiente_view,
        {
            'nombre_modulo': 'Historial de evaluaciones',
            'area': 'decisor',
            'referencia_figma': 'nodo 7:4609',
        },
        name='decisor-historial-evaluaciones'
    ),
]
