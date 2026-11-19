"""Regresión de los límites temporales del acceso (HU01)."""
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.application.services.login_throttle import LoginThrottle
from apps.data.models import Usuario


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                        'LOCATION': 'guios-pruebas-limite-acceso'}},
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class LimiteAccesoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = Usuario.objects.create_user(correo='decisor@guios.test',
            nombre='Decisor', password='Clave-Segura-123!')

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.url = reverse('presentation:home')

    def entrar(self, correo='decisor@guios.test', clave='incorrecta', ip='127.0.0.1', **extras):
        return self.client.post(self.url, {'username': correo, 'password': clave},
                                REMOTE_ADDR=ip, **extras)

    def test_bloquea_sexto_intento_incluso_con_clave_correcta(self):
        for _ in range(5):
            self.assertEqual(self.entrar().status_code, 200)
        r = self.entrar(clave='Clave-Segura-123!')
        self.assertContains(r, 'Demasiados intentos', status_code=429)
        self.assertEqual(r['Retry-After'], '900')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_normaliza_correo_y_no_confia_en_cabecera_enviada_por_cliente(self):
        for _ in range(5):
            self.entrar(correo='DECISOR@GUIOS.TEST')
        self.assertEqual(self.entrar(HTTP_X_FORWARDED_FOR='192.0.2.10').status_code, 429)

    def test_correo_inexistente_tiene_el_mismo_limite(self):
        for _ in range(5):
            self.assertContains(self.entrar(correo='nadie@guios.test'), 'Correo o contraseña incorrectos.')
        self.assertEqual(self.entrar(correo='nadie@guios.test').status_code, 429)

    def test_exito_reinicia_solo_contador_del_par(self):
        for _ in range(4):
            self.entrar()
        self.assertEqual(self.entrar(clave='Clave-Segura-123!').status_code, 302)
        ip, par = LoginThrottle.claves('127.0.0.1', self.usuario.correo)
        self.assertIsNone(cache.get(par))
        self.assertEqual(cache.get(ip), 4)

    def test_limite_global_ip_no_se_elude_cambiando_correo(self):
        for i in range(30):
            self.assertEqual(self.entrar(correo=f'otro{i}@guios.test').status_code, 200)
        self.assertEqual(self.entrar().status_code, 429)
        self.assertEqual(self.entrar(ip='192.0.2.10', clave='Clave-Segura-123!').status_code, 302)

    def test_al_expirar_ventana_se_permite_acceso(self):
        for _ in range(5):
            self.entrar()
        _, par = LoginThrottle.claves('127.0.0.1', self.usuario.correo)
        cache.set(par, 5, timeout=0)  # Simula vencimiento del TTL sin esperar 15 minutos.
        self.assertEqual(self.entrar(clave='Clave-Segura-123!').status_code, 302)
