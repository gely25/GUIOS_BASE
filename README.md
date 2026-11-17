# GUIOS PRO

Sistema de apoyo a la decisión para la adopción de software FLOSS, basado en la metodología GUIOS.
Proyecto final del curso (UNEMI). Django 5.2 + PostgreSQL 17 con pgvector.

## Puesta en marcha (Windows / PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env        # luego edita .env con tus datos
python manage.py check_db          # comprueba PostgreSQL y pgvector
python manage.py migrate
python manage.py test
python manage.py runserver
```

El archivo `.env` es local y **nunca se sube** a Git. Las variables están descritas en `.env.example`.
Si falta una variable obligatoria, `settings.py` indica cuál es.

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
| Presentación | `apps/presentation/` | Vistas, plantillas, estáticos y rutas. No calcula. |
| Aplicación | `apps/application/services/` | Servicios que orquestan casos de uso. |
| Reglas de negocio | `apps/business_rules/` | IL, IS, IR, PM, FODA. Python puro, sin Django. |
| Datos | `apps/data/` | Modelos, migraciones y comandos de base de datos. |

~~~
config/                         settings, urls, wsgi
apps/
  business_rules/               cálculos puros + tests/
  application/
    services/
      bibliographic.py          BibliographicService
      indicadores_literatura/   modelos, fuente_simulada, servicio (HU03)
      ai.py catalog.py document.py evaluation.py report.py retrieval.py
    tests/
  data/
    management/commands/        check_db
    migrations/
  presentation/
    views/  urls.py  urls_admin.py
    templates/presentation/     layouts/ includes/ acceso/ administracion/ decisor/ comun/
    static/presentation/css/
    tests/
~~~

## Convenciones de organización

- **Servicios**: cada archivo de `application/services/` expone una clase como punto de entrada
  (por ejemplo `BibliographicService`). Si el servicio necesita varios archivos, sus detalles van en un
  subpaquete con el tema (como `indicadores_literatura/`).
- **Reglas de negocio**: funciones puras, sin importar Django ni acceder a la base de datos.
  Reciben datos y devuelven resultados, así se prueban sin infraestructura.
- **Un único punto de acceso a datos por servicio**: por ejemplo `cargar_datos_catalogo()` en
  `indicadores_literatura/`. Hoy usa datos simulados y es lo único que se cambia al leer de PostgreSQL.
- **Plantillas por área**: `layouts/`, `includes/` (fragmentos reutilizables), `acceso/`,
  `administracion/`, `decisor/`, `comun/`. Las páginas van bajo `presentation/...`.
- **Pruebas**: carpeta `tests/` dentro de cada capa. Antes de subir cambios, `python manage.py test` debe pasar.
- **Vistas previas**: las rutas bajo `vista-previa/` solo existen con `DEBUG=True`; en producción dan 404.
- **Commits**: mensaje claro en español, un cambio por commit. Sin líneas de coautoría automáticas.
- **Subcarpeta por tema**: solo cuando hay varios archivos del mismo tema.

## Dónde va cada historia de usuario

| Historia | Dónde implementarla |
|----------|---------------------|
| HU02 Actualización bibliográfica | `application/services/bibliographic.py` y `data/` |
| HU03 Indicadores IL / IS | `business_rules/il.py`, `is_.py` y `application/services/indicadores_literatura/` (hecho) |
| HU05 Catálogo y evaluaciones | `catalog.py`, `evaluation.py` |
| HU06 IR (ID e IS, excluye IR=1) | `business_rules/ir.py` |
| HU07 Documentos | `document.py` |
| HU08 Recuperación de evidencia | `retrieval.py` (pgvector) |
| HU09 y HU10 IA | `ai.py` |
| HU11, HU13, HU15 Evaluación | `evaluation.py` |
| HU12 PM y FODA | `business_rules/pm.py`, `foda.py` |
| HU14 Informe | `report.py` |

## Estado

- Base, configuración, PostgreSQL con pgvector y estructura por capas: listos.
- HU03 (IL e IS): lógica validada contra la Tabla 5.3 de la tesis y vista previa en
  `/vista-previa/administracion/indicadores-literatura/` con datos simulados.
- HU06 (IR) y HU12 (PM, FODA): lógica lista y probada en `business_rules/`; HU12 validada con la Figura 6.5 de la tesis. Falta conectarlas a servicios y pantallas.
- Lectura real de citas (TC) desde PostgreSQL: pendiente de los datos de HU02.

Ver también `RUTAS_NAVEGACION.md`.

