"""
Formulario de acceso (capa de presentación).

El usuario entra con correo y contraseña. El rol no se elige: sale de usuario.rol.
"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm


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
