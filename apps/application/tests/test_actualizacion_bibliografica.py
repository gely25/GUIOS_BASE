"""Pruebas de la actualización bibliográfica (HU02). La fuente es simulada: no usa red."""

from types import SimpleNamespace

from django.test import TestCase

from apps.application.services.actualizacion_bibliografica import (
    ActualizacionBibliografica,
    total_citas_por_factor,
)
from apps.application.services.actualizacion_bibliografica.consultas import construir_consulta
from apps.data.models.bibliografia import (
    BusquedaBibliografica,
    BusquedaPublicacion,
    Publicacion,
    PublicacionFactor,
)
from apps.data.models.catalogo import Dimension, Factor
from apps.external_services.openalex import OpenAlexError


def pub(titulo, anio=2022, doi=None, url=None, openalex_id=None):
    return SimpleNamespace(titulo=titulo, anio=anio, doi=doi, url=url, openalex_id=openalex_id)


class BuscadorFalso:
    """Devuelve lo que se le indique según una palabra de la consulta."""

    def __init__(self, respuestas=None, falla_en=None):
        self.respuestas = respuestas or {}
        self.falla_en = falla_en
        self.llamadas = []

    def buscar(self, texto, anio_inicio, anio_fin, limite):
        self.llamadas.append((texto, anio_inicio, anio_fin, limite))
        if self.falla_en and self.falla_en in texto:
            raise OpenAlexError("límite de consultas")
        for clave, lista in self.respuestas.items():
            if clave in texto:
                return lista
        return []


class BaseTests(TestCase):
    def setUp(self):
        dim = Dimension.objects.create(nombre="Tecnológica")
        self.compat = Factor.objects.create(dimension=dim, nombre="Compatibilidad", alcance="interno")
        self.fiab = Factor.objects.create(dimension=dim, nombre="Fiabilidad", alcance="interno")


class ConsultasTests(TestCase):
    def test_consulta_booleana_con_termino_y_contexto(self):
        self.assertEqual(
            construir_consulta("Compatibilidad"),
            '("compatibility" OR "interoperability") AND '
            '("open source software" OR "free software" OR "FLOSS") AND adoption')

    def test_cada_factor_del_catalogo_tiene_terminos_en_ingles(self):
        from apps.data.management.commands.cargar_catalogo_demo import CATALOGO_REFERENCIA
        from apps.application.services.actualizacion_bibliografica.consultas import TERMINOS_POR_FACTOR
        for _dim, nombre, *_ in CATALOGO_REFERENCIA:
            self.assertIn(nombre.lower(), TERMINOS_POR_FACTOR, nombre)

    def test_quita_comillas_del_nombre_de_un_factor_desconocido(self):
        self.assertTrue(construir_consulta('Factor "raro"').startswith('("Factor raro")'))

    def test_nombre_del_catalogo_para_tco(self):
        self.assertIn('"total cost of ownership"', construir_consulta("Coste total de propiedad"))

    def test_factor_desconocido_usa_su_nombre(self):
        self.assertTrue(construir_consulta("Factor nuevo").startswith('("Factor nuevo") AND '))

    def test_nombre_vacio_falla(self):
        with self.assertRaises(ValueError):
            construir_consulta("  ")


