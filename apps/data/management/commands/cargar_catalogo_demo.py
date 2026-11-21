"""
Carga el catálogo GUIOS de referencia (tesis, Tablas 5.3 y 5.4) en una base de DESARROLLO.

Crea la dimensión, los 18 factores (con su alcance interno/externo), la versión
ACTIVA «2021» del catálogo y los indicadores base por factor: NS, TC e IE de la
tesis. No crea subfactores (el catálogo no trae sus descripciones aquí).
Es idempotente: se puede ejecutar varias veces.

Uso:  python manage.py cargar_catalogo_demo
Solo funciona en bases cuyo nombre termina en «_dev».
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.data.models.catalogo import CatalogoVersion, Dimension, Factor, IndicadorFactor

VERSION = "2021"
IE_BASE = 3

# (dimensión, factor, alcance, NS, TC)  -  tesis GUIOS, Tablas 5.3 y 5.4
CATALOGO_REFERENCIA = (
    ("Tecnológica", "Compatibilidad", "externo", 8, 33),
    ("Tecnológica", "Fiabilidad", "externo", 5, 19),
    ("Tecnológica", "Mantenibilidad", "externo", 1, 4),
    ("Tecnológica", "Personalización", "externo", 6, 30),
    ("Tecnológica", "Prueba", "externo", 1, 4),
    ("Tecnológica", "Documentación", "externo", 11, 20),
    ("Tecnológica", "Portabilidad", "externo", 2, 4),
    ("Tecnológica", "Reusabilidad", "externo", 2, 5),
    ("Tecnológica", "Usabilidad", "externo", 4, 14),
    ("Organizacional", "Apoyo de la alta dirección", "interno", 1, 5),
    ("Organizacional", "Formación", "interno", 4, 27),
    ("Organizacional", "Soporte", "ambos", 6, 43),
    ("Organizacional", "Actitud hacia el cambio", "interno", 2, 3),
    ("Organizacional", "Bloqueo de proveedores", "externo", 1, 3),
    ("Organizacional", "Casos de estudio de adopción FLOSS", "externo", 1, 1),
    ("Organizacional", "Centralidad de la tecnología de la información", "interno", 2, 2),
    ("Organizacional", "Tiempo de adopción", "interno", 2, 2),
    ("Económica", "Coste total de propiedad", "interno", 2, 24),
)


def es_base_de_desarrollo(nombre_base: str) -> bool:
    return str(nombre_base).endswith("_dev")


@transaction.atomic
def cargar_catalogo_referencia() -> int:
    """Crea o actualiza el catálogo de referencia. Devuelve cuántos factores quedaron."""
    version, _ = CatalogoVersion.objects.get_or_create(
        version=VERSION, defaults={"fecha_creacion": date(2021, 1, 1), "estado": "ACTIVO"})
    for nombre_dim, nombre, alcance, ns, tc in CATALOGO_REFERENCIA:
        dimension, _ = Dimension.objects.get_or_create(nombre=nombre_dim)
        factor, _ = Factor.objects.get_or_create(
            dimension=dimension, nombre=nombre, defaults={"alcance": alcance})
        IndicadorFactor.objects.update_or_create(
            catalogo=version, factor=factor,
            defaults={"numero_subfactores": ns, "total_citas": tc, "importancia_experto": IE_BASE})
    return len(CATALOGO_REFERENCIA)


class Command(BaseCommand):
    help = "Carga el catálogo GUIOS de referencia (18 factores) en una base de desarrollo (_dev)."

    def handle(self, *args, **options):
        nombre = connection.settings_dict["NAME"]
        if not es_base_de_desarrollo(nombre):
            raise CommandError(f"Solo se permite en bases terminadas en «_dev» (esta es «{nombre}»).")
        cantidad = cargar_catalogo_referencia()
        self.stdout.write(self.style.SUCCESS(
            f"Catálogo {VERSION} listo: {cantidad} factores con sus indicadores base."))
