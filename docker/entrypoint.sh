#!/bin/sh
# Entrypoint común para los contenedores web y worker.
set -eu

wait_for_db() {
    [ "${WAIT_FOR_DB:-1}" = "1" ] || return 0

    echo "Esperando a PostgreSQL..."
    intentos=0
    until python manage.py check_db >/dev/null 2>&1; do
        intentos=$((intentos + 1))
        if [ "$intentos" -ge 30 ]; then
            echo "No se pudo conectar a PostgreSQL después de 60 segundos." >&2
            exit 1
        fi
        sleep 2
    done
    echo "PostgreSQL disponible."
}

wait_for_db

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "Aplicando migraciones..."
    python manage.py migrate --noinput
fi

if [ "${RUN_COLLECTSTATIC:-1}" = "1" ]; then
    echo "Recolectando archivos estáticos..."
    python manage.py collectstatic --noinput
fi

if [ "${CARGAR_CATALOGO:-0}" = "1" ]; then
    echo "Cargando catálogo GUIOS..."
    python manage.py cargar_catalogo_guios
fi

if [ "${CARGAR_DATOS_DEMO:-0}" = "1" ]; then
    echo "Cargando datos de demostración..."
    python manage.py cargar_datos_demo
fi

exec "$@"
