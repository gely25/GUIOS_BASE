"""Configuración de la capa de datos (modelos, migraciones y pgvector)."""

from django.apps import AppConfig


class DataConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.data'
    verbose_name = 'Capa de Datos'