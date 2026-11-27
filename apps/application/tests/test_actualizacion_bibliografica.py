"""
Pruebas del flujo de actualización bibliográfica (HU02) con una fuente científica falsa:
búsqueda -> sugerencias -> revisión -> recálculo -> publicación de versión.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.application.services.bibliographic import BibliographicService
from apps.data.models import (
    BusquedaBibliografica,
    BusquedaPublicacion,
    CatalogoVersion,
    Evaluacion,
    Factor,
    IndicadorFactor,
    Organizacion,
    Publicacion,
    PublicacionFactor,
    Software,
    Usuario,
)
from apps.external_services.bibliografia import ErrorFuenteCientifica, ResultadoPublicacion
from apps.external_services.ai_errors import AnalisisNoDisponible

servicio = BibliographicService()


class FuenteFalsa:
    nombre = 'Fuente falsa'

    def __init__(self, resultados=(), fallar_en=()):
        self.resultados = list(resultados)
        self.fallar_en = set(fallar_en)
        self.consultas = []

    def buscar(self, consulta, anio_inicio, anio_fin, maximo):
        self.consultas.append(consulta)
        if any(t in consulta for t in self.fallar_en):
            raise ErrorFuenteCientifica('Servicio no disponible')
        return self.resultados[:maximo]


LOCK_IN = ResultadoPublicacion('Vendor lock-in in open source adoption', 2022, 'https://doi.org/10.1/LOCK',
                               'https://ejemplo.org/lock', 'We study vendor dependence.')
LOCK_IN_DUPLICADO = ResultadoPublicacion('Vendor lock-in (preprint)', 2022, '10.1/lock', None, None)
SIN_DOI = ResultadoPublicacion('Usability of FLOSS', 2021, None, None, 'ease of use')
ANTIGUA = ResultadoPublicacion('Usability study', 2018, '10.1/old', None, None)


class Base(TestCase):

    @classmethod
    def setUpTestData(cls):
        call_command('cargar_catalogo_guios', verbosity=0)
        cls.admin = Usuario.objects.create_user(
            correo='admin@guios.test', password='Clave-Segura-123', nombre='Ana Admin', rol=Usuario.ADMINISTRADOR)
        cls.decisor = Usuario.objects.create_user(
            correo='decisor@guios.test', password='Clave-Segura-123', nombre='Dario Decisor', rol=Usuario.DECISOR)
        cls.bloqueo = Factor.objects.get(nombre='Bloqueo de proveedores')
        cls.usabilidad = Factor.objects.get(nombre='Usabilidad')

    def lanzar_y_procesar(self, fuente, factor_ids=None):
        servicio.lanzar_actualizacion(self.admin.pk, factor_ids)
        return servicio.procesar_pendientes(fuente=fuente)

    def vinculo(self, publicacion, factor):
        return PublicacionFactor.objects.get(publicacion=publicacion, factor=factor)


class LanzarTests(Base):

    def test_deja_una_busqueda_pendiente_por_factor_con_periodo_2020_2025(self):
        lote = servicio.lanzar_actualizacion(self.admin.pk)
        busquedas = BusquedaBibliografica.objects.filter(lote=lote)
        self.assertEqual(busquedas.count(), 18)
        self.assertEqual(set(busquedas.values_list('estado', flat=True)), {BusquedaBibliografica.PENDIENTE})
        self.assertEqual(set(busquedas.values_list('anio_inicio', 'anio_fin')), {(2020, 2025)})
        consulta = busquedas.get(factor=self.bloqueo).consulta
        self.assertIn('"vendor lock-in"', consulta)

    def test_solo_un_administrador_puede_lanzarla(self):
        with self.assertRaises(PermissionDenied):
            servicio.lanzar_actualizacion(self.decisor.pk)

    def test_no_se_lanzan_dos_actualizaciones_a_la_vez(self):
        servicio.lanzar_actualizacion(self.admin.pk)
        with self.assertRaises(ValidationError):
            servicio.lanzar_actualizacion(self.admin.pk)

    def test_sin_catalogo_avisa_como_cargarlo(self):
        CatalogoVersion.objects.update(estado=CatalogoVersion.HISTORICO)
        with self.assertRaisesMessage(ValidationError, 'Solicite al equipo de soporte que cargue el catálogo.'):
            servicio.lanzar_actualizacion(self.admin.pk)


class ProcesarTests(Base):

    def test_guarda_publicaciones_sin_duplicar_por_doi_ni_por_titulo(self):
        fuente = FuenteFalsa([LOCK_IN, LOCK_IN_DUPLICADO, SIN_DOI])
        self.lanzar_y_procesar(fuente, [self.bloqueo.pk, self.usabilidad.pk])

        self.assertEqual(Publicacion.objects.count(), 2)
        lock = Publicacion.objects.get(doi='10.1/lock')
        self.assertEqual(lock.fuente, 'Fuente falsa')
        # Cada búsqueda registra la publicación una vez, con su posición.
        self.assertEqual(BusquedaPublicacion.objects.filter(publicacion=lock).count(), 2)
        self.assertEqual(set(BusquedaBibliografica.objects.values_list('estado', flat=True)),
                         {BusquedaBibliografica.COMPLETADA})

    def test_no_crea_sugerencias_antes_del_analisis_ia_a_demanda(self):
        self.lanzar_y_procesar(FuenteFalsa([LOCK_IN, SIN_DOI]), [self.bloqueo.pk])
        self.assertFalse(PublicacionFactor.objects.exists())

    def test_si_la_fuente_falla_la_busqueda_queda_fallida_y_las_demas_siguen(self):
        fuente = FuenteFalsa([LOCK_IN], fallar_en=['"usability"'])
        self.lanzar_y_procesar(fuente, [self.bloqueo.pk, self.usabilidad.pk])
        fallida = BusquedaBibliografica.objects.get(factor=self.usabilidad)
        self.assertEqual(fallida.estado, BusquedaBibliografica.FALLIDA)
        self.assertIn('no disponible', fallida.mensaje_error)
        self.assertEqual(BusquedaBibliografica.objects.get(factor=self.bloqueo).estado,
                         BusquedaBibliografica.COMPLETADA)

    def test_estado_del_lote(self):
        lote = servicio.lanzar_actualizacion(self.admin.pk, [self.bloqueo.pk, self.usabilidad.pk])
        estado = servicio.estado_lote()
        self.assertEqual((estado['lote'], estado['total'], estado['terminado'], estado['progreso']),
                         (str(lote), 2, False, 0))
        servicio.procesar_pendientes(fuente=FuenteFalsa([LOCK_IN]))
        estado = servicio.estado_lote(lote)
        self.assertEqual((estado['terminado'], estado['progreso']), (True, 100))


class RevisionTests(Base):

    def setUp(self):
        self.lanzar_y_procesar(FuenteFalsa([LOCK_IN, SIN_DOI, ANTIGUA]), [self.bloqueo.pk])
        self.busqueda = BusquedaBibliografica.objects.get()
        self.lock = Publicacion.objects.get(doi='10.1/lock')
        servicio.sugerir_publicaciones_ia(
            self.admin.pk,
            self.busqueda.pk,
            lambda entrada: {
                'sugerencias': [{
                    'publicacion_id': self.lock.pk,
                    'pertinencia': 92,
                    'justificacion': 'El resumen estudia dependencia del proveedor.',
                }]
            },
        )

    def test_aprobar_marca_la_publicacion_como_seleccionada(self):
        v = self.vinculo(self.lock, self.bloqueo)
        servicio.revisar_vinculo(self.admin.pk, self.busqueda.pk, v.pk, aprobar=True)
        v.refresh_from_db()
        self.assertEqual((v.estado, v.revisado_por), (PublicacionFactor.APROBADA, self.admin))
        self.assertTrue(BusquedaPublicacion.objects.get(busqueda=self.busqueda, publicacion=self.lock).seleccionada)

    def test_rechazar(self):
        v = self.vinculo(self.lock, self.bloqueo)
        servicio.revisar_vinculo(self.admin.pk, self.busqueda.pk, v.pk, aprobar=False)
        v.refresh_from_db()
        self.assertEqual(v.estado, PublicacionFactor.RECHAZADA)

    def test_vincular_a_mano_queda_aprobado(self):
        soporte = Factor.objects.get(nombre='Soporte')
        v = servicio.vincular_manual(self.admin.pk, self.busqueda.pk, self.lock.pk, soporte.pk, 'Habla de soporte')
        self.assertEqual((v.estado, v.origen, v.justificacion),
                         (PublicacionFactor.APROBADA, PublicacionFactor.MANUAL, 'Habla de soporte'))

    def test_no_revisa_publicaciones_de_otra_busqueda(self):
        otra = BusquedaBibliografica.objects.create(consulta='x', fuente='f')
        v = self.vinculo(self.lock, self.bloqueo)
        with self.assertRaises(ValidationError):
            servicio.revisar_vinculo(self.admin.pk, otra.pk, v.pk, aprobar=True)

    def test_el_decisor_no_puede_revisar(self):
        v = self.vinculo(self.lock, self.bloqueo)
        with self.assertRaises(PermissionDenied):
            servicio.revisar_vinculo(self.decisor.pk, self.busqueda.pk, v.pk, aprobar=True)


class SugerenciasIATests(Base):

    def setUp(self):
        self.lanzar_y_procesar(FuenteFalsa([LOCK_IN, SIN_DOI]), [self.bloqueo.pk])
        self.busqueda = BusquedaBibliografica.objects.get()
        self.lock = Publicacion.objects.get(doi='10.1/lock')

    def test_guarda_sugerencia_de_ia_pendiente_con_justificacion(self):
        def proveedor(entrada):
            self.assertEqual(entrada['factor']['nombre'], self.bloqueo.nombre)
            return {
                'sugerencias': [{
                    'publicacion_id': self.lock.pk,
                    'pertinencia': 91.5,
                    'justificacion': 'El resumen aborda dependencia de proveedores.',
                }]
            }

        total = servicio.sugerir_publicaciones_ia(self.admin.pk, self.busqueda.pk, proveedor)

        vinculo = self.vinculo(self.lock, self.bloqueo)
        self.busqueda.refresh_from_db()
        self.assertEqual(total, 1)
        self.assertEqual((vinculo.estado, vinculo.origen), (PublicacionFactor.SUGERIDA, PublicacionFactor.IA))
        self.assertEqual(vinculo.pertinencia, 91.5)
        self.assertIn('dependencia de proveedores', vinculo.justificacion)
        self.assertTrue(self.busqueda.analisis_ia_completado)

    def test_rechaza_ids_que_no_pertenecen_al_lote_y_no_persiste_nada(self):
        with self.assertRaisesMessage(AnalisisNoDisponible, 'publicación inexistente o repetida'):
            servicio.sugerir_publicaciones_ia(
                self.admin.pk, self.busqueda.pk,
                lambda entrada: {
                    'sugerencias': [{
                        'publicacion_id': 999999,
                        'pertinencia': 80,
                        'justificacion': 'No verificable.',
                    }]
                },
            )
        self.assertFalse(PublicacionFactor.objects.exists())
        self.busqueda.refresh_from_db()
        self.assertFalse(self.busqueda.analisis_ia_completado)

    def test_el_analisis_ia_requiere_administrador(self):
        with self.assertRaises(PermissionDenied):
            servicio.sugerir_publicaciones_ia(self.decisor.pk, self.busqueda.pk, lambda _: {})

    def test_contexto_bibliografico_modificado_no_persiste_sugerencias(self):
        def proveedor(_):
            Publicacion.objects.filter(pk=self.lock.pk).update(resumen='Resumen editado.')
            return {'sugerencias': [{'publicacion_id': self.lock.pk, 'pertinencia': 80,
                                     'justificacion': 'Justificación del resumen anterior.'}]}

        with self.assertRaisesMessage(ValidationError, 'resultados de la búsqueda cambiaron'):
            servicio.sugerir_publicaciones_ia(self.admin.pk, self.busqueda.pk, proveedor)
        self.assertFalse(PublicacionFactor.objects.exists())


class VersionesTests(Base):

    def aprobar(self, publicacion, factor):
        busqueda = BusquedaBibliografica.objects.filter(resultados__publicacion=publicacion).first()
        servicio.vincular_manual(self.admin.pk, busqueda.pk, publicacion.pk, factor.pk)

    def setUp(self):
        self.lanzar_y_procesar(FuenteFalsa([LOCK_IN, SIN_DOI, ANTIGUA]), [self.bloqueo.pk])
        self.lock = Publicacion.objects.get(doi='10.1/lock')
        self.sin_doi = Publicacion.objects.get(doi=None)
        self.antigua = Publicacion.objects.get(doi='10.1/old')
        self.v1 = CatalogoVersion.objects.get(version='v1-2021')

    def indicador(self, version, factor):
        return IndicadorFactor.objects.get(catalogo=version, factor=factor)

    def test_tc_es_el_de_2021_mas_las_aprobadas_del_periodo(self):
        self.aprobar(self.lock, self.bloqueo)
        self.aprobar(self.sin_doi, self.bloqueo)
        self.aprobar(self.antigua, self.bloqueo)   # 2018: no cuenta
        borrador = servicio.crear_borrador(self.admin.pk)
        i = self.indicador(borrador, self.bloqueo)
        self.assertEqual((i.total_citas_base, i.total_citas), (3, 5))
        self.assertEqual(i.relacion_ri, 5)
        # Las sugerencias sin aprobar no cuentan.
        self.assertEqual(self.indicador(borrador, self.usabilidad).total_citas, 14)

    def test_volver_a_recalcular_no_cuenta_dos_veces(self):
        self.aprobar(self.lock, self.bloqueo)
        servicio.crear_borrador(self.admin.pk)
        servicio.publicar_borrador(self.admin.pk)
        borrador = servicio.crear_borrador(self.admin.pk)
        self.assertEqual(self.indicador(borrador, self.bloqueo).total_citas, 4)

    def test_publicar_deja_una_sola_activa_y_conserva_la_anterior(self):
        self.aprobar(self.lock, self.bloqueo)
        borrador = servicio.crear_borrador(self.admin.pk)
        self.assertEqual(borrador.estado, CatalogoVersion.BORRADOR)
        servicio.publicar_borrador(self.admin.pk)

        borrador.refresh_from_db()
        self.v1.refresh_from_db()
        self.assertEqual(borrador.estado, CatalogoVersion.ACTIVO)
        self.assertEqual(borrador.publicado_por, self.admin)
        self.assertEqual(self.v1.estado, CatalogoVersion.HISTORICO)
        self.assertEqual(self.indicador(self.v1, self.bloqueo).total_citas, 3)
        self.assertEqual(servicio.indicadores_literatura().version, borrador.version)

    def test_las_evaluaciones_previas_conservan_su_version(self):
        organizacion = Organizacion.objects.create(nombre='Org')
        evaluacion = Evaluacion.objects.create(
            organizacion=organizacion, usuario=self.decisor, catalogo=self.v1,
            software=Software.objects.create(nombre='LibreOffice'))
        self.aprobar(self.lock, self.bloqueo)
        servicio.crear_borrador(self.admin.pk)
        servicio.publicar_borrador(self.admin.pk)
        evaluacion.refresh_from_db()
        self.assertEqual(evaluacion.catalogo, self.v1)
        self.assertEqual(self.indicador(evaluacion.catalogo, self.bloqueo).total_citas, 3)

    def test_recalcular_reemplaza_el_borrador_y_descartar_lo_borra(self):
        primero = servicio.crear_borrador(self.admin.pk)
        segundo = servicio.crear_borrador(self.admin.pk)
        self.assertFalse(CatalogoVersion.objects.filter(pk=primero.pk).exists())
        self.assertEqual(CatalogoVersion.objects.filter(estado=CatalogoVersion.BORRADOR).get(), segundo)
        servicio.descartar_borrador(self.admin.pk)
        self.assertFalse(CatalogoVersion.objects.filter(estado=CatalogoVersion.BORRADOR).exists())

    def test_publicar_sin_borrador_falla(self):
        with self.assertRaises(ValidationError):
            servicio.publicar_borrador(self.admin.pk)

    def test_un_factor_desactivado_no_entra_en_la_nueva_version(self):
        Factor.objects.filter(pk=self.usabilidad.pk).update(activo=False)
        borrador = servicio.crear_borrador(self.admin.pk)
        self.assertFalse(IndicadorFactor.objects.filter(catalogo=borrador, factor=self.usabilidad).exists())
        self.assertTrue(IndicadorFactor.objects.filter(catalogo=self.v1, factor=self.usabilidad).exists())

    def test_la_base_impide_dos_versiones_activas(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CatalogoVersion.objects.create(version='otra', fecha_creacion='2026-01-01',
                                           estado=CatalogoVersion.ACTIVO)

    def test_comparacion_muestra_antes_y_despues(self):
        self.aprobar(self.lock, self.bloqueo)
        servicio.crear_borrador(self.admin.pk)
        filas = {f.factor: f for f in servicio.comparacion_versiones().filas}
        self.assertEqual(len(filas), 18)
        f = filas['Bloqueo de proveedores']
        self.assertEqual((f.tc_base, f.nuevas, f.tc_activa, f.tc_borrador), (3, 1, 3, 4))
