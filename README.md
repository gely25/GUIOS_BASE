# GUIOS PRO

Sistema de apoyo a la decisión para la adopción de software FLOSS, basado en la metodología GUIOS.
Proyecto final del curso (UNEMI). Django 5.2 + PostgreSQL 17 con pgvector.

Documentos del proyecto: [`RUTAS_NAVEGACION.md`](RUTAS_NAVEGACION.md) (pantallas y responsables),
[`DATOS_DEMO.md`](DATOS_DEMO.md) (usuarios de prueba), [`CONTRIBUTING.md`](CONTRIBUTING.md) (cómo colaborar).

## Puesta en marcha (Windows / PowerShell)

Requisitos: Python 3.12, PostgreSQL 17 con la extensión **pgvector** instalada en el servidor.

~~~powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env          # luego edita .env con tus datos
psql -U postgres -c "CREATE DATABASE guios_pro_db_dev;"
python manage.py check_db            # comprueba PostgreSQL y pgvector
python manage.py migrate
python manage.py cargar_datos_demo   # usuarios de prueba (solo bases terminadas en _dev)
python manage.py test                # toda la suite debe pasar
python manage.py runserver
~~~

Abre `http://127.0.0.1:8000/` e inicia sesión con un usuario de [`DATOS_DEMO.md`](DATOS_DEMO.md).

El archivo `.env` es local y **nunca se sube** a Git. Las variables están descritas en `.env.example`.
Si falta una variable obligatoria, `settings.py` indica cuál es.

## Acceso y roles (HU01)

- El usuario inicia sesión con **correo y contraseña** (modelo `Usuario`, tabla `usuario`).
- Hay dos roles, guardados en `usuario.rol`: `ADMINISTRADOR` y `DECISOR`. El rol **no se elige** al entrar.
- El menú lateral se dibuja desde un catálogo en código: `apps/business_rules/menu.py`.
- Los permisos los aplica `PermisosPorRolMiddleware` (`apps/presentation/middleware.py`) a **todas** las
  rutas de `presentation`, con GET y POST, usando ese mismo catálogo:
  - sin sesión: redirige al login con `?next=`;
  - rol equivocado: página 403;
  - ruta que no está en el catálogo: **403 para todos** (lo no declarado se niega).
- Cerrar sesión es un POST a `/salir/` (botón en la barra superior).
- Los mensajes de error del login son genéricos: no revelan si el correo existe.

Pendiente de HU01: pantalla de gestión de usuarios y roles (hoy es una maqueta) y límite de intentos
fallidos de login.

## Arquitectura por capas

Cada capa solo habla con la de abajo. La interfaz nunca toca la base de datos ni calcula;
la IA nunca hace cálculos.

~~~
presentation  ->  application (servicios)  ->  business_rules (cálculos puros)
                                           ->  data (PostgreSQL + pgvector)
                                           ->  servicios externos
~~~

| Capa | Carpeta | Qué contiene |
|------|---------|--------------|
| Presentación | `apps/presentation/` | Vistas, plantillas, estáticos, rutas, middleware de permisos. No calcula. |
| Aplicación | `apps/application/services/` | Servicios que orquestan casos de uso. |
| Reglas de negocio | `apps/business_rules/` | IL, IS, IR, PM, FODA y el catálogo de roles/menú. Python puro, sin Django. |
| Datos | `apps/data/` | Modelos (19 tablas), migraciones y comandos de base de datos. |

~~~
config/                         settings, urls, wsgi
apps/
  business_rules/               cálculos puros, menu.py (catálogo y permisos) + tests/
  application/
    services/
      bibliographic.py          BibliographicService
      indicadores_literatura/   modelos, fuente_simulada, servicio (HU03)
      ai.py catalog.py document.py evaluation.py report.py retrieval.py
    tests/
  data/
    models/                     usuarios, catalogo, evaluaciones, bibliografia, documentos, resultados
    management/commands/        check_db, cargar_datos_demo
    migrations/  tests/
  presentation/
    views/  urls.py  urls_admin.py  urls_decisor.py
    middleware.py  forms.py  context_processors.py  screens.py
    templates/presentation/     layouts/ includes/ acceso/ administracion/ decisor/ comun/
    static/presentation/css/
    tests/
  test_codificacion.py          falla si algún archivo de texto trae BOM
~~~

## Cómo agregar una pantalla nueva

1. **Declárala en el catálogo**: `apps/business_rules/menu.py` (`CATALOGO`) con su `ruta`, etiqueta,
   ícono, rol y si aparece en el menú. Sin esto queda denegada para todos.
