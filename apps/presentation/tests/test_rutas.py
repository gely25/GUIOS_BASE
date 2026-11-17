from django.test import SimpleTestCase, override_settings
from django.urls import reverse

RUTAS = [
    'presentation:admin-inicio',
    'presentation:admin-usuarios-roles',
    'presentation:admin-actualizacion-bibliografica',
    'presentation:admin-indicadores-literatura',
    'presentation:admin-catalogo-metodologico',
    'presentation:decisor-inicio',
    'presentation:decisor-ficha-inicial',
    'presentation:decisor-importancia-factores',
    'presentation:decisor-carga-documental',
    'presentation:decisor-revision-valoraciones',
    'presentation:decisor-resultados',
    'presentation:decisor-informe',
    'presentation:decisor-historial-evaluaciones',
]

PENDIENTES = [
    'presentation:admin-actualizacion-bibliografica',
    'presentation:admin-catalogo-metodologico',
    'presentation:decisor-ficha-inicial',
    'presentation:decisor-importancia-factores',
    'presentation:decisor-carga-documental',
    'presentation:decisor-revision-valoraciones',
    'presentation:decisor-resultados',
    'presentation:decisor-informe',
    'presentation:decisor-historial-evaluaciones',
]


class RutasVistaPreviaTests(SimpleTestCase):

    @override_settings(DEBUG=True)
    def test_todas_las_rutas_responden_en_desarrollo(self):
        for nombre in RUTAS:
            with self.subTest(ruta=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)

    @override_settings(DEBUG=False)
    def test_en_produccion_ninguna_ruta_de_vista_previa_existe(self):
        for nombre in RUTAS:
            with self.subTest(ruta=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 404)

    @override_settings(DEBUG=True)
    def test_los_modulos_pendientes_muestran_modulo_no_disponible(self):
        for nombre in PENDIENTES:
            with self.subTest(ruta=nombre):
                self.assertContains(self.client.get(reverse(nombre)), 'Módulo no disponible')

    @override_settings(DEBUG=True)
    def test_la_vista_de_indicadores_no_es_un_modulo_pendiente(self):
        respuesta = self.client.get(reverse('presentation:admin-indicadores-literatura'))
        self.assertNotContains(respuesta, 'Módulo no disponible')
