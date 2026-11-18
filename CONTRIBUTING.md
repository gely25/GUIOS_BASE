# Cómo colaborar en GUIOS PRO

Guía corta para el equipo. La puesta en marcha, la arquitectura y cómo agregar una pantalla están en
[`README.md`](README.md); las rutas y sus responsables, en [`RUTAS_NAVEGACION.md`](RUTAS_NAVEGACION.md).

## Flujo de trabajo

1. Actualiza tu copia: `git checkout main` y `git pull`.
2. Crea una rama por tarea, con nombre corto y claro:

~~~
git checkout -b hu05-ficha-inicial
~~~

3. Trabaja en tu rama y haz commits pequeños.
4. Antes de subir, corre toda la suite y verifica que pase:

~~~
python manage.py test
~~~

5. Sube la rama y abre un **Pull Request** hacia `main`. Otra persona del equipo lo revisa antes de unirlo.
6. **No se hace push directo a `main`.**

## Commits

- Mensaje en español, claro y específico: qué cambia y por qué se nota (por ejemplo,
  `HU05: ficha inicial de evaluacion con validacion de campos`).
- Un cambio por commit. Evita mensajes como "arreglos" o "cambios".
- **Sin líneas de coautoría ni atribución automática de herramientas** (`Co-Authored-By` u otras). El
  profesor permite usar IA como apoyo, pero no quiere que aparezca como contribuyente.

## Dónde va cada cosa

- **Cálculos** (IL, IS, IR, PM, FODA): `apps/business_rules/`, funciones puras sin Django. Las vistas y la IA
  nunca calculan.
- **Casos de uso**: servicios en `apps/application/services/`. La vista solo pide datos al servicio y renderiza.
- **Base de datos**: modelos y migraciones en `apps/data/`. El esquema de 19 tablas está acordado con el
  grupo: antes de cambiar una tabla, avisa y acuerden el cambio. Cada cambio lleva su migración
  (`python manage.py makemigrations`). Si dos ramas crean migraciones a la vez, avisa para unirlas.
- **Pantallas nuevas**: sigue los pasos de "Cómo agregar una pantalla nueva" del README. Declara la ruta en
  `apps/business_rules/menu.py`; lo que no está allí queda denegado.

## Antes de pedir revisión

- [ ] `python manage.py test` pasa completo.
- [ ] Hay pruebas para lo que agregaste o cambiaste.
- [ ] No subiste `.env`, contraseñas, claves ni archivos temporales (`git status` limpio de cosas ajenas).
- [ ] Los archivos están en UTF-8 sin BOM (el test `test_codificacion.py` lo verifica).
- [ ] No quitaste ni evitaste el middleware de permisos, ni usaste `@csrf_exempt`.
- [ ] Actualizaste la documentación si cambió una ruta, una HU o un comando.

## Datos de prueba

`python manage.py cargar_datos_demo` crea un administrador, un decisor y un decisor inactivo en tu base de
desarrollo. Detalles en [`DATOS_DEMO.md`](DATOS_DEMO.md). Esas cuentas son públicas: no las uses fuera de
una base `_dev`.
