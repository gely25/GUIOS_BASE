"""
Rutas del Espacio del Decisor - GUIOS PRO.
"""
from .views.documentos import carga_documental_view
from django.urls import path
from .views import decisor_home_view, historial_evaluaciones_view
from .views.evaluacion import evaluacion_inicial_view
from .views.importancia import importancia_factores_view
from .views.preguntas import preguntas_view
from .views.documentos import carga_documental_view
from .views.informe import informe_view, resultados_view

urlpatterns = [
    path(
        '',
        decisor_home_view,
        name='decisor-inicio'
    ),
    path(
        'ficha-inicial/',
        evaluacion_inicial_view,
        name='decisor-ficha-inicial'
    ),
    path(
        'importancia-factores/',
        importancia_factores_view,
        name='decisor-importancia-factores'
    ),
    path(
        'carga-documental/',
        carga_documental_view,
        name='decisor-carga-documental'
    ),
    path(
        'revision-valoraciones/',
        preguntas_view,
        name='decisor-revision-valoraciones'
    ),
    path(
        'resultados/',
        resultados_view,
        name='decisor-resultados'
    ),
    path(
        'informe/',
        informe_view,
        name='decisor-informe'
    ),
    path(
        'historial-evaluaciones/',
        historial_evaluaciones_view,
        name='decisor-historial-evaluaciones'
    ),
]
