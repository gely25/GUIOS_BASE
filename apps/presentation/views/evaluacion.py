"""Vistas de registro de evaluaciones - HU05."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.application.services.evaluation import EvaluationService
from apps.presentation.forms import EvaluacionInicialForm


def evaluacion_inicial_view(request):
    if not request.user.is_authenticated or not request.user.activo or request.user.rol != 'DECISOR':
        raise PermissionDenied

    organizacion = request.user.organizacion
    inicial = {
        'nombre_organizacion': organizacion.nombre if organizacion else '',
        'sector': organizacion.sector if organizacion else '',
        'tamano': organizacion.tamano if organizacion else '',
        'objetivo_adopcion': organizacion.objetivo_adopcion if organizacion else '',
    }
    form = EvaluacionInicialForm(request.POST or None, initial=inicial)

    if request.method == 'POST' and form.is_valid():
        try:
            evaluacion = EvaluationService.crear_evaluacion(request.user, form.cleaned_data)
        except ValidationError as exc:
            if hasattr(exc, 'message_dict'):
                for campo, errores in exc.message_dict.items():
                    if campo in form.fields:
                        form.add_error(campo, errores)
            else:
                form.add_error(None, exc.messages)
        else:
            messages.success(
                request,
                f'Evaluación #{evaluacion.pk} registrada en estado EN_PROCESO '
                f'con el catálogo {evaluacion.catalogo.version}.',
            )
            return redirect(reverse('presentation:decisor-ficha-inicial'))

    return render(
        request,
        'presentation/decisor/evaluacion_inicial.html',
        {'form': form, 'active_tab': 'nueva-evaluacion', 'current_step': 1},
    )
