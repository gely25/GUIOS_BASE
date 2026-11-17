# Rutas de navegación

| Ruta | Nombre | Qué muestra | Disponible |
|------|--------|-------------|------------|
| `/` | `presentation:home` | Pantalla de acceso | siempre |
| `/admin/` | — | Administración de Django | siempre |
| `/vista-previa/administracion/indicadores-literatura/` | `presentation:admin-indicadores-literatura` | Indicadores bibliográficos IL e IS (HU03) con datos simulados | solo `DEBUG=True` |

## Cómo agregar una ruta

1. Crea la vista en `apps/presentation/views/` (una vista solo pide datos a un servicio y renderiza).
2. Registra la ruta en `apps/presentation/urls_admin.py` (o en un `urls_decisor.py` si es del decisor)
   con un `name` que empiece por el área, por ejemplo `admin-...`.
3. Pon la plantilla en `templates/presentation/<area>/`.
4. Agrega el enlace en `includes/app_sidebar.html` (hoy los enlaces pendientes apuntan a `#`).
5. Agrega una prueba en `apps/presentation/tests/`.
