"""Vistas del Área de Administración - GUIOS PRO."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.application.services.usuarios import UsuarioService
from apps.data.models import Usuario
from apps.presentation.forms import UsuarioEditarForm, UsuarioEstadoForm, UsuarioNuevoForm
from apps.presentation.screens import get_admin_dashboard_data


@require_http_methods(['GET', 'POST'])
def admin_home_view(request):
    """Gestiona usuarios en las dos rutas administrativas ya autorizadas."""
    entrada = request.POST if request.method == 'POST' else request.GET
    accion = entrada.get('accion', '')
    usuario = None
    formulario = None
    if accion in ('editar', 'estado'):
        try:
            pk = int(entrada.get('usuario', ''))
            if not 0 < pk <= 9223372036854775807:
                raise ValueError
            usuario = UsuarioService.obtener(pk)
        except (ValueError, Usuario.DoesNotExist):
            raise Http404('Usuario no encontrado.')
    datos = request.POST if request.method == 'POST' else None
    if accion == 'nuevo':
        formulario = UsuarioNuevoForm(datos)
    elif accion == 'editar':
        formulario = UsuarioEditarForm(datos, initial={
            'nombre': usuario.nombre, 'correo': usuario.correo, 'rol': usuario.rol})
    elif accion == 'estado':
        formulario = UsuarioEstadoForm(datos, initial={'activo': '0' if usuario.activo else '1'})
    elif accion or request.method == 'POST':
        return HttpResponseBadRequest('Acción no válida.')

    if request.method == 'POST' and formulario.is_valid():
        try:
            if accion == 'estado':
                UsuarioService.cambiar_estado(request.user.pk, usuario.pk, **formulario.cleaned_data)
            else:
                UsuarioService.guardar(request.user.pk, formulario.cleaned_data,
                                       pk=usuario.pk if usuario else None)
        except ValidationError as exc:
            formulario.add_error(None, exc)
        except Usuario.DoesNotExist:
            raise Http404('Usuario no encontrado.')
        else:
            mensaje = {'nuevo': 'Usuario creado correctamente.',
                       'editar': 'Usuario actualizado correctamente.'}.get(accion)
            if accion == 'estado':
                mensaje = ('Usuario activado correctamente.' if formulario.cleaned_data['activo']
                           else 'Usuario desactivado correctamente.')
            messages.success(request, mensaje)
            return redirect('presentation:admin-usuarios-roles')

    activos = Usuario.objects.filter(activo=True).count()
    context = {
        'usuarios_activos': activos,
        'usuarios_inactivos': Usuario.objects.count() - activos,
        'dashboard': get_admin_dashboard_data(),
        'active_tab': 'usuarios-roles',
        'accion_usuario': accion,
        'usuario_seleccionado': usuario,
        'formulario_usuario': formulario,
        **UsuarioService.consultar(
            buscar=request.GET.get('buscar', ''), rol=request.GET.get('rol', ''),
            estado=request.GET.get('estado', ''),
        ),
    }
    return render(request, 'presentation/administracion/admin_home.html', context)
