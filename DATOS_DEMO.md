# Datos de demostración

Usuarios de prueba para ver cada pantalla con su rol en **desarrollo local**. Sirven para comprobar el menú, la redirección al iniciar sesión y, desde el paso de permisos, el bloqueo entre roles.

> Estas contraseñas son públicas: están en el repositorio. No las uses fuera de una base de desarrollo.

## Usuarios

| Rol | Correo | Contraseña | Qué debe pasar |
|---|---|---|---|
| Administrador | `admin.demo@guios.local` | `Demo-Admin-123` | Entra a Administración y ve 3 opciones en el menú |
| Decisor | `decisor.demo@guios.local` | `Demo-Decisor-123` | Entra al Espacio del Decisor y ve 3 opciones |
| Decisor inactivo | `inactivo.demo@guios.local` | `Demo-Inactivo-123` | No entra: "Correo o contraseña incorrectos." |

Los tres pertenecen a la organización **Organización Demo**.

## Cómo cargarlos

Requisitos: entorno virtual activo, `.env` configurado y la base creada (ver `README.md`).

~~~
python manage.py migrate
python manage.py cargar_datos_demo
~~~

La salida lista cada usuario con su estado:

~~~
Usuarios de demostración:
  [creado] ADMINISTRADOR  admin.demo@guios.local       Demo-Admin-123
  [creado] DECISOR        decisor.demo@guios.local     Demo-Decisor-123
  [creado] DECISOR        inactivo.demo@guios.local    Demo-Inactivo-123  (inactivo)
~~~

- El comando es **repetible**: si el correo ya existe, actualiza sus datos y restablece su contraseña. Sirve para volver al estado de demo.
- Las migraciones crean `GUIOS-V1` como versión vigente del catálogo; no es necesario cargar datos demo para registrar una evaluación.
- El comando puede crear `GUIOS-DEMO-V1` en estado `DEMO`, pero nunca lo activa ni desplaza el catálogo vigente.
- **Solo corre en una base cuyo nombre termine en `_dev`** (por ejemplo `guios_pro_db_dev`). En cualquier otra se niega.

## Cómo probar cada rol

1. Arranca el servidor: `python manage.py runserver`.
2. En una ventana normal abre `http://127.0.0.1:8000/` e inicia sesión como **decisor**.
3. En una ventana de incógnito inicia sesión como **administrador**. Cada ventana tiene su propia sesión, así que se ven los dos roles a la vez.
4. Prueba el usuario **inactivo**: no debe poder entrar.
5. Cierra sesión con el botón "Cerrar sesión" de la barra superior (funciona por POST).

## Cuenta propia de administrador

Para tu usuario real (no demo) usa:

~~~
python manage.py createsuperuser
~~~

Pide correo, nombre y contraseña. La contraseña pasa por las validaciones de Django.

## Dónde está el código

- Comando: `apps/data/management/commands/cargar_datos_demo.py`
- Pruebas: `apps/data/tests/test_datos_demo.py`
