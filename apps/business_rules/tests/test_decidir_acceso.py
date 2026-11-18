"""Pruebas de la decisión de acceso por rol (reglas puras)."""

import unittest

from apps.business_rules import menu


class DecidirAccesoTests(unittest.TestCase):

    def test_sin_sesion_se_pide_login_en_rutas_protegidas(self):
        for modulo in menu.CATALOGO:
            self.assertEqual(menu.decidir_acceso(None, modulo.ruta), menu.PEDIR_LOGIN, modulo.ruta)

    def test_rutas_publicas_se_permiten_con_y_sin_sesion(self):
        for ruta in menu.RUTAS_PUBLICAS:
            self.assertEqual(menu.decidir_acceso(None, ruta), menu.PERMITIR)
            self.assertEqual(menu.decidir_acceso(menu.DECISOR, ruta), menu.PERMITIR)

    def test_cada_rol_se_permite_en_lo_suyo(self):
        for modulo in menu.CATALOGO:
            for rol in modulo.roles:
                self.assertEqual(menu.decidir_acceso(rol, modulo.ruta), menu.PERMITIR)

    def test_el_rol_equivocado_se_deniega(self):
        self.assertEqual(menu.decidir_acceso(menu.DECISOR, 'admin-inicio'), menu.DENEGAR)
        self.assertEqual(menu.decidir_acceso(menu.ADMINISTRADOR, 'decisor-informe'), menu.DENEGAR)

    def test_ruta_fuera_del_catalogo_se_deniega_con_sesion(self):
        self.assertEqual(menu.decidir_acceso(menu.ADMINISTRADOR, 'ruta-inventada'), menu.DENEGAR)

    def test_ruta_fuera_del_catalogo_sin_sesion_pide_login(self):
        self.assertEqual(menu.decidir_acceso(None, 'ruta-inventada'), menu.PEDIR_LOGIN)

    def test_rol_desconocido_se_deniega(self):
        self.assertEqual(menu.decidir_acceso('INVITADO', 'decisor-inicio'), menu.DENEGAR)


if __name__ == '__main__':
    unittest.main()
