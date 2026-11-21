from django.test import TestCase
from django.urls import reverse

from apps.business_rules import menu
from apps.data.models import Usuario

PENDIENTES = [
    'admin-actualizacion-bibliografica',
    'admin-catalogo-metodologico',
    'decisor-ficha-inicial',
    'decisor-importancia-factores',
    'decisor-resultados',
    'decisor-informe',
    'decisor-historial-evaluaciones',
]


class RutasPorAreaTests(TestCase):
    """Cada ruta responde con la sesión del rol que corresponde."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(
            correo='admin@guios.test', password='Clave-Segura-123',
            nombre='Ana Admin', rol=Usuario.ADMINISTRADOR)
        cls.decisor = Usuario.objects.create_user(
            correo='decisor@guios.test', password='Clave-Segura-123',
            nombre='Dario Decisor', rol=Usuario.DECISOR)

    def abrir(self, ruta):
        modulo = next(m for m in menu.CATALOGO if m.ruta == ruta)
        usuario = self.admin if menu.ADMINISTRADOR in modulo.roles else self.decisor
        self.client.force_login(usuario)
        return self.client.get(reverse('presentation:' + ruta))

    def test_todas_las_rutas_responden_200_con_su_rol(self):
        for modulo in menu.CATALOGO:
            with self.subTest(ruta=modulo.ruta):
                self.assertEqual(self.abrir(modulo.ruta).status_code, 200)

    def test_los_modulos_pendientes_muestran_modulo_no_disponible(self):
        for ruta in PENDIENTES:
            with self.subTest(ruta=ruta):
                self.assertContains(self.abrir(ruta), 'Módulo no disponible')

    def test_la_vista_de_indicadores_no_es_un_modulo_pendiente(self):
        self.assertNotContains(self.abrir('admin-indicadores-literatura'), 'Módulo no disponible')

    def test_las_rutas_ya_no_llevan_el_prefijo_vista_previa(self):
        for modulo in menu.CATALOGO:
            self.assertNotIn('vista-previa', reverse('presentation:' + modulo.ruta))
