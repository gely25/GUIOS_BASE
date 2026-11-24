"""
Vistas de la actualización bibliográfica (HU02) - área de Administración.

Solo piden datos y acciones a BibliographicService; no calculan ni consultan la base.
El acceso solo de administradores lo garantiza PermisosPorRolMiddleware (catálogo de menu.py).
"""

import uuid

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.db import transaction

from apps.data.models import BusquedaPublicacion, PublicacionFactor
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from apps.application.services.bibliographic import BibliographicService
from apps.presentation.forms import RevisionVinculoForm, VinculoManualForm

servicio = BibliographicService()


def _errores(error):
    return ' '.join(error.messages) if isinstance(error, ValidationError) else str(error)


def _entero_positivo(valor):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return numero if 0 < numero <= 9223372036854775807 else None


@require_http_methods(['GET', 'POST'])
def panel_view(request):
    """Panel: lanzar la búsqueda, ver su progreso y el historial reciente."""
    if request.method == 'POST':
        if request.POST.get('accion') != 'lanzar':
            return HttpResponseBadRequest('Acción no válida.')
        try:
            servicio.lanzar_actualizacion(request.user.pk)
        except ValidationError as error:
            messages.error(request, _errores(error))
        else:
            messages.success(request, 'Búsqueda bibliográfica en cola. El progreso se actualiza solo.')
        return redirect('presentation:admin-actualizacion-bibliografica')

    comparacion = servicio.comparacion_versiones()
    return render(request, 'presentation/administracion/bibliografia_panel.html', {
        'active_tab': 'actualizacion-bibliografica',
        'estado': servicio.estado_lote(),
        'busquedas': servicio.busquedas_recientes(20),
        'vinculos': servicio.resumen_vinculos(),
        'version_activa': comparacion.activa,
        'version_borrador': comparacion.borrador,
        'filas_indicadores': comparacion.filas[:8] if comparacion.filas else [],
    })


