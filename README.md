# GUIOS PRO

Sistema de apoyo a la decisión para la adopción de software FLOSS, basado en la metodología GUIOS.
Proyecto final del curso (UNEMI). Django 5.2 + PostgreSQL 17 con pgvector.

Documentos del proyecto: [`RUTAS_NAVEGACION.md`](RUTAS_NAVEGACION.md) (pantallas y responsables),
[`DATOS_DEMO.md`](DATOS_DEMO.md) (usuarios de prueba), [`CONTRIBUTING.md`](CONTRIBUTING.md) (cómo colaborar).

## Puesta en marcha (Windows / PowerShell)

Instala Python 3.12 y PostgreSQL 17 con la extensión pgvector disponible en el servidor. Ejecuta desde la raíz del repositorio.

~~~powershell
py -3.12 -m venv venv  # solo al instalar
.\venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
psql -h localhost -U postgres -c "CREATE DATABASE guios_pro_ai_dev;"  # solo para una base nueva
~~~

Configura `DB_NAME=guios_pro_ai_dev`, `DB_HOST=localhost`, usuario y contraseña de PostgreSQL en `.env`. Comprueba el destino local antes de aplicar migraciones.

~~~powershell
.\venv\Scripts\python.exe manage.py check_db
.\venv\Scripts\python.exe manage.py migrate --plan
.\venv\Scripts\python.exe manage.py migrate  # instalación nueva; habilita vector en la base
.\venv\Scripts\python.exe manage.py cargar_catalogo_guios
.\venv\Scripts\python.exe manage.py cargar_datos_demo  # opcional, para una base de demostración
~~~

Para actualizar una instalación local de esta rama que ya tiene 0015, respalda la base y revisa el plan de 0016/0017 antes de aplicarlo con el script protegido.

~~~powershell
.\scripts\ia-local.ps1 -Accion Plan
.\scripts\ia-local.ps1 -Accion Migrar
~~~

### Piloto de IA y workers

