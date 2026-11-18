"""
Organización y Usuario (tablas `organizacion` y `usuario`).

El usuario inicia sesión con su correo; su rol es una columna (ADMINISTRADOR o DECISOR).
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import Q


class Organizacion(models.Model):
    organizacion_id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=200)
    sector = models.CharField(max_length=100, blank=True, null=True)
    tamano = models.CharField(max_length=50, blank=True, null=True)
    objetivo_adopcion = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'organizacion'

    def __str__(self):
        return self.nombre


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, correo, password=None, **campos):
        if not correo:
            raise ValueError('El usuario debe tener un correo.')
        usuario = self.model(correo=correo, **campos)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def get_by_natural_key(self, correo):
        return self.get(correo__iexact=correo)

    def create_superuser(self, correo, password=None, **campos):
        campos['rol'] = Usuario.ADMINISTRADOR
        return self.create_user(correo, password, **campos)


class Usuario(AbstractBaseUser):
    ADMINISTRADOR = 'ADMINISTRADOR'
    DECISOR = 'DECISOR'
    ROLES = [(ADMINISTRADOR, 'Administrador'), (DECISOR, 'Decisor')]

    usuario_id = models.BigAutoField(primary_key=True)
    organizacion = models.ForeignKey(
        Organizacion, on_delete=models.PROTECT, null=True, blank=True,
        db_column='organizacion_id', related_name='usuarios',
    )
    nombre = models.CharField(max_length=150)
    correo = models.EmailField(max_length=150, unique=True)
    password = models.TextField(db_column='password_hash')
    rol = models.CharField(max_length=30, choices=ROLES, default=DECISOR)
    activo = models.BooleanField(default=True)

    objects = UsuarioManager()

    USERNAME_FIELD = 'correo'
    EMAIL_FIELD = 'correo'
    REQUIRED_FIELDS = ['nombre']

    class Meta:
        db_table = 'usuario'
        constraints = [
            models.CheckConstraint(
                condition=Q(rol__in=['ADMINISTRADOR', 'DECISOR']), name='usuario_rol_valido'),
        ]

    def __str__(self):
        return f'{self.nombre} <{self.correo}>'

    def get_full_name(self):
        return self.nombre

    def get_short_name(self):
        return self.nombre.split(' ')[0] if self.nombre else ''

    def save(self, *args, **kwargs):
        # El correo es el identificador de acceso: se guarda siempre en minúsculas.
        self.correo = (self.correo or '').strip().lower()
        super().save(*args, **kwargs)

    # Django usa estos nombres; se derivan de las columnas del esquema.
    @property
    def is_active(self):
        return self.activo

    @is_active.setter
    def is_active(self, valor):
        self.activo = valor

    @property
    def es_administrador(self):
        return self.rol == self.ADMINISTRADOR

    @property
    def is_staff(self):
        return self.activo and self.es_administrador

    @property
    def is_superuser(self):
        return self.activo and self.es_administrador

    def has_perm(self, perm, obj=None):
        return self.is_staff

    def has_module_perms(self, app_label):
        return self.is_staff
