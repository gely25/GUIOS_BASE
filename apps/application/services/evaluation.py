"""
Servicio de Aplicación: EvaluationService.

Capa: application. Registro y seguimiento de evaluaciones, valoraciones confirmadas y resultados (HU05, HU11, HU13, HU15).
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.application.services.catalog import CatalogService
from apps.data.models import Evaluacion, Organizacion, Software


class EvaluationService:
    """Registro y seguimiento de evaluaciones, valoraciones confirmadas y resultados (HU05, HU11, HU13, HU15)."""

    @staticmethod
    def crear_evaluacion(usuario, datos):
        """Crea organización, software y evaluación de forma transaccional."""
        if not usuario or not usuario.is_authenticated or not usuario.activo:
            raise ValidationError('Debe iniciar sesión con una cuenta activa.')
        if usuario.rol != 'DECISOR':
            raise ValidationError('Solo un decisor puede registrar evaluaciones.')

        nombre_organizacion = (datos.get('nombre_organizacion') or '').strip()
        nombre_software = (datos.get('nombre_software') or '').strip()
        if not nombre_organizacion:
            raise ValidationError({'nombre_organizacion': 'Ingrese el nombre de la organización.'})
        if not nombre_software:
            raise ValidationError({'nombre_software': 'Ingrese el nombre del software.'})

        catalogo = CatalogService.obtener_version_vigente()
        with transaction.atomic():
            organizacion = usuario.organizacion
            if organizacion is None:
                organizacion = Organizacion(
                    nombre=nombre_organizacion,
                    sector=(datos.get('sector') or '').strip() or None,
                    tamano=(datos.get('tamano') or '').strip() or None,
                    objetivo_adopcion=(datos.get('objetivo_adopcion') or '').strip() or None,
                )
            else:
                organizacion.nombre = nombre_organizacion
                organizacion.sector = (datos.get('sector') or '').strip() or None
                organizacion.tamano = (datos.get('tamano') or '').strip() or None
                organizacion.objetivo_adopcion = (datos.get('objetivo_adopcion') or '').strip() or None
            organizacion.save()
            if usuario.organizacion_id != organizacion.pk:
                usuario.organizacion = organizacion
                usuario.save(update_fields=['organizacion'])

            software = Software.objects.create(
                nombre=nombre_software,
                version=(datos.get('version_software') or '').strip() or None,
                proveedor=(datos.get('proveedor') or '').strip() or None,
                descripcion=(datos.get('descripcion_software') or '').strip() or None,
            )
            return Evaluacion.objects.create(
                organizacion=organizacion,
                usuario=usuario,
                software=software,
                catalogo=catalogo,
                estado=Evaluacion.EN_PROCESO,
            )
