# Imagen de desarrollo/despliegue básico para GUIOS PRO.
# Python 3.12 + PostgreSQL con pgvector (el servidor de base de datos va en compose).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings \
    HOME=/app

WORKDIR /app

# Primero las dependencias para aprovechar la caché de Docker.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Código de la aplicación, con un usuario sin privilegios (UID/GID 1000).
COPY --chown=1000:1000 . .

# Carpetas que se montan como volúmenes para conservar datos entre reinicios.
RUN mkdir -p /app/staticfiles /app/media \
    && chown -R 1000:1000 /app/staticfiles /app/media

# El entrypoint queda fuera de /app para que un volumen no lo tape.
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER 1000:1000

EXPOSE 8000

# Comprueba que Django responde (lo usa compose para esperar antes del worker).
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=3)"

ENTRYPOINT ["entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]
