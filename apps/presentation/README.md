# Capa de presentación

Vistas, plantillas, estáticos y rutas. Solo pide datos a los servicios de `application` y los muestra:
no calcula ni accede a la base de datos.

- `views/`: una vista por pantalla (`access.py`, `literatura.py`, `preview.py`).
- `urls.py` y `urls_admin.py`: rutas. Las del decisor irán en `urls_decisor.py`.
- `templates/presentation/`: `layouts/`, `includes/`, `acceso/`, `administracion/`, `decisor/`, `comun/`.
- `static/presentation/css/style.css`: estilos globales.
- `tests/`: pruebas de las vistas.
