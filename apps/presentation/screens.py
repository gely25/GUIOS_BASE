"""
Servicios de presentación y preparación de datos para pantallas de GUIOS PRO.

Encapsula los metadatos de interfaz, textos, estado visual y configuración inicial
de las pantallas del Decisor y de Administración.
"""


def get_access_screen_data():
    """
    Proporciona la configuración y metadatos iniciales para la pantalla «Acceso · Decisor».
    """
    return {
        'default_role': 'decisor',
        'roles': [
            {'value': 'decisor', 'label': 'Decisor', 'selected': True},
            {'value': 'administrador', 'label': 'Administrador', 'selected': False},
        ],
        'email_placeholder': 'decisor@organizacion.com',
        'auth_pending_note': 'La autenticación y validación de credenciales se implementarán en la HU01.',
    }


def get_decisor_dashboard_data():
    """
    Obtiene los datos para la pantalla «Decisor · Inicio» (nodo 7:2970).
    Provee el listado de módulos de evaluación, estado de la evaluación activa
    y el estado vacío si no existen evaluaciones.
    """
    return {
        'area': 'decisor',
        'area_title': 'Espacio del Decisor',
        'user_name': 'Decisor Institucional',
        'user_email': 'decisor@organizacion.com',
        'user_role': 'Decisor',
        'evaluations': [],  # Lista vacía simulando el estado inicial
        'empty_state_title': 'Aún no hay evaluaciones registradas',
        'empty_state_description': (
            'Para iniciar el proceso de adopción tecnológica guiado por evidencia, '
            'registre una nueva evaluación completando la ficha inicial.'
        ),
        'modules': [
            {
                'name': 'Ficha inicial de evaluación',
                'url_name': 'presentation:decisor-ficha-inicial',
                'figma_ref': 'nodo 7:3102',
                'description': 'Registro de datos del proyecto, entidad y tecnología de software libre evaluada.',
                'badge': 'Paso 1',
            },
            {
                'name': 'Importancia de factores',
                'url_name': 'presentation:decisor-importancia-factores',
                'figma_ref': 'nodo 7:3241',
                'description': 'Ponderación de factores en dimensiones tecnológica, organizacional y económica.',
                'badge': 'Paso 2',
            },
            {
                'name': 'Carga documental',
                'url_name': 'presentation:decisor-carga-documental',
                'figma_ref': 'nodo 7:3507',
                'description': 'Carga de evidencias documentales, normativas, técnicas y económicas.',
                'badge': 'Paso 3',
            },
            {
                'name': 'Revisión de valoraciones',
                'url_name': 'presentation:decisor-revision-valoraciones',
                'figma_ref': 'nodo 7:3631',
                'description': 'Validación de criterios y evidencia asistida antes de los cálculos.',
                'badge': 'Paso 4',
            },
            {
                'name': 'Resultados',
                'url_name': 'presentation:decisor-resultados',
                'figma_ref': 'nodo 7:4266',
                'description': 'Consulta de índices IL, IS, IR, PM y matriz de clasificación FODA.',
                'badge': 'Paso 5',
            },
            {
                'name': 'Informe',
                'url_name': 'presentation:decisor-informe',
                'figma_ref': 'nodo 7:4464',
                'description': 'Generación, revisión y exportación de informe consolidado y recomendación final.',
                'badge': 'Paso 6',
            },
            {
                'name': 'Historial de evaluaciones',
                'url_name': 'presentation:decisor-historial-evaluaciones',
                'figma_ref': 'nodo 7:4609',
                'description': 'Historial trazable, estado de avances y comparativa de evaluaciones previas.',
                'badge': 'Histórico',
            },
        ],
    }


def get_admin_dashboard_data():
    """
    Obtiene los datos para la pantalla «Administración · Usuarios y roles».
    Provee el listado de módulos del área administrativa.
    """
    return {
        'area': 'administracion',
        'area_title': 'Área de Administración',
        'user_name': 'Administrador del Sistema',
        'user_email': 'admin@guios.pro',
        'user_role': 'Administrador',
        'modules': [
            {
                'name': 'Usuarios y roles',
                'url_name': 'presentation:admin-usuarios-roles',
                'figma_ref': 'nodo 7:4928',
                'description': 'Gestión de cuentas institucionales, asignación de perfiles y permisos de acceso.',
                'badge': 'Seguridad',
            },
            {
                'name': 'Actualización bibliográfica',
                'url_name': 'presentation:admin-actualizacion-bibliografica',
                'figma_ref': 'nodo 7:5175',
                'description': 'Gestión de fuentes científicas y sincronización con literatura 2020–2025.',
                'badge': 'Bibliografía',
            },
            {
                'name': 'Catálogo metodológico',
                'url_name': 'presentation:admin-catalogo-metodologico',
                'figma_ref': 'nodo 7:5516',
                'description': 'Configuración de factores, subfactores, cuartiles y umbrales de decisión.',
                'badge': 'Metodología',
            },
        ],
    }


def get_pending_module_data(nombre_modulo, area, referencia_figma=None, descripcion_extra=None):
    """
    Obtiene los datos para presentar la pantalla de módulo pendiente.
    Garantiza que el enlace de retorno regrese al área desde la que se accedió.
    """
    if area == 'administracion':
        url_retorno = 'presentation:admin-inicio'
        area_display = 'Área de Administración'
        step_number = None
    else:
        url_retorno = 'presentation:decisor-inicio'
        area_display = 'Área del Decisor'
        step_mapping = {
            'Ficha inicial de evaluación': 1,
            'Importancia de factores': 2,
            'Carga documental': 3,
            'Revisión de valoraciones': 4,
            'Resultados': 5,
            'Informe': 6,
        }
        step_number = step_mapping.get(nombre_modulo)

    return {
        'nombre_modulo': nombre_modulo,
        'mensaje': 'Módulo no disponible',
        'texto_retorno': 'Volver al inicio',
        'url_retorno': url_retorno,
        'area': area,
        'area_display': area_display,
        'referencia_figma': referencia_figma or 'Figma GUIOS PRO',
        'descripcion_extra': descripcion_extra,
        'step_number': step_number,
    }
