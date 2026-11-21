# Capa de presentación

Vistas, plantillas, estáticos, rutas y control de acceso. Solo pide datos a los servicios de `application`
y los muestra: no calcula ni accede a la base de datos.

- `views/`: una vista por pantalla. `access.py` (login), `administration.py`, `decisor.py`,
  `literatura.py` (HU03), `bibliografia.py` (HU02) y `pendiente.py` (módulo «no disponible» para lo que aún no existe).
- `urls.py`: acceso (`/`, `/salir/`) e inclusión de las áreas. `urls_admin.py` (`/administracion/...`) y
  `urls_decisor.py` (`/decisor/...`): rutas de cada área.
- `middleware.py`: `PermisosPorRolMiddleware`. Aplica los permisos a todas las rutas (GET y POST) usando el
  catálogo de `business_rules/menu.py`. Sin sesión redirige al login; con el rol equivocado da 403; lo que no
  está en el catálogo se niega.
- `context_processors.py`: arma el menú lateral del rol y la URL de inicio.
- `forms.py`: formulario de acceso. `screens.py`: textos y datos de maqueta de las pantallas.
- `templates/presentation/`: `layouts/`, `includes/`, `acceso/`, `administracion/`, `decisor/`, `comun/`.
- `static/presentation/css/`: `style.css` (espacio de trabajo), `login.css` (acceso) y `estado.css` (403).
- `tests/`: pruebas de vistas, permisos por rol, menú lateral y acceso.

Para agregar una pantalla, ver «Cómo agregar una pantalla nueva» en el `README.md` principal.
