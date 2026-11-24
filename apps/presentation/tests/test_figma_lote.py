"""Regresión visual/funcional de administración y revisión bibliográfica por lotes."""

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.data.models import (
    BusquedaBibliografica, BusquedaPublicacion, Factor,
    Publicacion, PublicacionFactor, Usuario,
)


class AdministracionFigmaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(
            correo='figma-admin@guios.test', nombre='Admin Figma',
            password='Clave-Segura-123', rol=Usuario.ADMINISTRADOR,
        )
        Usuario.objects.create_user(
            correo='figma-decisor@guios.test', nombre='Decisor Figma',
            password='Clave-Segura-123', rol=Usuario.DECISOR,
        )
        Usuario.objects.create_user(
            correo='figma-inactivo@guios.test', nombre='Inactivo Figma',
            password='Clave-Segura-123', rol=Usuario.DECISOR, activo=False,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_usuarios_muestra_diseno_y_conteos_reales(self):
        res = self.client.get(reverse('presentation:admin-usuarios-roles'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['usuarios_activos'], 2)
        self.assertEqual(res.context['usuarios_inactivos'], 1)
        self.assertContains(res, '2 activos · 1 inactivo')
        self.assertContains(res, 'usuarios-switch')
        self.assertContains(res, 'Usuarios institucionales')

    def test_mantiene_confirmacion_para_desactivar(self):
        res = self.client.get(reverse('presentation:admin-usuarios-roles'))
        self.assertContains(res, 'accion=estado')
        res = self.client.get(reverse('presentation:admin-usuarios-roles'), {
            'accion': 'estado', 'usuario': Usuario.objects.get(correo='figma-decisor@guios.test').pk,
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Motivo del cambio')


class LoteBibliograficoFigmaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('cargar_catalogo_guios', verbosity=0)
        cls.admin = Usuario.objects.create_user(
            correo='figma-bib-admin@guios.test', nombre='Admin Bibliografía',
            password='Clave-Segura-123', rol=Usuario.ADMINISTRADOR,
        )
        cls.decisor = Usuario.objects.create_user(
            correo='figma-bib-decisor@guios.test', nombre='Decisor Bibliografía',
            password='Clave-Segura-123', rol=Usuario.DECISOR,
        )
        cls.factor = Factor.objects.first()
        cls.busqueda = BusquedaBibliografica.objects.create(
            consulta='prueba lote', fuente='Fuente de prueba', anio_inicio=2020,
            anio_fin=2025, factor=cls.factor, estado=BusquedaBibliografica.COMPLETADA,
        )
        cls.otra_busqueda = BusquedaBibliografica.objects.create(
            consulta='otra búsqueda', fuente='Fuente de prueba', anio_inicio=2020,
            anio_fin=2025, factor=cls.factor, estado=BusquedaBibliografica.COMPLETADA,
        )
        cls.vinculos = []
        for i in range(3):
            pub = Publicacion.objects.create(
                titulo=f'Publicación Figma {i}', anio=2023, doi=f'10.9999/guios-figma-{i}',
            )
            BusquedaPublicacion.objects.create(
                busqueda=cls.busqueda if i < 2 else cls.otra_busqueda,
                publicacion=pub, posicion=i + 1,
            )
            cls.vinculos.append(PublicacionFactor.objects.create(
                publicacion=pub, factor=cls.factor, origen=PublicacionFactor.PALABRAS_CLAVE,
                estado=PublicacionFactor.SUGERIDA,
            ))

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse('presentation:admin-bibliografia-busquedas') + f'?id={self.busqueda.pk}'

    def test_formulario_favorece_revision_multiple(self):
        res = self.client.get(self.url)
        self.assertContains(res, 'Seleccionar sugeridas')
        self.assertContains(res, 'Aprobar seleccionadas')
        self.assertContains(res, 'Rechazar seleccionadas')
        self.assertContains(res, 'Publicaciones recuperadas (2)')

    def test_lote_aprueba_solo_seleccionadas(self):
        res = self.client.post(self.url, {
            'accion': 'revisar_lote', 'decision': 'aprobar', 'confirmar': 'si',
            'vinculos': [str(self.vinculos[0].pk), str(self.vinculos[1].pk)],
        })
        self.assertEqual(res.status_code, 302)
        for v in self.vinculos[:2]:
            v.refresh_from_db()
            self.assertEqual(v.estado, PublicacionFactor.APROBADA)
        self.vinculos[2].refresh_from_db()
        self.assertEqual(self.vinculos[2].estado, PublicacionFactor.SUGERIDA)

    def test_lote_rechaza_vinculos_de_otra_busqueda_sin_cambios(self):
        res = self.client.post(self.url, {
            'accion': 'revisar_lote', 'decision': 'aprobar', 'confirmar': 'si',
            'vinculos': [str(self.vinculos[0].pk), str(self.vinculos[2].pk)],
        })
        self.assertEqual(res.status_code, 302)
        for v in self.vinculos:
            v.refresh_from_db()
            self.assertEqual(v.estado, PublicacionFactor.SUGERIDA)

    def test_lote_exige_confirmacion_explicita(self):
        res = self.client.post(self.url, {
            'accion': 'revisar_lote', 'decision': 'aprobar',
            'vinculos': [str(self.vinculos[0].pk)],
        })
        self.assertEqual(res.status_code, 400)
        self.vinculos[0].refresh_from_db()
        self.assertEqual(self.vinculos[0].estado, PublicacionFactor.SUGERIDA)

    def test_decisor_no_puede_aprobar_lote(self):
        self.client.force_login(self.decisor)
        res = self.client.post(self.url, {
            'accion': 'revisar_lote', 'decision': 'aprobar', 'confirmar': 'si',
            'vinculos': [str(self.vinculos[0].pk)],
        })
        self.assertEqual(res.status_code, 403)
        self.vinculos[0].refresh_from_db()
        self.assertEqual(self.vinculos[0].estado, PublicacionFactor.SUGERIDA)
