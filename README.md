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
python manage.py cargar_catalogo_guios  # catálogo GUIOS 2021 (versión v1-2021)
python manage.py cargar_datos_demo   # usuarios de prueba (solo bases terminadas en _dev)
python manage.py test                # toda la suite debe pasar
python manage.py runserver
python manage.py procesar_busquedas  # en otra terminal: ejecuta las búsquedas bibliográficas (HU02)
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

## Actualización bibliográfica (HU02)

Flujo del administrador en `/administracion/actualizacion-bibliografica/`:

1. **Buscar literatura 2020–2025**: deja en cola una búsqueda por factor activo (`busqueda_bibliografica`).
   La consulta combina contexto FLOSS + «adoption» + términos en inglés del factor
   (`business_rules/glosario_bibliografico.py`). Fuente: OpenAlex (`external_services/bibliografia/`).
2. **`python manage.py procesar_busquedas`** ejecuta la cola en segundo plano (la interfaz muestra el
   progreso). Guarda publicaciones sin duplicar (DOI o título+año) y sugiere factores por palabras clave
   (`business_rules/coincidencia.py`). Sin IA.
3. **Revisar**: el administrador aprueba o rechaza cada sugerencia o vincula a mano. Solo lo aprobado cuenta.
4. **Recalcular**: crea un borrador de catálogo con `TC = TC GUIOS 2021 + publicaciones aprobadas de
   2020–2025`, y r_i, IL e IS recalculados (`business_rules/rules_engine.py`).
5. **Publicar**: el borrador pasa a ACTIVO y la versión anterior a HISTORICO. Las evaluaciones guardan
   su versión, así que no cambian.

Variables opcionales en `.env`: `BIBLIOGRAPHIC_API_KEY` (key gratuita de OpenAlex con cupo propio),
`BIBLIOGRAPHIC_BASE_URL`, `BIBLIOGRAPHIC_TIMEOUT`, `BIBLIOGRAPHIC_MAX_RESULTADOS`.

Nota: el TC de 2021 pudo incluir artículos de 2020–2021 que la búsqueda vuelva a encontrar; como no
existe la lista de referencias original, el administrador debe tenerlo en cuenta al aprobar.

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
      bibliographic.py          BibliographicService (HU02 y HU03)
      actualizacion_bibliografica/  búsquedas, revisión y versiones del catálogo (HU02)
      indicadores_literatura/   modelos, fuente_catalogo, servicio (HU03)
      ai.py catalog.py document.py evaluation.py report.py retrieval.py
    tests/
  data/
    models/                     usuarios, catalogo, evaluaciones, bibliografia, documentos, resultados
    repositorios/               consultas ORM que usan los servicios (catalogo, bibliografia)
    semillas/guios_2021/        catálogo GUIOS 2021 (TSV) para cargar_catalogo_guios
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
  `indicadores_literatura/`, que lee la versión activa del catálogo en PostgreSQL.
- **Plantillas por área**: `layouts/`, `includes/` (fragmentos reutilizables), `acceso/`,
  `administracion/`, `decisor/`, `comun/`. Las páginas van bajo `presentation/...`.
- **Pruebas**: carpeta `tests/` dentro de cada capa. Antes de subir cambios, `python manage.py test` debe pasar.
- **Codificación**: archivos en UTF-8 **sin BOM** (ver `.editorconfig`). PowerShell 5 agrega BOM con
  `Set-Content -Encoding utf8`; usa PowerShell 7 o un editor, o el test `test_codificacion.py` te avisará.
- **Commits**: mensaje claro en español, un cambio por commit. Sin líneas de coautoría automáticas.

## Historias de usuario

Cada persona tiene su tabla. «Dónde» indica el archivo principal de la historia.

### Angely (líder)

| Historia | Dónde se implementa | Estado |
|----------|---------------------|--------|
| HU01 Acceso y roles (antes José) | `data/models/usuarios.py`, `business_rules/menu.py`, `presentation/` | Acceso, roles, menú y permisos: hecho. Gestión de usuarios: pendiente |
| HU03 / HU04 Indicadores IL e IS | `business_rules/il.py`, `is_.py`, `application/services/indicadores_literatura/` | Hecho (lee la versión activa del catálogo) |
| HU06 Importancia relativa (IR) | `business_rules/ir.py`, `application/services/importancia.py` | Hecho: pantalla de valoración de factores (ID, IR, exclusión de IR = 1) |
| HU09 Preguntas por información faltante (antes José) | `application/services/ai.py` | Pendiente |
| HU11 Revisión humana de valoraciones (antes José) | `application/services/evaluation.py` | Pendiente |
| HU12 PM y FODA | `business_rules/pm.py`, `foda.py`, `application/services/pm_foda.py` | Hecho: se calculan y guardan en la pantalla de Resultados. Falta la recomendación (HU13) y el informe (HU14). Ver `HU12_RESULTADOS.md` |

### Jorge

| Historia | Dónde se implementa | Estado |
|----------|---------------------|--------|
| HU07 Documentos | `application/services/document.py` | Pendiente |
| HU08 Recuperación de evidencia | `application/services/retrieval.py` (pgvector) | Pendiente |
| HU10 IA | `application/services/ai.py` | Pendiente |

### Joseph

| Historia | Dónde se implementa | Estado |
|----------|---------------------|--------|
| HU05 Catálogo y evaluaciones | `application/services/catalog.py`, `evaluation.py` | Pendiente |
| HU13 Recomendación | `application/services/recomendacion.py` | Hecho: regla versionada 1.0 basada en conteos FODA e IR; bloqueo si faltan valoraciones confirmadas |
| HU15 Historial | `application/services/historial.py`, `presentation/views/historial.py` | Hecho: listado privado por decisor, estados, recomendaciones y enlaces a resultados e informe |

### Merly

| Historia | Dónde se implementa | Estado |
|----------|---------------------|--------|
| HU02 Actualización bibliográfica | `application/services/actualizacion_bibliografica/`, `business_rules/rules_engine.py`, `external_services/bibliografia/` | Hecho sin IA (OpenAlex + sugerencias por palabras clave + revisión manual) |
| HU14 Informe | `application/services/report.py` | Pendiente |

## Estado

- Base, configuración, PostgreSQL con pgvector, estructura por capas y modelo de datos (19 tablas): listos.
- Acceso, roles, menú por rol y permisos por ruta (HU01): listos y probados.
- HU03 (IL e IS): lógica validada contra el caso de referencia de la metodología GUIOS y pantalla en
  `/administracion/indicadores-literatura/` con la versión activa del catálogo.
- HU06 (IR) y HU12 (PM, FODA): lógica, servicio y pantalla listos y probados; HU12 validada con el caso de referencia de LibreOffice. Cómo verlo: `HU12_RESULTADOS.md`.
- HU02: búsqueda en OpenAlex (2020–2025), revisión de vínculos y nueva versión del catálogo con
  TC = TC GUIOS 2021 + publicaciones aprobadas. Ver «Actualización bibliográfica (HU02)».

## Fundamento metodológico

La metodología GUIOS define los indicadores (IL, IS, IR, PM y FODA). Los valores esperados de las
pruebas de `apps/business_rules/tests/` provienen de la evaluación de referencia de esa metodología
(caso LibreOffice) y quedan documentados en cada prueba.

Fuente: tesis base de la metodología GUIOS.

Datos que HU12 entrega a la recomendación (HU13) y al informe (HU14): `INTEGRACION_HU12_HU13.md`.