"""
Catálogo de módulos, menú por rol y decisión de acceso (HU01) - reglas de negocio puras.

Es la única fuente de verdad de qué pantalla existe, qué rol puede entrar y
cuáles aparecen en el menú lateral. No depende de Django: la capa de
presentación solo traduce cada `ruta` a una URL.

Regla de oro: lo que no está declarado aquí se niega.
"""

from dataclasses import dataclass

ADMINISTRADOR = 'ADMINISTRADOR'
DECISOR = 'DECISOR'

SECCION_POR_ROL = {
    ADMINISTRADOR: 'ADMINISTRACIÓN',
    DECISOR: 'ESPACIO DEL DECISOR',
}

INICIO_POR_ROL = {
    ADMINISTRADOR: 'admin-inicio',
    DECISOR: 'decisor-inicio',
}

# Rutas que no exigen sesión: el login y el cierre de sesión.
RUTAS_PUBLICAS = ('home', 'logout')

# Resultados de decidir_acceso.
PERMITIR = 'permitir'
PEDIR_LOGIN = 'pedir_login'
DENEGAR = 'denegar'


@dataclass(frozen=True)
class Modulo:
    ruta: str                 # nombre de la ruta en la app 'presentation'
    etiqueta: str
    icono: str
    roles: tuple
    en_menu: bool = True
    alias: tuple = ()         # otras rutas que dejan esta opción marcada como activa


CATALOGO = (
    # Administración
    Modulo('admin-inicio', 'Inicio administración', 'usuarios', (ADMINISTRADOR,), en_menu=False),
    Modulo('admin-usuarios-roles', 'Usuarios y roles', 'usuarios', (ADMINISTRADOR,),
           alias=('admin-inicio',)),
    Modulo('admin-actualizacion-bibliografica', 'Actualización bibliográfica', 'libro',
           (ADMINISTRADOR,),
           alias=('admin-bibliografia-busquedas', 'admin-bibliografia-version',
                  'admin-indicadores-literatura')),
    Modulo('admin-bibliografia-busquedas', 'Búsquedas bibliográficas', 'libro',
           (ADMINISTRADOR,), en_menu=False),
    Modulo('admin-bibliografia-estado', 'Progreso de la búsqueda', 'libro',
           (ADMINISTRADOR,), en_menu=False),
    Modulo('admin-bibliografia-version', 'Versión del catálogo', 'catalogo',
           (ADMINISTRADOR,), en_menu=False),
    Modulo('admin-indicadores-literatura', 'Indicadores de literatura', 'grafica',
           (ADMINISTRADOR,), en_menu=False),
    Modulo('admin-catalogo-metodologico', 'Catálogo metodológico', 'catalogo',
           (ADMINISTRADOR,)),
    # Decisor
    Modulo('decisor-inicio', 'Inicio', 'inicio', (DECISOR,)),
    Modulo('decisor-ficha-inicial', 'Nueva evaluación', 'mas', (DECISOR,)),
    Modulo('decisor-importancia-factores', 'Importancia de factores', 'mas', (DECISOR,),
           en_menu=False),
    Modulo('decisor-carga-documental', 'Carga documental', 'mas', (DECISOR,), en_menu=False),
    Modulo('decisor-revision-valoraciones', 'Revisión de valoraciones', 'mas', (DECISOR,),
           en_menu=False),
    Modulo('decisor-resultados', 'Resultados', 'mas', (DECISOR,), en_menu=False),
    Modulo('decisor-informe', 'Informe', 'mas', (DECISOR,), en_menu=False),
    Modulo('decisor-historial-evaluaciones', 'Historial de evaluaciones', 'reloj', (DECISOR,)),
)

_POR_RUTA = {m.ruta: m for m in CATALOGO}


def menu_para(rol):
    """Módulos que se dibujan en el menú lateral para ese rol."""
    return tuple(m for m in CATALOGO if m.en_menu and rol in m.roles)


def inicio_de(rol):
    """Ruta de la pantalla de inicio del rol (None si el rol no existe)."""
    return INICIO_POR_ROL.get(rol)


def seccion_de(rol):
    return SECCION_POR_ROL.get(rol, '')


def roles_permitidos(ruta):
    """Roles que pueden abrir esa ruta; vacío si la ruta no está en el catálogo."""
    modulo = _POR_RUTA.get(ruta)
    return modulo.roles if modulo else ()


def puede_acceder(rol, ruta):
    """Una ruta fuera del catálogo se niega: lo no declarado no se abre."""
    return rol in roles_permitidos(ruta)


def decidir_acceso(rol, ruta):
    """
    Decide qué hacer con una petición a `ruta`.

    `rol` es None cuando no hay sesión. Devuelve PERMITIR, PEDIR_LOGIN o DENEGAR.
    """
    if ruta in RUTAS_PUBLICAS:
        return PERMITIR
    if rol is None:
        return PEDIR_LOGIN
    return PERMITIR if puede_acceder(rol, ruta) else DENEGAR
