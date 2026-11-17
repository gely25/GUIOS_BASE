"""Configuración de la capa de presentación (vistas, plantillas y estáticos)."""

from django.apps import AppConfig


class PresentationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.presentation'
    verbose_name = 'Capa de Presentación'