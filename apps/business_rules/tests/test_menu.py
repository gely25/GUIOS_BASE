"""Pruebas del catálogo de módulos y el menú por rol."""

import unittest

from apps.business_rules import menu


class MenuPorRolTests(unittest.TestCase):

    def rutas(self, rol):
        return [m.ruta for m in menu.menu_para(rol)]

    def test_administrador_ve_solo_modulos_de_administracion(self):
        self.assertEqual(self.rutas(menu.ADMINISTRADOR), [
            'admin-usuarios-roles',
            'admin-actualizacion-bibliografica',
        ])

    def test_indicadores_de_literatura_no_aparece_en_el_menu_pero_el_admin_puede_abrirla(self):
        self.assertNotIn('admin-indicadores-literatura', self.rutas(menu.ADMINISTRADOR))
        self.assertTrue(menu.puede_acceder(menu.ADMINISTRADOR, 'admin-indicadores-literatura'))
        self.assertFalse(menu.puede_acceder(menu.DECISOR, 'admin-indicadores-literatura'))

    def test_decisor_ve_solo_modulos_del_decisor(self):
        self.assertEqual(self.rutas(menu.DECISOR), [
            'decisor-inicio',
            'decisor-ficha-inicial',
            'decisor-historial-evaluaciones',
        ])

    def test_ningun_rol_ve_modulos_del_otro(self):
        self.assertFalse(set(self.rutas(menu.ADMINISTRADOR)) & set(self.rutas(menu.DECISOR)))

    def test_rol_desconocido_no_ve_nada(self):
        self.assertEqual(menu.menu_para('INVITADO'), ())
        self.assertEqual(menu.menu_para(None), ())


class PermisosTests(unittest.TestCase):

    def test_cada_rol_accede_a_su_area(self):
        self.assertTrue(menu.puede_acceder(menu.ADMINISTRADOR, 'admin-inicio'))
        self.assertTrue(menu.puede_acceder(menu.DECISOR, 'decisor-resultados'))

    def test_un_rol_no_accede_al_area_del_otro(self):
        self.assertFalse(menu.puede_acceder(menu.DECISOR, 'admin-usuarios-roles'))
        self.assertFalse(menu.puede_acceder(menu.ADMINISTRADOR, 'decisor-informe'))

    def test_ruta_fuera_del_catalogo_se_niega(self):
        self.assertFalse(menu.puede_acceder(menu.ADMINISTRADOR, 'ruta-inventada'))

    def test_rol_desconocido_se_niega_en_todo(self):
        for modulo in menu.CATALOGO:
            self.assertFalse(menu.puede_acceder('INVITADO', modulo.ruta))


class CatalogoTests(unittest.TestCase):

    def test_las_15_rutas_de_presentacion_estan_en_el_catalogo(self):
        self.assertEqual(len(menu.CATALOGO), 15)
        self.assertEqual(len({m.ruta for m in menu.CATALOGO}), 15)

    def test_cada_ruta_tiene_exactamente_un_rol(self):
        for modulo in menu.CATALOGO:
            self.assertEqual(len(modulo.roles), 1, modulo.ruta)

    def test_inicio_y_seccion_por_rol(self):
        self.assertEqual(menu.inicio_de(menu.ADMINISTRADOR), 'admin-inicio')
        self.assertEqual(menu.inicio_de(menu.DECISOR), 'decisor-inicio')
        self.assertIsNone(menu.inicio_de('INVITADO'))
        self.assertEqual(menu.seccion_de(menu.DECISOR), 'ESPACIO DEL DECISOR')

    def test_la_ruta_de_inicio_de_cada_rol_es_accesible_para_ese_rol(self):
        for rol in (menu.ADMINISTRADOR, menu.DECISOR):
            self.assertTrue(menu.puede_acceder(rol, menu.inicio_de(rol)))


if __name__ == '__main__':
    unittest.main()
