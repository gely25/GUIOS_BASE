# Rutas de navegación

Las rutas bajo `vista-previa/` solo existen con `DEBUG=True` (en producción dan 404).
Los módulos que todavía no se implementan muestran «Módulo no disponible».

| Ruta | Nombre | Estado | Historia / responsable |
|------|--------|--------|------------------------|
| `/` | `presentation:home` | acceso (esqueleto) | HU01, José |
| `/admin/` | — | Administración de Django | — |
| `/vista-previa/administracion/` | `admin-inicio` | maqueta de Usuarios y roles | HU01, José |
| `/vista-previa/administracion/usuarios-roles/` | `admin-usuarios-roles` | maqueta | HU01, José |
| `/vista-previa/administracion/actualizacion-bibliografica/` | `admin-actualizacion-bibliografica` | módulo no disponible | HU02, Merly |
| `/vista-previa/administracion/indicadores-literatura/` | `admin-indicadores-literatura` | **implementada** (datos simulados) | HU03/HU04, Angely |
| `/vista-previa/administracion/catalogo-metodologico/` | `admin-catalogo-metodologico` | módulo no disponible | por asignar |
| `/vista-previa/decisor/` | `decisor-inicio` | maqueta de inicio | — |
| `/vista-previa/decisor/ficha-inicial/` | `decisor-ficha-inicial` | módulo no disponible | HU05, Joseph |
| `/vista-previa/decisor/importancia-factores/` | `decisor-importancia-factores` | módulo no disponible | HU06, Angely |
| `/vista-previa/decisor/carga-documental/` | `decisor-carga-documental` | módulo no disponible | HU07, Jorge |
| `/vista-previa/decisor/revision-valoraciones/` | `decisor-revision-valoraciones` | módulo no disponible | HU11, José |
| `/vista-previa/decisor/resultados/` | `decisor-resultados` | módulo no disponible | HU14, Merly |
| `/vista-previa/decisor/informe/` | `decisor-informe` | módulo no disponible | HU14, Merly |
| `/vista-previa/decisor/historial-evaluaciones/` | `decisor-historial-evaluaciones` | módulo no disponible | HU15, Joseph |

## Cómo implementar un módulo pendiente

1. Crea la vista en `apps/presentation/views/` (solo pide datos a un servicio y renderiza).
2. En `urls_admin.py` o `urls_decisor.py`, cambia `modulo_pendiente_view` de esa ruta por tu vista y
   quita sus argumentos. El `name` de la ruta no cambia, así el menú sigue funcionando.
3. Pon la plantilla en `templates/presentation/<area>/`.
4. Quita la ruta de `PENDIENTES` en `apps/presentation/tests/test_rutas.py` y agrega tus pruebas.
5. Actualiza esta tabla.
