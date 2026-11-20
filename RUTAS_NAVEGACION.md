# Rutas de navegación

Todas las pantallas exigen sesión y un rol. El control lo hace `PermisosPorRolMiddleware` con el catálogo
de `apps/business_rules/menu.py`: sin sesión redirige al login (`/?next=...`), con el rol equivocado da
**403**, y una ruta que no está en el catálogo se niega para todos.

Los módulos que todavía no se implementan muestran «Módulo no disponible».

## Rutas públicas

| Ruta | Nombre | Qué es |
|------|--------|--------|
| `/` | `presentation:home` | Inicio de sesión (correo y contraseña). Si ya hay sesión, lleva al inicio del rol |
| `/salir/` | `presentation:logout` | Cierra la sesión. Solo acepta POST |

## Administración (rol ADMINISTRADOR)

| Ruta | Nombre | Estado | Historia / responsable |
|------|--------|--------|------------------------|
| `/administracion/` | `admin-inicio` | maqueta de Usuarios y roles | HU01, Angely |
| `/administracion/usuarios-roles/` | `admin-usuarios-roles` | maqueta | HU01, Angely |
| `/administracion/actualizacion-bibliografica/` | `admin-actualizacion-bibliografica` | módulo no disponible | HU02, Merly |
| `/administracion/indicadores-literatura/` | `admin-indicadores-literatura` | **implementada** (datos simulados; sin opción en el menú, se abre por URL) | HU03/HU04, Angely |
| `/administracion/catalogo-metodologico/` | `admin-catalogo-metodologico` | módulo no disponible | por asignar |

## Espacio del Decisor (rol DECISOR)

| Ruta | Nombre | Estado | Historia / responsable |
|------|--------|--------|------------------------|
| `/decisor/` | `decisor-inicio` | maqueta de inicio | Angely (base) |
| `/decisor/ficha-inicial/` | `decisor-ficha-inicial` | implementada | HU05, Joseph |
| `/decisor/importancia-factores/` | `decisor-importancia-factores` | módulo no disponible | HU06, Angely |
| `/decisor/carga-documental/` | `decisor-carga-documental` | módulo no disponible | HU07, Jorge |
| `/decisor/revision-valoraciones/` | `decisor-revision-valoraciones` | módulo no disponible | HU11, Angely |
| `/decisor/resultados/` | `decisor-resultados` | módulo no disponible | HU14, Merly |
| `/decisor/informe/` | `decisor-informe` | módulo no disponible | HU14, Merly |
| `/decisor/historial-evaluaciones/` | `decisor-historial-evaluaciones` | módulo no disponible | HU15, Joseph |

La ruta `/admin/` es el panel de Django. No forma parte del flujo de la aplicación y solo lo abre un
usuario ADMINISTRADOR activo.

## Cómo implementar un módulo pendiente

1. La ruta ya está declarada en `apps/business_rules/menu.py` (catálogo) y en `urls_admin.py` o
   `urls_decisor.py` apuntando a `modulo_pendiente_view`.
2. Crea tu vista en `apps/presentation/views/` (solo pide datos a un servicio y renderiza). No necesita
   decorador de permisos: el middleware ya la protege con GET y POST.
3. En `urls_admin.py` o `urls_decisor.py`, cambia `modulo_pendiente_view` de esa ruta por tu vista y quita
   sus argumentos. **El `name` no cambia**, así el menú y los permisos siguen funcionando.
4. Pon la plantilla en `templates/presentation/<area>/`, siguiendo `decisor_home.html` o `admin_home.html`.
5. Quita la ruta de `PENDIENTES` en `apps/presentation/tests/test_rutas.py` y agrega tus pruebas.
6. Actualiza la tabla de arriba.

Si necesitas una ruta **nueva** (no una de la lista), agrégala primero al catálogo con su rol: si no, el
test `GuardianDeRutasTests` falla y la ruta queda denegada.
