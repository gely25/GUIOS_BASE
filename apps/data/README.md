# Capa de datos

PostgreSQL con pgvector.

- `migrations/0001_enable_vector_extension.py`: activa la extensión `vector`.
- `management/commands/check_db.py`: `python manage.py check_db` verifica conexión, versión y pgvector.

Los modelos del catálogo y de evaluaciones se agregan aquí. Al tenerlos, `cargar_datos_catalogo()`
(en `application/services/indicadores_literatura/`) se reemplaza por una lectura real.
