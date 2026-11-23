"""Vista del paso 2 de la evaluación: importancia de los factores - HU06."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.application.services.importancia import (
    ImportanciaFactoresService,
    ImportanciaInvalidaError,
)


def _entero(valor):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return numero if 0 < numero <= 9223372036854775807 else None


@require_http_methods(['GET', 'POST'])
def importancia_factores_view(request):
    """
    Pantalla «Valoración de factores» (Figma nodo 7:3241).

    El decisor ajusta la ID de cada factor (parte de la IS sugerida); la IR se calcula
    en el servicio y los factores con IR = 1 quedan fuera de la evaluación.
    """
    if not request.user.is_authenticated or not request.user.activo or request.user.rol != 'DECISOR':
        raise PermissionDenied

    datos = request.POST if request.method == 'POST' else request.GET
    crudo = datos.get('evaluacion_id')
    servicio = ImportanciaFactoresService()
    evaluacion = None
    if not crudo:
        evaluacion = servicio.evaluacion_del_decisor(request.user)
    elif _entero(crudo) is not None:
        evaluacion = servicio.evaluacion_del_decisor(request.user, _entero(crudo))
    if evaluacion is None:
        # Sin evaluación propia en curso (o identificador ajeno o inválido): no se guarda nada
        # y se invita a registrar la ficha inicial, sin revelar si la evaluación existe.
        return render(request, 'presentation/decisor/importancia_factores.html', {
            'evaluacion': None,
            'active_tab': 'nueva-evaluacion',
            'current_step': 2,
        })

    error = None
    ids = {}
    if request.method == 'POST':
        for fila in servicio.filas(evaluacion):
            valor = _entero(request.POST.get(f'id_{fila.factor_id}'))
            if valor is not None:
                ids[fila.factor_id] = valor
        try:
            servicio.guardar(evaluacion, ids)
        except ImportanciaInvalidaError as exc:
            error = str(exc)
        else:
            messages.success(request, 'Importancia de los factores registrada.')
            siguiente = reverse('presentation:decisor-carga-documental')
            return redirect(f'{siguiente}?evaluacion_id={evaluacion.pk}')

    grupos = servicio.agrupadas(evaluacion, ids)
    filas = [fila for grupo in grupos for fila in grupo['filas']]
    return render(request, 'presentation/decisor/importancia_factores.html', {
        'evaluacion': evaluacion,
        'grupos': grupos,
        'niveles': servicio.NIVELES.items(),
        'total': len(filas),
        'relevantes': sum(1 for fila in filas if fila.relevante),
        'excluidos': [fila for fila in filas if not fila.relevante],
        'suma_ir': sum(fila.ir for fila in filas if fila.relevante),
        'filas': filas,
        'matriz': servicio.matriz_ir(),
        'resumen_niveles': [
            {'ir': nivel, 'etiqueta': etiqueta, 'filas': [f for f in filas if f.ir == nivel]}
            for nivel, etiqueta in sorted(servicio.NIVELES.items(), reverse=True)
        ],
        'error': error,
        'active_tab': 'nueva-evaluacion',
        'current_step': 2,
    })
