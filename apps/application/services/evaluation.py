"""
Servicio de Aplicación: EvaluationService.

Capa: application. Registro y seguimiento de evaluaciones, valoraciones confirmadas y resultados (HU05, HU11, HU13, HU15).
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.application.services.catalog import CatalogService
from apps.data.models import Evaluacion, Organizacion, Software, Usuario


class EvaluationService:
    """Registro y seguimiento de evaluaciones, valoraciones confirmadas y resultados (HU05, HU11, HU13, HU15)."""

    @staticmethod
    def crear_evaluacion(usuario, datos):
        """Crea organización, software y evaluación sin alterar datos históricos."""
        if not usuario or not getattr(usuario, 'is_authenticated', False):
            raise ValidationError('Debe iniciar sesión con una cuenta activa.')
        if not getattr(usuario, 'activo', False):
            raise ValidationError('Debe iniciar sesión con una cuenta activa.')
        if usuario.rol != Usuario.DECISOR:
            raise ValidationError('Solo un decisor puede registrar evaluaciones.')

        datos_organizacion = {
            'nombre': (datos.get('nombre_organizacion') or '').strip(),
            'sector': (datos.get('sector') or '').strip() or None,
            'tamano': (datos.get('tamano') or '').strip() or None,
            'objetivo_adopcion': (datos.get('objetivo_adopcion') or '').strip() or None,
        }
        nombre_software = (datos.get('nombre_software') or '').strip()

        if not datos_organizacion['nombre']:
            raise ValidationError({
                'nombre_organizacion': 'Ingrese el nombre de la organización.'
            })
        if not nombre_software:
            raise ValidationError({
                'nombre_software': 'Ingrese el nombre del software.'
            })

        with transaction.atomic():
            # Releer y bloquear al decisor evita que dos registros simultáneos
            # trabajen con una relación usuario-organización desactualizada.
            try:
                decisor = Usuario.objects.select_for_update().get(pk=usuario.pk)
            except Usuario.DoesNotExist:
                raise ValidationError('La cuenta del decisor ya no está disponible.')

            if not decisor.activo:
                raise ValidationError('Debe iniciar sesión con una cuenta activa.')
            if decisor.rol != Usuario.DECISOR:
                raise ValidationError('Solo un decisor puede registrar evaluaciones.')

            # La versión se obtiene dentro de la misma transacción que crea
            # la evaluación y se bloquea para evitar cambios concurrentes.
            catalogo = CatalogService.obtener_version_vigente(bloquear=True)

            organizacion = None
            if decisor.organizacion_id:
                organizacion_actual = Organizacion.objects.select_for_update().get(
                    pk=decisor.organizacion_id
                )
                tiene_evaluaciones = Evaluacion.objects.filter(
                    organizacion_id=organizacion_actual.pk
                ).exists()
                compartida = organizacion_actual.usuarios.exclude(
                    pk=decisor.pk
                ).exists()

                if tiene_evaluaciones or compartida:
                    datos_sin_cambios = all(
                        getattr(organizacion_actual, campo) == valor
                        for campo, valor in datos_organizacion.items()
                    )
                    if datos_sin_cambios:
                        # Reutilizar la ficha no altera el historial si sus
                        # datos permanecen exactamente iguales.
                        organizacion = organizacion_actual
                    else:
                        # Si hay historial o usuarios asociados, los cambios
                        # se guardan en una ficha nueva para no alterar datos
                        # de evaluaciones anteriores ni de otros decisores.
                        organizacion = Organizacion.objects.create(
                            **datos_organizacion
                        )
                else:
                    # Si todavía no hay historial ni otros usuarios asociados,
                    # es seguro actualizar la ficha existente.
                    for campo, valor in datos_organizacion.items():
                        setattr(organizacion_actual, campo, valor)
                    organizacion_actual.save(
                        update_fields=list(datos_organizacion.keys())
                    )
                    organizacion = organizacion_actual
            else:
                organizacion = Organizacion.objects.create(
                    **datos_organizacion
                )

            if decisor.organizacion_id != organizacion.pk:
                decisor.organizacion = organizacion
                decisor.save(update_fields=['organizacion'])

            # Mantener sincronizada la instancia recibida por el llamador.
            usuario.organizacion = organizacion

            software = Software.objects.create(
                nombre=nombre_software,
                version=(datos.get('version_software') or '').strip() or None,
                proveedor=(datos.get('proveedor') or '').strip() or None,
                descripcion=(datos.get('descripcion_software') or '').strip() or None,
            )

            return Evaluacion.objects.create(
                organizacion=organizacion,
                usuario=decisor,
                software=software,
                catalogo=catalogo,
                estado=Evaluacion.EN_PROCESO,
            )