class ActualizarTests(BaseTests):
    def test_guarda_busqueda_publicaciones_y_relaciones(self):
        buscador = BuscadorFalso({"compatibility": [pub("A", doi="10.1/a"), pub("B", doi="10.1/b")]})
        res = ActualizacionBibliografica(buscador).actualizar()

        self.assertEqual(BusquedaBibliografica.objects.count(), 2)  # una por factor
        b = BusquedaBibliografica.objects.get(consulta__contains="compatibility")
        self.assertEqual((b.anio_inicio, b.anio_fin, b.estado, b.fuente), (2020, 2025, "COMPLETADA", "OpenAlex"))
        self.assertEqual(Publicacion.objects.count(), 2)
        self.assertEqual(BusquedaPublicacion.objects.filter(busqueda=b, seleccionada=True).count(), 2)
        self.assertEqual(list(BusquedaPublicacion.objects.filter(busqueda=b).values_list("posicion", flat=True).order_by("posicion")), [1, 2])
        self.assertEqual(PublicacionFactor.objects.filter(factor=self.compat).count(), 2)
        self.assertEqual(res.tc_por_factor, {self.compat.factor_id: 2})

    def test_pasa_periodo_y_limite_a_la_fuente(self):
        buscador = BuscadorFalso()
        ActualizacionBibliografica(buscador).actualizar(2021, 2024, 10)
        self.assertTrue(all(l[1:] == (2021, 2024, 10) for l in buscador.llamadas))
        self.assertEqual(len(buscador.llamadas), 2)

    def test_sin_resultados(self):
        res = ActualizacionBibliografica(BuscadorFalso()).actualizar()
        self.assertEqual({f.estado for f in res.factores}, {"SIN_RESULTADOS"})
        self.assertEqual(Publicacion.objects.count(), 0)
        self.assertEqual(res.tc_por_factor, {})

    def test_duplicado_por_doi_entre_factores(self):
        comun = pub("Común", doi="10.1/x")
        buscador = BuscadorFalso({"compatibility": [comun], "reliability": [comun]})
        res = ActualizacionBibliografica(buscador).actualizar()
        self.assertEqual(Publicacion.objects.count(), 1)
        self.assertEqual(PublicacionFactor.objects.count(), 2)
        self.assertEqual(res.total_publicaciones_nuevas, 1)

    def test_sin_doi_usa_el_enlace(self):
        p = pub("Sin DOI", url="https://openalex.org/W1")
        buscador = BuscadorFalso({"compatibility": [p, p], "reliability": [p]})
        ActualizacionBibliografica(buscador).actualizar()
        self.assertEqual(Publicacion.objects.count(), 1)
        self.assertIsNone(Publicacion.objects.get().doi)

    def test_sin_doi_ni_url_usa_el_identificador_openalex(self):
        p = pub("Solo id", openalex_id="https://openalex.org/W9")
        ActualizacionBibliografica(BuscadorFalso({"compatibility": [p]})).actualizar()
        self.assertEqual(Publicacion.objects.get().url, "https://openalex.org/W9")

    def test_sin_doi_ni_enlace_se_omite(self):
        buscador = BuscadorFalso({"compatibility": [pub("Anónima")]})
        res = ActualizacionBibliografica(buscador).actualizar()
        self.assertEqual(Publicacion.objects.count(), 0)
        self.assertEqual(res.factores[0].estado, "SIN_RESULTADOS")

    def test_repetir_la_busqueda_no_duplica_relaciones(self):
        buscador = BuscadorFalso({"compatibility": [pub("A", doi="10.1/a")]})
        servicio = ActualizacionBibliografica(buscador)
        servicio.actualizar()
        res = servicio.actualizar()
        self.assertEqual(Publicacion.objects.count(), 1)
        self.assertEqual(PublicacionFactor.objects.count(), 1)
        self.assertEqual(BusquedaBibliografica.objects.count(), 4)  # cada ejecución se conserva
        self.assertEqual(res.total_publicaciones_nuevas, 0)

    def test_error_de_un_factor_no_detiene_a_los_demas(self):
        buscador = BuscadorFalso({"reliability": [pub("R", doi="10.1/r")]}, falla_en="compatibility")
        res = ActualizacionBibliografica(buscador).actualizar()
        por_nombre = {f.factor: f for f in res.factores}
        self.assertEqual(por_nombre["Compatibilidad"].estado, "ERROR")
        self.assertIn("límite", por_nombre["Compatibilidad"].error)
        self.assertEqual(por_nombre["Fiabilidad"].estado, "COMPLETADA")
        self.assertTrue(res.hubo_errores)
        self.assertEqual(BusquedaBibliografica.objects.get(consulta__contains="compatibility").estado, "ERROR")

    def test_factores_inactivos_no_se_buscan(self):
        self.fiab.activo = False
        self.fiab.save()
        buscador = BuscadorFalso()
        ActualizacionBibliografica(buscador).actualizar()
        self.assertEqual(len(buscador.llamadas), 1)

    def test_parametros_invalidos(self):
        servicio = ActualizacionBibliografica(BuscadorFalso())
        with self.assertRaises(ValueError):
            servicio.actualizar(2025, 2020)
        with self.assertRaises(ValueError):
            servicio.actualizar(limite=0)
        self.assertEqual(BusquedaBibliografica.objects.count(), 0)


class BuscadorConConteo:
    def __init__(self, totales=None, falla_en=None):
        self.totales = totales or {}
        self.falla_en = falla_en

    def contar(self, texto, anio_inicio, anio_fin):
        if self.falla_en and self.falla_en in texto:
            raise OpenAlexError("límite de consultas")
        for clave, total in self.totales.items():
            if clave in texto:
                return total
        return 0


class TotalesPorFactorTests(BaseTests):
    def test_devuelve_el_total_de_cada_factor_sin_guardar_nada(self):
        buscador = BuscadorConConteo({"compatibility": 1200, "reliability": 300})
        filas = ActualizacionBibliografica(buscador).totales_por_factor(2020, 2025)
        self.assertEqual({f.factor: f.total for f in filas}, {"Compatibilidad": 1200, "Fiabilidad": 300})
        self.assertEqual(BusquedaBibliografica.objects.count(), 0)
        self.assertEqual(Publicacion.objects.count(), 0)

    def test_un_error_se_anota_en_ese_factor_y_sigue(self):
        buscador = BuscadorConConteo({"reliability": 5}, falla_en="compatibility")
        filas = {f.factor: f for f in ActualizacionBibliografica(buscador).totales_por_factor()}
        self.assertIsNone(filas["Compatibilidad"].total)
        self.assertIn("límite", filas["Compatibilidad"].error)
        self.assertEqual(filas["Fiabilidad"].total, 5)

    def test_rango_invalido(self):
        with self.assertRaises(ValueError):
            ActualizacionBibliografica(BuscadorConConteo()).totales_por_factor(2025, 2020)


class TotalCitasTests(BaseTests):
    def test_cuenta_solo_publicaciones_del_periodo(self):
        for i, anio in enumerate([2019, 2020, 2025, 2026, None]):
            p = Publicacion.objects.create(titulo=f"P{i}", anio=anio, doi=f"10.1/{i}")
            PublicacionFactor.objects.create(publicacion=p, factor=self.compat)
        self.assertEqual(total_citas_por_factor(2020, 2025), {self.compat.factor_id: 2})
