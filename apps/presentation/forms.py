"""
Formulario de acceso (capa de presentación).

El usuario entra con correo y contraseña. El rol no se elige: sale de usuario.rol.
"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from apps.data.models import Usuario


class EvaluacionInicialForm(forms.Form):
    nombre_organizacion = forms.CharField(
        label='Nombre de la organización', max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'evaluacion-input',
            'placeholder': 'Ej. Universidad Nacional',
        }))
    sector = forms.CharField(
        label='Sector', max_length=100, required=False,
        widget=forms.TextInput(attrs={
            'class': 'evaluacion-input',
            'placeholder': 'Ej. Educación',
        }))
    tamano = forms.CharField(
        label='Tamaño', max_length=50, required=False,
        widget=forms.TextInput(attrs={
            'class': 'evaluacion-input',
            'placeholder': 'Ej. Mediana',
        }))
    objetivo_adopcion = forms.CharField(
        label='Objetivo de adopción', required=False,
        widget=forms.Textarea(attrs={
            'class': 'evaluacion-input evaluacion-textarea',
            'rows': 3,
            'placeholder': 'Describa brevemente el propósito de la adopción',
        }))
    nombre_software = forms.CharField(
        label='Nombre del software', max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'evaluacion-input',
            'placeholder': 'Ej. LibreOffice',
        }))
    version_software = forms.CharField(
        label='Versión del software', max_length=50, required=False,
        widget=forms.TextInput(attrs={
            'class': 'evaluacion-input',
            'placeholder': 'Ej. 24.2',
        }))
    proveedor = forms.CharField(
        label='Proveedor', max_length=150, required=False,
        widget=forms.TextInput(attrs={
            'class': 'evaluacion-input',
            'placeholder': 'Ej. The Document Foundation',
        }))
    descripcion_software = forms.CharField(
        label='Descripción del software', required=False,
        widget=forms.Textarea(attrs={
            'class': 'evaluacion-input evaluacion-textarea',
            'rows': 3,
            'placeholder': 'Indique su propósito o principales características',
        }))


class AccesoForm(AuthenticationForm):
    username = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={
            'autocomplete': 'username',
            'autofocus': True,
            'placeholder': 'usuario@organizacion.com',
        }),
    )
    password = forms.CharField(
        label='Contraseña',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'current-password',
            'placeholder': '••••••••',
        }),
    )

    # Mensaje único: no revela si el correo existe o si la cuenta está inactiva.
    error_messages = {
        'invalid_login': 'Correo o contraseña incorrectos.',
        'inactive': 'Correo o contraseña incorrectos.',
    }


class UsuarioEditarForm(forms.Form):
    nombre = forms.CharField(label='Nombre completo', max_length=150,
                             widget=forms.TextInput(attrs={'class': 'filter-input'}))
    correo = forms.EmailField(label='Correo electrónico', max_length=150,
                              widget=forms.EmailInput(attrs={'class': 'filter-input'}))
    rol = forms.ChoiceField(label='Rol', choices=Usuario.ROLES,
                            widget=forms.Select(attrs={'class': 'filter-select'}))


class UsuarioNuevoForm(UsuarioEditarForm):
    rol = forms.ChoiceField(label='Rol', choices=Usuario.ROLES, initial=Usuario.DECISOR,
                            widget=forms.Select(attrs={'class': 'filter-select'}))
    password = forms.CharField(label='Contraseña inicial', strip=False, max_length=128,
                               widget=forms.PasswordInput(attrs={'class': 'filter-input', 'autocomplete': 'new-password'}))
    confirmacion = forms.CharField(label='Confirmar contraseña', strip=False, max_length=128,
                                   widget=forms.PasswordInput(attrs={'class': 'filter-input', 'autocomplete': 'new-password'}))

    def clean(self):
        datos = super().clean()
        if datos.get('password') and datos.get('confirmacion') and datos['password'] != datos['confirmacion']:
            self.add_error('confirmacion', 'Las contraseñas no coinciden.')
        return datos


class UsuarioEstadoForm(forms.Form):
    activo = forms.TypedChoiceField(choices=(('1', 'Activar'), ('0', 'Desactivar')),
                                    coerce=lambda valor: valor == '1', widget=forms.HiddenInput)
    motivo = forms.CharField(label='Motivo del cambio', max_length=500,
                             widget=forms.Textarea(attrs={'class': 'usuarios-motivo', 'rows': 3}))


# --- Actualización bibliográfica (HU02) ---------------------------------------

class RevisionVinculoForm(forms.Form):
    """Aprobar o rechazar un vínculo publicación-factor sugerido."""

    vinculo = forms.IntegerField(min_value=1, max_value=9223372036854775807, widget=forms.HiddenInput)
    decision = forms.ChoiceField(choices=(('aprobar', 'Aprobar'), ('rechazar', 'Rechazar')))


class VinculoManualForm(forms.Form):
    """Vincular a mano una publicación con un factor (queda aprobado)."""

    publicacion = forms.IntegerField(min_value=1, max_value=9223372036854775807, widget=forms.HiddenInput)
    factor = forms.TypedChoiceField(label='Factor', coerce=int,
                                    widget=forms.Select(attrs={'class': 'filter-select'}))
    justificacion = forms.CharField(label='Justificación', max_length=2000, required=False,
                                    widget=forms.TextInput(attrs={'class': 'filter-input',
                                                                  'placeholder': 'Por qué es pertinente (opcional)'}))

    def __init__(self, *args, factores=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['factor'].choices = [(f.pk, f.nombre) for f in factores]