El perfil local usa Gemini 3.5 Flash-Lite y Cloudflare Llama 3.3 70B en sus niveles gratuitos. Configura en `.env` `GUIOS_AI_GEMINI_API_KEY`, `GUIOS_AI_GEMINI_MODEL`, `GUIOS_AI_CLOUDFLARE_API_KEY` (alias `GUIOS_AI_CLOUDFLARE_API_TOKEN`), `GUIOS_AI_CLOUDFLARE_ACCOUNT_ID` y `GUIOS_AI_CLOUDFLARE_MODEL`. Usa exactamente los modelos del perfil. Confirma en cada cuenta que no admite cobros ni excedentes y crea `autorizacion-gratuita.json` según el esquema documentado. Conserva el manifiesto, las claves y los datos de prueba fuera de Git. [Perfil local](config/ia-local.json) · [Esquema de autorización](docs/PLAN_IMPLEMENTACION.md#ejecutar-el-benchmark-aislado)

~~~powershell
.\scripts\ia-local.ps1 -Accion Configurar
.\scripts\ia-local.ps1 -Accion Cuotas
.\scripts\ia-local.ps1 -Accion Django
~~~

Abre `http://127.0.0.1:8000/`. Desde la raíz, inicia cada worker en su propia terminal PowerShell con el mismo perfil.

~~~powershell
.\scripts\ia-local.ps1 -Accion Busquedas   # HU02, cola de búsquedas OpenAlex
.\scripts\ia-local.ps1 -Accion Worker      # HU09, cola de suficiencia
~~~

En HU02, el administrador abre el detalle de una búsqueda completada y solicita el análisis. En HU09, el decisor encola el lote desde Preguntas y espera su finalización. La pantalla habilita HU10 al recibir el estado final. Las propuestas se revisan y se confirman manualmente en HU11. Para iniciar solo la web, usa `.\venv\Scripts\python.exe manage.py runserver`. La IA permanece inactiva si falta la configuración autorizada.

### Verificaciones sin inferencia

~~~powershell
.\venv\Scripts\python.exe manage.py test --noinput
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py migrate --plan
~~~

El usuario de PostgreSQL necesita crear la base de pruebas y habilitar pgvector en ella.

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

El registro público crea cuentas de Decisor. Los administradores se incorporan desde la gestión autenticada de usuarios o mediante la carga local de datos de demostración para el piloto. Limitar los intentos de acceso sigue siendo una tarea de despliegue.

## Actualización bibliográfica (HU02)

Flujo del administrador en `/administracion/actualizacion-bibliografica/`:

1. **Buscar literatura 2020–2025**: deja en cola una búsqueda por factor activo (`busqueda_bibliografica`).
   La consulta combina contexto FLOSS + «adoption» + términos en inglés del factor
   (`business_rules/glosario_bibliografico.py`). Fuente: OpenAlex (`external_services/bibliografia/`).
2. **`python manage.py procesar_busquedas`** ejecuta la cola en segundo plano (la interfaz muestra el
   progreso) y guarda publicaciones sin duplicar (DOI o título+año).
3. **Analizar con IA**: desde el detalle de una búsqueda completada, el administrador puede pedir a la IA
   que evalúe las publicaciones recuperadas para el factor y explique cada sugerencia. El análisis es a demanda.
4. **Revisar**: el administrador aprueba o rechaza cada sugerencia o vincula a mano. Solo lo aprobado cuenta.
5. **Recalcular**: crea un borrador de catálogo con `TC = TC GUIOS 2021 + publicaciones aprobadas de
   2020–2025`, y r_i, IL e IS recalculados (`business_rules/rules_engine.py`).
6. **Publicar**: el borrador pasa a ACTIVO y la versión anterior a HISTORICO. Las evaluaciones guardan
   su versión, así que no cambian.

OpenAlex tiene cupo propio. Configura `BIBLIOGRAPHIC_API_KEY` y consulta las opciones de búsqueda en `.env.example`.
PostgreSQL coordina las cuotas de IA y permite concurrencia en lotes o subfactores independientes. Cada tarea tiene un único intento activo y el fallback es secuencial. Usa únicamente evidencia que la cuenta autorizada pueda tratar según sus condiciones de uso. El [plan de implementación](docs/PLAN_IMPLEMENTACION.md) recoge las mediciones, la recuperación manual y los límites operativos.

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
| HU01 Acceso y roles (antes José) | `data/models/usuarios.py`, `business_rules/menu.py`, `presentation/` | Acceso, permisos por rol y gestión de usuarios. Registro público limitado a Decisor |
| HU03 / HU04 Indicadores IL e IS | `business_rules/il.py`, `is_.py`, `application/services/indicadores_literatura/` | Hecho (lee la versión activa del catálogo) |
| HU06 Importancia relativa (IR) | `business_rules/ir.py`, `application/services/importancia.py` | Hecho: pantalla de valoración de factores (ID, IR, exclusión de IR = 1) |
| HU09 Preguntas por información faltante (antes José) | `application/services/lotes_hu09.py`, `suficiencia.py` | Implementada. Piloto real de dos subfactores |
| HU11 Revisión humana de valoraciones (antes José) | `application/services/revision_humana.py` | Confirmación humana y trazabilidad exigidas para resultados |
| HU12 PM y FODA | `business_rules/pm.py`, `foda.py`, `application/services/pm_foda.py` | Hecho: se calculan y guardan en la pantalla de Resultados. Falta la recomendación (HU13) y el informe (HU14). Ver `HU12_RESULTADOS.md` |

### Jorge

| Historia | Dónde se implementa | Estado |
|----------|---------------------|--------|
| HU07 Documentos | `application/services/document.py` | Pendiente |
| HU08 Recuperación de evidencia | `application/services/retrieval.py` (pgvector) | Pendiente |
| HU10 IA | `application/services/ai.py` | Implementada. Dos propuestas del piloto pendientes de HU11 |

### Joseph

| Historia | Dónde se implementa | Estado |
|----------|---------------------|--------|
| HU05 Catálogo y evaluaciones | `application/services/catalog.py`, `evaluation.py` | Pendiente |
| HU13 Recomendación | `application/services/recomendacion.py` | Hecho: regla versionada 1.0 basada en conteos FODA e IR; bloqueo si faltan valoraciones confirmadas |
| HU15 Historial | `application/services/historial.py`, `presentation/views/historial.py` | Hecho: listado privado por decisor, estados, recomendaciones y enlaces a resultados e informe |

### Merly

| Historia | Dónde se implementa | Estado |
|----------|---------------------|--------|
| HU02 Actualización bibliográfica | `application/services/actualizacion_bibliografica/`, `business_rules/rules_engine.py`, `external_services/bibliografia/` | OpenAlex, sugerencias de IA verificadas en el piloto y revisión manual |
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
