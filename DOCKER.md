# GUIOS PRO con Docker

Guía para levantar el proyecto con Docker Compose. La configuración está pensada para
desarrollo y demostración: usa el servidor de Django (`runserver`) y PostgreSQL 17 con
pgvector.

## Requisitos

- Docker Engine
- Docker Compose v2 (`docker compose`)

## Puesta en marcha

1. Crea el archivo de entorno si aún no existe:

   ```bash
   cp .env.example .env
   ```

2. Revisa en `.env` al menos `DJANGO_SECRET_KEY`, `DB_NAME`, `DB_USER` y `DB_PASSWORD`.
   `DB_HOST` y `DB_PORT` pueden quedar como están: Compose sobreescribe `DB_HOST=db`
   y `DB_PORT=5432` dentro de los contenedores.

3. Levanta la base de datos, la aplicación y el procesador de búsquedas:

   ```bash
   docker compose up --build -d
   ```

4. Comprueba el estado y los logs:

   ```bash
   docker compose ps
   docker compose logs -f web
   ```

5. Abre `http://localhost:8000/`.

## Cargar el catálogo y datos de prueba

La primera vez la base de datos está vacía. Ejecuta:

```bash
docker compose exec web python manage.py cargar_catalogo_guios
docker compose exec web python manage.py cargar_datos_demo
```

También puedes hacerlo automático al arrancar, añadiendo a `.env`:

```env
CARGAR_CATALOGO=1
CARGAR_DATOS_DEMO=1
```

Después puedes volver a `0` para no repetir la carga en cada reinicio.

## Búsquedas bibliográficas (HU02)

El servicio `worker` ejecuta `python manage.py procesar_busquedas` en bucle. Para verlo:

```bash
docker compose logs -f worker
```

## Pruebas

```bash
docker compose exec web python manage.py test
```

## Comandos útiles

```bash
# Reconstruir después de cambiar código o requirements.txt
docker compose up --build -d

# Abrir una shell de Django
docker compose exec web python manage.py shell

# Ver el estado de la base de datos
docker compose exec web python manage.py check_db

# Detener los contenedores (conserva los volúmenes)
docker compose down

# Detener y borrar también la base de datos y los archivos subidos
docker compose down -v
```

## Puertos y volúmenes

- `WEB_PORT` (por defecto `8000`): puerto público de la aplicación.
- `DB_PORT` (por defecto `5432` en `.env.example`): puerto del host para PostgreSQL.
  Cámbialo si ya tienes un PostgreSQL local usando ese puerto.
- `pgvector_data`: datos de PostgreSQL.
- `media_data`: documentos subidos en `media/`.
- `static_data`: archivos estáticos recolectados con `collectstatic`.

Si necesitas conservar los archivos de `media/` que ya tienes en local, cópialos al
volumen con el contenedor web en marcha:

```bash
docker compose cp ./media/. web:/app/media/
```

## Notas de producción

Esta configuración usa el servidor de desarrollo de Django. Para producción:

- Cambia `DJANGO_DEBUG=False` y configura `DJANGO_ALLOWED_HOSTS` y
  `DJANGO_CSRF_TRUSTED_ORIGINS` con tu dominio real.
- Sustituye `runserver` por Gunicorn (añadiéndolo a `requirements.txt`) o sirve la
  aplicación con un proxy inverso.
- Sirve `/static/` con WhiteNoise o Nginx; con `DEBUG=False` Django no sirve estáticos.
- Usa HTTPS y una `DJANGO_SECRET_KEY` aleatoria.
