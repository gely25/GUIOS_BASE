"""
Revisión del administrador: aprobar o rechazar sugerencias y vincular a mano (RF02).
Solo los vínculos APROBADOS cuentan para el TC.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.data.models import PublicacionFactor
from apps.data.repositorios import bibliografia as repo
from apps.data.repositorios import catalogo as repo_catalogo

from .autorizacion import autorizar_administrador


@transaction.atomic
def revisar(actor_id, busqueda_id, vinculo_id, aprobar):
    actor = autorizar_administrador(actor_id)
    vinculo = repo.obtener_vinculo(vinculo_id, bloquear=True)
    if not repo.busqueda_contiene(busqueda_id, vinculo.publicacion_id):
        raise ValidationError('La publicación no pertenece a esta búsqueda.')
    estado = PublicacionFactor.APROBADA if aprobar else PublicacionFactor.RECHAZADA
    repo.revisar_vinculo(vinculo, estado, actor)
    if aprobar:
        repo.marcar_seleccionada(busqueda_id, vinculo.publicacion_id)
    return vinculo


@transaction.atomic
def vincular_manual(actor_id, busqueda_id, publicacion_id, factor_id, justificacion=''):
    actor = autorizar_administrador(actor_id)
    if not repo.busqueda_contiene(busqueda_id, publicacion_id):
        raise ValidationError('La publicación no pertenece a esta búsqueda.')
    factores = {f.pk for f in repo_catalogo.factores_de(repo_catalogo.version_activa())}
    if factor_id not in factores:
        raise ValidationError('El factor no está activo en el catálogo vigente.')
    vinculo = repo.vincular_manual(publicacion_id, factor_id, (justificacion or '').strip()[:2000], actor)
    repo.marcar_seleccionada(busqueda_id, publicacion_id)
    return vinculo
