"""Consultas del módulo de usuarios institucionales (HU01)."""

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth.password_validation import UserAttributeSimilarityValidator, validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q

from apps.data.models import Usuario


class UsuarioService:
    @staticmethod
    def consultar(buscar='', rol='', estado=''):
        """Lista filtrada y contadores globales de cuentas, incluidas las inactivas."""
        buscar = buscar.strip()[:150]
        rol = rol if rol in (Usuario.ADMINISTRADOR, Usuario.DECISOR) else ''
        estado = estado if estado in ('activo', 'inactivo') else ''

        cuentas = Usuario.objects.all()
        conteos = cuentas.aggregate(
            total=Count('pk'),
            decisores=Count('pk', filter=Q(rol=Usuario.DECISOR)),
            administradores=Count('pk', filter=Q(rol=Usuario.ADMINISTRADOR)),
        )
        if buscar:
            cuentas = cuentas.filter(Q(nombre__icontains=buscar) | Q(correo__icontains=buscar))
        if rol:
            cuentas = cuentas.filter(rol=rol)
        if estado:
            cuentas = cuentas.filter(activo=(estado == 'activo'))

        return {
            'usuarios': cuentas.only('nombre', 'correo', 'rol', 'activo', 'last_login').order_by('nombre', 'pk'),
            'conteos': conteos,
            'filtros': {'buscar': buscar, 'rol': rol, 'estado': estado},
            'roles': Usuario.ROLES,
        }

    @staticmethod
    def obtener(pk):
        return Usuario.objects.get(pk=pk)

    @staticmethod
    def _autorizar(actor_id):
        # Serializa cambios de administradores y vuelve a comprobar el rol.
        list(Usuario.objects.select_for_update().filter(
            rol=Usuario.ADMINISTRADOR, activo=True).order_by('pk').values_list('pk', flat=True))
        actor = Usuario.objects.get(pk=actor_id)
        if not actor.is_staff:
            raise PermissionDenied
        return actor

    @staticmethod
    def _registrar(actor, usuario, descripcion, accion):
        LogEntry.objects.create(
            user_id=actor.pk, content_type=ContentType.objects.get_for_model(Usuario),
            object_id=str(usuario.pk), object_repr=str(usuario)[:200],
            action_flag=accion, change_message=descripcion,
        )

    @classmethod
    @transaction.atomic
    def guardar(cls, actor_id, datos, pk=None):
        actor = cls._autorizar(actor_id)
        usuario = Usuario.objects.select_for_update().get(pk=pk) if pk else Usuario()
        if pk == actor.pk and datos['rol'] != actor.rol:
            raise ValidationError('No puedes cambiar tu propio rol.')
        correo = datos['correo'].strip().lower()
        if Usuario.objects.filter(correo__iexact=correo).exclude(pk=pk).exists():
            raise ValidationError('Este correo ya está registrado.')
        usuario.nombre = datos['nombre']
        usuario.correo = correo
        usuario.rol = datos['rol']
        if not pk:
            validate_password(datos['password'], user=usuario)
            UserAttributeSimilarityValidator(user_attributes=('nombre', 'correo')).validate(
                datos['password'], usuario)
            usuario.set_password(datos['password'])
        usuario.full_clean()
        try:
            with transaction.atomic():
                usuario.save()
        except IntegrityError as exc:
            raise ValidationError('No se pudo guardar la cuenta; verifica que el correo sea único.') from exc
        cls._registrar(actor, usuario, 'Cuenta editada.' if pk else 'Cuenta creada.', CHANGE if pk else ADDITION)
        return usuario

    @classmethod
    @transaction.atomic
    def cambiar_estado(cls, actor_id, pk, activo, motivo):
        actor = cls._autorizar(actor_id)
        usuario = Usuario.objects.select_for_update().get(pk=pk)
        if usuario.pk == actor.pk:
            raise ValidationError('No puedes cambiar el estado de tu propia cuenta.')
        if not motivo.strip():
            raise ValidationError('Indica el motivo del cambio de estado.')
        if usuario.activo != activo:
            usuario.activo = activo
            usuario.save(update_fields=['activo'])
            cls._registrar(actor, usuario, ('Activación' if activo else 'Desactivación') + ': ' + motivo, CHANGE)
        return usuario
