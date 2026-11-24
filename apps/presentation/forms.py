"""
Formulario de acceso (capa de presentación).

El usuario entra con correo y contraseña. El rol no se elige: sale de usuario.rol.
"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from apps.data.models import Usuario


SIN_ELEGIR = ('', 'Seleccione una opción')

SECTORES = [SIN_ELEGIR] + [(v, v) for v in (
    'Educación', 'Tecnología', 'Salud', 'Gobierno', 'Finanzas', 'Industria',
    'Comercio', 'Investigación', 'Otro',
)]

# El valor que se guarda es el nombre; la lista muestra el rango de personal de cada tamaño.
TAMANOS = [SIN_ELEGIR,
           ('Microempresa', 'Microempresa · de 1 a 9 personas'),
           ('Pequeña', 'Pequeña · de 10 a 49 personas'),
           ('Mediana', 'Mediana · de 50 a 199 personas'),
           ('Grande', 'Grande · 200 personas o más')]


class EvaluacionInicialForm(forms.Form):
    nombre_organizacion = forms.CharField(
        label='Nombre de la organización', max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'evaluacion-input',
            'placeholder': 'Ej. Universidad Nacional',
        }))
    sector = forms.ChoiceField(
        label='Sector', required=False, choices=SECTORES,
        widget=forms.Select(attrs={'class': 'evaluacion-input'}))
    sector_otro = forms.CharField(
        label='Otro sector', required=False, max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'evaluacion-input',
            'placeholder': 'Escriba el sector',
        }))
    tamano = forms.ChoiceField(
        label='Tamaño', required=False, choices=TAMANOS,
        widget=forms.Select(attrs={'class': 'evaluacion-input'}))
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

    def clean(self):
        datos = super().clean()
        if datos.get('sector') == 'Otro':
            propio = ' '.join((datos.get('sector_otro') or '').split())
            if not propio:
                self.add_error('sector_otro', 'Escriba el sector de la organización.')
            else:
                datos['sector'] = propio
        return datos

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in ('sector', 'tamano'):
            actual = (self.initial.get(campo) or '').strip()
            opciones = self.fields[campo].choices
            if actual and actual not in [valor for valor, _ in opciones]:
                self.fields[campo].choices = list(opciones) + [(actual, actual)]


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


class RegistroForm(forms.Form):
    """Alta de una persona decisora. La organización se registra luego, en su primera evaluación."""

    nombre = forms.CharField(
        label='Nombre completo', max_length=150,
        widget=forms.TextInput(attrs={'autocomplete': 'name', 'autofocus': True,
                                      'placeholder': 'Nombre y apellido'}))
    correo = forms.EmailField(
        label='Correo electrónico', max_length=150,
        widget=forms.EmailInput(attrs={'autocomplete': 'username',
                                       'placeholder': 'usuario@organizacion.com'}))
    rol = forms.ChoiceField(
        label='Tipo de cuenta', choices=[(Usuario.DECISOR, 'Decisor'), (Usuario.ADMINISTRADOR, 'Administrador')], initial=Usuario.DECISOR,
        widget=forms.RadioSelect)
    password1 = forms.CharField(
        label='Contraseña', strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': 'Mínimo 8 caracteres'}))
    password2 = forms.CharField(
        label='Confirmar contraseña', strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': 'Repita la contraseña'}))

    def clean_nombre(self):
        nombre = ' '.join(self.cleaned_data['nombre'].split())
        if not nombre:
            raise forms.ValidationError('Escriba su nombre.')
        return nombre

    def clean_correo(self):
        correo = self.cleaned_data['correo'].strip().lower()
        if Usuario.objects.filter(correo__iexact=correo).exists():
            raise forms.ValidationError('Ya existe una cuenta con este correo. Inicie sesión.')
        return correo

    def clean(self):
        datos = super().clean()
        clave, repetida = datos.get('password1'), datos.get('password2')
        if clave and repetida and clave != repetida:
            self.add_error('password2', 'Las contraseñas no coinciden.')
        elif clave:
            candidato = Usuario(nombre=datos.get('nombre', ''), correo=datos.get('correo', ''))
            try:
                validate_password(clave, candidato)
            except forms.ValidationError as error:
                self.add_error('password1', error)
        return datos


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
