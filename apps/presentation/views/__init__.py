"""
Paquete de vistas de la capa de presentación - GUIOS PRO.

Reexporta las vistas para que urls.py las importe de forma uniforme.
"""

from .access import home_view
from .administration import admin_home_view
from .decisor import decisor_home_view
from .pendiente import modulo_pendiente_view
from .evaluacion import evaluacion_inicial_view
from .historial import historial_evaluaciones_view

__all__ = [
    'home_view',
    'decisor_home_view',
    'admin_home_view',
    'modulo_pendiente_view',
    'evaluacion_inicial_view',
    'historial_evaluaciones_view',
]
