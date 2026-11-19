"""Límite temporal de intentos fallidos del formulario de acceso.

Usa el caché de Django. En producción debe ser compartido por todos los procesos
(p. ej., Redis) y admitir incremento atómico. No almacena correos ni claves.
"""
from django.core.cache import cache
from django.utils.crypto import salted_hmac


class LoginThrottle:
    VENTANA = 15 * 60
    LIMITE_PAR = 5
    LIMITE_IP = 30

    @classmethod
    def claves(cls, ip, correo):
        def clave(tipo, valor):
            return 'guios:acceso:' + tipo + ':' + salted_hmac(
                'guios.acceso.' + tipo, valor, algorithm='sha256').hexdigest()
        correo = correo.strip().lower()
        return clave('ip', ip), clave('par', ip + '\0' + correo)

    @classmethod
    def bloqueado(cls, ip, correo):
        por_ip, por_par = cls.claves(ip, correo)
        return (cache.get(por_ip, 0) >= cls.LIMITE_IP
                or cache.get(por_par, 0) >= cls.LIMITE_PAR)

    @classmethod
    def fallo(cls, ip, correo):
        for clave in cls.claves(ip, correo):
            if not cache.add(clave, 1, timeout=cls.VENTANA):
                try:
                    cache.incr(clave)
                except ValueError:
                    # La ventana pudo expirar entre add e incr.
                    cache.add(clave, 1, timeout=cls.VENTANA)

    @classmethod
    def exito(cls, ip, correo):
        # No reinicia el límite global de la IP.
        cache.delete(cls.claves(ip, correo)[1])
