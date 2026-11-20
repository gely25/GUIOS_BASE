"""Solo un administrador activo puede actualizar la bibliografía o publicar versiones (RNF05)."""

from django.core.exceptions import PermissionDenied

from apps.data.models import Usuario


def autorizar_administrador(actor_id):
    """Vuelve a leer el usuario (el rol pudo cambiar después de iniciar sesión)."""
    actor = Usuario.objects.filter(pk=actor_id).first()
    if actor is None or not actor.is_staff:
        raise PermissionDenied('Solo un administrador activo puede hacer esta acción.')
    return actor
