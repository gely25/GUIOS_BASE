"""
Paquete de vistas de la capa de presentación - GUIOS PRO.

Reexporta las vistas y decoradores para que urls.py los importe de forma uniforme.
"""

from .access import home_view
from .administration import admin_home_view
from .decisor import decisor_home_view
from .preview import modulo_pendiente_view, require_debug_preview

__all__ = [
    'home_view',
    'decisor_home_view',
    'admin_home_view',
    'require_debug_preview',
    'modulo_pendiente_view',
]
