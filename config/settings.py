"""
Configuración de Django para el proyecto GUIOS PRO.

Arquitectura modular por capas:
- Presentación (apps.presentation)
- Aplicación (apps.application)
- Reglas de negocio (apps.business_rules)
- Servicios externos (apps.external_services)
- Datos (apps.data)

Los valores sensibles (clave secreta, base de datos) se leen del archivo .env.
Copia .env.example como .env y ajústalo en tu equipo.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Carga .env si existe (en desarrollo local).
load_dotenv(BASE_DIR / '.env')


def _obligatoria(nombre):
    """Devuelve la variable de entorno o falla con un mensaje claro."""
    valor = os.getenv(nombre)
    if not valor:
        raise ImproperlyConfigured(f"Define {nombre} en el archivo .env")
    return valor


def _booleana(nombre, defecto=False):
    valor = os.getenv(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in ('true', '1', 't', 'si', 'sí')


def _lista(nombre, defecto=''):
    return [item.strip() for item in os.getenv(nombre, defecto).split(',') if item.strip()]


# --- Seguridad --------------------------------------------------------------
SECRET_KEY = _obligatoria('DJANGO_SECRET_KEY')
DEBUG = _booleana('DJANGO_DEBUG', False)
ALLOWED_HOSTS = _lista('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = _lista('DJANGO_CSRF_TRUSTED_ORIGINS')

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = _booleana('DJANGO_SECURE_SSL_REDIRECT', False)

# --- Aplicaciones -----------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Soporte pgvector para Django
    'pgvector.django',

    # Capas del proyecto que son aplicaciones de Django.
    # application, business_rules y external_services son paquetes de Python
    # puros: no se registran aquí.
    'apps.data.apps.DataConfig',
    'apps.presentation.apps.PresentationConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'apps.presentation.middleware.PermisosPorRolMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# --- Plantillas -------------------------------------------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'apps' / 'presentation' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.presentation.context_processors.menu_lateral',
            ],
        },
    },
]

# --- Base de datos: PostgreSQL con pgvector ---------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': _obligatoria('DB_NAME'),
        'USER': _obligatoria('DB_USER'),
        'PASSWORD': _obligatoria('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# --- Contraseñas ------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internacionalización ---------------------------------------------------
LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'America/Guayaquil'
USE_I18N = True
USE_TZ = True

# --- Archivos estáticos -----------------------------------------------------
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'apps' / 'presentation' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
# --- Autenticación -----------------------------------------------------------
# Usuario propio: tabla `usuario` del esquema del grupo, con login por correo.
AUTH_USER_MODEL = 'data.Usuario'
LOGIN_URL = 'presentation:home'

# --- Actualización bibliográfica (HU02) ---------------------------------------
# Fuente científica: OpenAlex. La API key es opcional (sin ella se usa el cupo compartido).
BIBLIOGRAPHIC_BASE_URL = os.getenv('BIBLIOGRAPHIC_BASE_URL') or 'https://api.openalex.org'
BIBLIOGRAPHIC_API_KEY = os.getenv('BIBLIOGRAPHIC_API_KEY') or None
BIBLIOGRAPHIC_TIMEOUT = int(os.getenv('BIBLIOGRAPHIC_TIMEOUT') or 20)
# Máximo de publicaciones que se guardan por consulta (una consulta por factor).
BIBLIOGRAPHIC_MAX_RESULTADOS = int(os.getenv('BIBLIOGRAPHIC_MAX_RESULTADOS') or 50)

# HU09: proveedor local opcional; vacío conserva el modo manual.
HU09_OLLAMA_MODEL = os.getenv('HU09_OLLAMA_MODEL', '').strip()

# HU09: comparación semántica opcional; vacío mantiene el filtro textual.
HU09_EMBEDDING_MODEL = os.getenv('HU09_EMBEDDING_MODEL', '').strip()

# HU10: proveedor local para valoración preliminar (escala 1 a 4 con evidencia).
HU10_OLLAMA_MODEL = os.getenv('HU10_OLLAMA_MODEL', '').strip() or HU09_OLLAMA_MODEL

# --- IA generativa HU09/HU10: Ollama local o API HTTPS compatible -----------
# Por defecto se mantiene el comportamiento anterior (ollama).
GUIOS_AI_BACKEND = os.getenv('GUIOS_AI_BACKEND', 'ollama').strip().lower()
GUIOS_AI_API_KEY = os.getenv('GUIOS_AI_API_KEY', '').strip()
GUIOS_AI_MODEL = os.getenv('GUIOS_AI_MODEL', '').strip()
GUIOS_AI_BASE_URL = os.getenv('GUIOS_AI_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta/openai').strip()
GUIOS_AI_TIMEOUT = int(os.getenv('GUIOS_AI_TIMEOUT', '25'))
