# Capa de datos

PostgreSQL 17 con pgvector. Aquí viven los modelos del esquema acordado por el grupo (19 tablas).

- `models/`: `usuarios.py` (Organizacion y Usuario, con login por correo y rol), `catalogo.py`,
  `evaluaciones.py`, `bibliografia.py`, `documentos.py` y `resultados.py`.
- `migrations/0001_initial.py`: activa la extensión `vector` (`VectorExtension`) y crea las 19 tablas.
  `usuario` va en la primera migración porque es el modelo de usuario del proyecto (`AUTH_USER_MODEL`).
- `management/commands/check_db.py`: `python manage.py check_db` verifica conexión, versión y pgvector.
- `management/commands/cargar_datos_demo.py`: crea usuarios de prueba (ver `DATOS_DEMO.md`).
- `tests/`: pruebas de los modelos, sus restricciones y los datos de demostración.

Reglas para cambiar el esquema:

- Se acuerda con el grupo antes de tocar una tabla.
- Cada cambio lleva su migración nueva (`python manage.py makemigrations`); no se edita `0001_initial.py`.
- Si dos ramas crean migraciones a la vez, hay que unirlas antes de hacer merge.

Cuando existan los datos reales de HU02, `cargar_datos_catalogo()` (en
`application/services/indicadores_literatura/`) se reemplaza por una lectura de estas tablas.