@require_http_methods(['GET', 'POST'])
def busquedas_view(request):
    """Sin ?id: historial de búsquedas. Con ?id: resultados y revisión de vínculos."""
    busqueda_id = _entero_positivo(request.GET.get('id'))
    if busqueda_id is None:
        if request.method == 'POST' or 'id' in request.GET:
            raise Http404('Búsqueda no encontrada.')
        return render(request, 'presentation/administracion/bibliografia_busquedas.html', {
            'active_tab': 'actualizacion-bibliografica',
            'busquedas': servicio.busquedas_recientes(200),
        })

    try:
        busqueda, resultados, factores = servicio.detalle_busqueda(busqueda_id)
    except ObjectDoesNotExist:
        raise Http404('Búsqueda no encontrada.')

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'revisar_lote':
            # Permite revisar varios vínculos explícitamente seleccionados sin
            # aprobar en silencio todas las sugerencias recuperadas.
            decision = request.POST.get('decision')
            valores = request.POST.getlist('vinculos')
            if decision not in ('aprobar', 'rechazar') or request.POST.get('confirmar') != 'si':
                return HttpResponseBadRequest('Confirme la acción y su decisión.')
            if not valores or len(valores) > 200:
                messages.error(request, 'Seleccione entre 1 y 200 vínculos para revisar.')
            else:
                ids = [_entero_positivo(valor) for valor in valores]
                if any(pk is None for pk in ids) or len(ids) != len(set(ids)):
                    messages.error(request, 'La selección contiene identificadores inválidos o duplicados.')
                else:
                    try:
                        with transaction.atomic():
                            # Todos deben pertenecer a ESTA búsqueda y estar sin revisar.
                            # Subconsulta de publicaciones de esta búsqueda: evita
                            # SELECT FOR UPDATE + DISTINCT, no permitido en PostgreSQL.
                            # El bloqueo afecta solo a filas de PublicacionFactor.
                            publicaciones = BusquedaPublicacion.objects.filter(
                                busqueda_id=busqueda.pk,
                            ).values_list('publicacion_id', flat=True)
                            elegidos = list(PublicacionFactor.objects.select_for_update().filter(
                                pk__in=ids,
                                publicacion_id__in=publicaciones,
                            ))
                            if len(elegidos) != len(ids) or any(
                                v.estado != PublicacionFactor.SUGERIDA for v in elegidos
                            ):
                                raise ValidationError(
                                    'Solo puede revisar sugerencias pendientes de esta búsqueda.')
                            for vinculo in elegidos:
                                servicio.revisar_vinculo(
                                    request.user.pk, busqueda.pk, vinculo.pk,
                                    aprobar=(decision == 'aprobar'))
                    except (ValidationError, ObjectDoesNotExist) as error:
                        messages.error(request, _errores(error))
                    else:
                        messages.success(request, f'{len(elegidos)} vínculos revisados correctamente.')
            return redirect(reverse('presentation:admin-bibliografia-busquedas') + f'?id={busqueda.pk}#bib-lote')
        if accion == 'revisar':
            formulario = RevisionVinculoForm(request.POST)
        elif accion == 'vincular':
            formulario = VinculoManualForm(request.POST, factores=factores)
        else:
            return HttpResponseBadRequest('Acción no válida.')
        if not formulario.is_valid():
            messages.error(request, 'Datos no válidos: revisa el formulario.')
        else:
            datos = formulario.cleaned_data
            try:
                if accion == 'revisar':
                    servicio.revisar_vinculo(request.user.pk, busqueda.pk, datos['vinculo'],
                                             aprobar=datos['decision'] == 'aprobar')
                    messages.success(request, 'Vínculo aprobado.' if datos['decision'] == 'aprobar'
                                     else 'Vínculo rechazado.')
                else:
                    servicio.vincular_manual(request.user.pk, busqueda.pk, datos['publicacion'],
                                             datos['factor'], datos['justificacion'])
                    messages.success(request, 'Publicación vinculada al factor.')
            except ObjectDoesNotExist:
                raise Http404('Vínculo no encontrado.')
            except ValidationError as error:
                messages.error(request, _errores(error))
        destino = reverse('presentation:admin-bibliografia-busquedas') + f'?id={busqueda.pk}'
        publicacion = _entero_positivo(request.POST.get('publicacion_ancla'))
        return redirect(destino + (f'#pub-{publicacion}' if publicacion else ''))

    return render(request, 'presentation/administracion/bibliografia_busqueda.html', {
        'active_tab': 'actualizacion-bibliografica',
        'busqueda': busqueda,
        'resultados': resultados,
        'factores': factores,
        'cantidad_sugeridas': sum(
            v.estado == PublicacionFactor.SUGERIDA
            for resultado in resultados for v in resultado.publicacion.factores.all()
        ),
    })


@require_GET
def estado_view(request):
    """Progreso del lote (por defecto el último) en JSON, para refrescar la interfaz sin recargar."""
    lote = request.GET.get('lote')
    estado = servicio.estado_lote(lote if _uuid_valido(lote) else None)
    return JsonResponse({
        'lote': estado['lote'],
        'total': estado['total'],
        'progreso': estado['progreso'],
        'terminado': estado['terminado'],
        'por_estado': estado['por_estado'],
    })


def _uuid_valido(valor):
    if not valor:
        return False
    try:
        uuid.UUID(valor)
    except ValueError:
        return False
    return True


@require_http_methods(['GET', 'POST'])
def version_view(request):
    """Recalcular TC/IL/IS en un borrador, compararlo con la versión activa y publicarlo."""
    if request.method == 'POST':
        acciones = {
            'recalcular': (servicio.crear_borrador, 'Borrador recalculado. Revisa los cambios antes de publicar.'),
            'publicar': (servicio.publicar_borrador, 'Nueva versión del catálogo publicada.'),
            'descartar': (servicio.descartar_borrador, 'Borrador descartado.'),
        }
        accion = acciones.get(request.POST.get('accion'))
        if accion is None:
            return HttpResponseBadRequest('Acción no válida.')
        funcion, mensaje = accion
        try:
            funcion(request.user.pk)
        except ValidationError as error:
            messages.error(request, _errores(error))
        else:
            messages.success(request, mensaje)
        return redirect('presentation:admin-bibliografia-version')

    return render(request, 'presentation/administracion/bibliografia_version.html', {
        'active_tab': 'actualizacion-bibliografica',
        'comparacion': servicio.comparacion_versiones(),
        'vinculos': servicio.resumen_vinculos(),
    })