2. **Conecta la ruta**: en `urls_admin.py` o `urls_decisor.py`, cambia `modulo_pendiente_view` por tu vista y
   quita sus argumentos. El `name` debe ser el mismo que pusiste en el catálogo.
3. **Crea la vista** en `apps/presentation/views/`: solo pide datos a un servicio y renderiza. No hace falta
   ningún decorador de permisos; el middleware ya la protege (GET y POST).
4. **Crea la plantilla** en `templates/presentation/<area>/`, siguiendo `decisor_home.html` o `admin_home.html`
   (incluyen `app_sidebar.html` y `app_topbar.html`).
5. **Pruebas**: quita la ruta de `PENDIENTES` en `tests/test_rutas.py` y agrega las tuyas.
   El test `GuardianDeRutasTests` falla si una ruta no está en el catálogo.

## Convenciones

- **Servicios**: cada archivo de `application/services/` expone una clase como punto de entrada
  (por ejemplo `BibliographicService`). Si necesita varios archivos, sus detalles van en un subpaquete
  con el tema (como `indicadores_literatura/`).
- **Reglas de negocio**: funciones puras, sin importar Django ni acceder a la base de datos.
  Reciben datos y devuelven resultados, así se prueban sin infraestructura.
- **Un único punto de acceso a datos por servicio**: por ejemplo `cargar_datos_catalogo()` en
  `indicadores_literatura/`. Hoy usa datos simulados y es lo único que se cambia al leer de PostgreSQL.
- **Plantillas por área**: `layouts/`, `includes/` (fragmentos reutilizables), `acceso/`,
  `administracion/`, `decisor/`, `comun/`. Las páginas van bajo `presentation/...`.
- **Pruebas**: carpeta `tests/` dentro de cada capa. Antes de subir cambios, `python manage.py test` debe pasar.
- **Codificación**: archivos en UTF-8 **sin BOM** (ver `.editorconfig`). PowerShell 5 agrega BOM con
  `Set-Content -Encoding utf8`; usa PowerShell 7 o un editor, o el test `test_codificacion.py` te avisará.
- **Commits**: mensaje claro en español, un cambio por commit. Sin líneas de coautoría automáticas.

## Historias de usuario

| Historia | Responsable | Dónde se implementa | Estado |
|----------|-------------|---------------------|--------|
| HU01 Acceso y roles | Angely (antes José) | `data/models/usuarios.py`, `business_rules/menu.py`, `presentation/` | Acceso, roles, menú y permisos: hecho. Gestión de usuarios: pendiente |
| HU02 Actualización bibliográfica | Merly | `application/services/bibliographic.py` y `data/` | Pendiente |
| HU03 / HU04 Indicadores IL e IS | Angely | `business_rules/il.py`, `is_.py` y `application/services/indicadores_literatura/` | Hecho (datos simulados) |
| HU05 Catálogo y evaluaciones | Joseph | `catalog.py`, `evaluation.py` | Pendiente |
| HU06 IR (ID e IS, excluye IR=1) | Angely | `business_rules/ir.py` | Lógica lista; falta servicio y pantalla |
| HU07 Documentos | Jorge | `document.py` | Pendiente |
| HU08 Recuperación de evidencia | Jorge | `retrieval.py` (pgvector) | Pendiente |
| HU09 Preguntas por información faltante | Angely (antes José) | `ai.py` | Pendiente |
| HU10 IA | Jorge | `ai.py` | Pendiente |
| HU11 Revisión humana de valoraciones | Angely (antes José) | `evaluation.py` | Pendiente |
| HU12 PM y FODA | Angely | `business_rules/pm.py`, `foda.py` | Lógica lista y validada; falta servicio y pantalla |
| HU13 Recomendación | Joseph | `evaluation.py` | Pendiente |
| HU14 Informe | Merly | `report.py` | Pendiente |
| HU15 Historial | Joseph | `evaluation.py` | Pendiente |

## Estado

- Base, configuración, PostgreSQL con pgvector, estructura por capas y modelo de datos (19 tablas): listos.
- Acceso, roles, menú por rol y permisos por ruta (HU01): listos y probados.
- HU03 (IL e IS): lógica validada contra la Tabla 5.3 de la tesis y pantalla en
  `/administracion/indicadores-literatura/` con datos simulados.
- HU06 (IR) y HU12 (PM, FODA): lógica lista y probada en `business_rules/`; HU12 validada con la Figura 6.5 de la tesis.
- Lectura real de citas (TC) desde PostgreSQL: pendiente de los datos de HU02.
