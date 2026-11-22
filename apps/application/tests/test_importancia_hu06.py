"""HU06 - Importancia de los factores: ID, IR y exclusión de factores con IR = 1."""

from datetime import date

from django.test import TestCase

from apps.application.services.evaluation import EvaluationService
from apps.application.services.importancia import ImportanciaFactoresService, ImportanciaInvalidaError
from apps.data.models import (
    CatalogoVersion, Dimension, EvaluacionFactor, Factor, IndicadorFactor, Subfactor, Usuario,
    ValoracionSubfactor,
)


def crear_catalogo_con_factores(sugeridas, subfactores=0):
    """Catálogo ACTIVO con un factor por cada IS de `sugeridas` ({nombre: IS}) y `subfactores` cada uno."""
    CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
    catalogo = CatalogoVersion.objects.create(
        version=f'HU06-TEST-{CatalogoVersion.objects.count() + 1}', fecha_creacion=date.today(), estado='ACTIVO')
    dimension, _ = Dimension.objects.get_or_create(nombre='Tecnológica')
    for nombre, sugerida in sugeridas.items():
        factor, _ = Factor.objects.get_or_create(dimension=dimension, nombre=nombre, defaults={'alcance': 'interno'})
        for n in range(subfactores):
            Subfactor.objects.get_or_create(factor=factor, descripcion=f'{nombre} · requisito {n + 1}')
        IndicadorFactor.objects.create(
            catalogo=catalogo, factor=factor, numero_subfactores=max(subfactores, 1), importancia_sugerida=sugerida)
    return catalogo


def crear_decisor(correo='decisor.hu06@guios.test'):
    return Usuario.objects.create_user(
        correo=correo, password='Clave-Segura-123', nombre='Decisor HU06', rol=Usuario.DECISOR)


def registrar_evaluacion(decisor, software='LibreOffice'):
    return EvaluationService.crear_evaluacion(decisor, {
        'nombre_organizacion': 'Instituto QA', 'nombre_software': software})


class ServicioImportanciaTests(TestCase):

    def setUp(self):
        crear_catalogo_con_factores({'Compatibilidad': 3, 'Documentación': 2})
        self.decisor = crear_decisor()
        self.evaluacion = registrar_evaluacion(self.decisor)
        self.servicio = ImportanciaFactoresService()

    def ids(self, **por_nombre):
        """{factor_id: ID}: la IS por defecto y el valor indicado para el factor nombrado."""
        return {f.factor_id: por_nombre.get(f.nombre, f.is_) for f in self.servicio.filas(self.evaluacion)}

    def test_la_id_parte_de_la_is_sugerida(self):
        filas = {f.nombre: f for f in self.servicio.filas(self.evaluacion)}
        self.assertEqual((filas['Compatibilidad'].is_, filas['Compatibilidad'].id_), (3, 3))
        self.assertEqual((filas['Documentación'].is_, filas['Documentación'].id_), (2, 2))

    def test_guardar_calcula_ir_y_excluye_los_irrelevantes(self):
        # Documentación: IS 2 e ID 1 -> IR 1 (se excluye). Compatibilidad: IS 3 e ID 4 -> IR 3.
        self.servicio.guardar(self.evaluacion, self.ids(Compatibilidad=4, Documentación=1))
        guardados = {ef.factor.nombre: ef for ef in EvaluacionFactor.objects.filter(evaluacion=self.evaluacion)}
        self.assertEqual(guardados['Compatibilidad'].importancia_relativa, 3)
        self.assertTrue(guardados['Compatibilidad'].relevante)
        self.assertEqual(guardados['Documentación'].importancia_relativa, 1)
        self.assertFalse(guardados['Documentación'].relevante)
        self.assertEqual(guardados['Documentación'].importancia_sugerida, 2)
        self.assertEqual(guardados['Documentación'].importancia_decisor, 1)

    def test_volver_a_guardar_actualiza_sin_duplicar(self):
        self.servicio.guardar(self.evaluacion, self.ids())
        self.servicio.guardar(self.evaluacion, self.ids(Compatibilidad=4))
        self.assertEqual(EvaluacionFactor.objects.filter(evaluacion=self.evaluacion).count(), 2)

    def test_rechaza_valores_fuera_de_rango_o_faltantes(self):
        for malo in (self.ids(Compatibilidad=5), self.ids(Compatibilidad=0), self.ids(Compatibilidad=True)):
            with self.assertRaises(ImportanciaInvalidaError):
                self.servicio.guardar(self.evaluacion, malo)
        faltante = self.ids()
        faltante.popitem()
        with self.assertRaises(ImportanciaInvalidaError):
            self.servicio.guardar(self.evaluacion, faltante)
        self.assertFalse(EvaluacionFactor.objects.filter(evaluacion=self.evaluacion).exists())

    def test_exige_al_menos_un_factor_relevante(self):
        # IS 3 con ID 1 -> IR 2 (nunca 1); IS 2 con ID 1 -> IR 1. Con IS 2 y 3, solo Documentación puede excluirse.
        # Se fuerza el caso con un catálogo cuyos factores sean todos de IS 2.
        crear_catalogo_con_factores({'Único': 2})
        evaluacion = registrar_evaluacion(self.decisor, 'Otro software')
        filas = self.servicio.filas(evaluacion)
        with self.assertRaises(ImportanciaInvalidaError):
            self.servicio.guardar(evaluacion, {f.factor_id: 1 for f in filas})
        self.assertFalse(EvaluacionFactor.objects.filter(evaluacion=evaluacion).exists())

    def test_no_permite_cambiar_si_ya_hay_valoraciones_con_avance(self):
        self.servicio.guardar(self.evaluacion, self.ids())
        ef = EvaluacionFactor.objects.filter(evaluacion=self.evaluacion).first()
        subfactor = Subfactor.objects.create(factor=ef.factor, descripcion='Subfactor de prueba')
        ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=subfactor, valor_confirmado=3)
        with self.assertRaises(ImportanciaInvalidaError):
            self.servicio.guardar(self.evaluacion, self.ids(Compatibilidad=4))

    def test_evaluacion_del_decisor_solo_devuelve_las_propias(self):
        otro = crear_decisor('otro.decisor@guios.test')
        self.assertEqual(self.servicio.evaluacion_del_decisor(self.decisor), self.evaluacion)
        self.assertEqual(
            self.servicio.evaluacion_del_decisor(self.decisor, self.evaluacion.pk), self.evaluacion)
        self.assertIsNone(self.servicio.evaluacion_del_decisor(otro))
        self.assertIsNone(self.servicio.evaluacion_del_decisor(otro, self.evaluacion.pk))

    def test_tiene_importancias(self):
        self.assertFalse(self.servicio.tiene_importancias(self.evaluacion))
        self.servicio.guardar(self.evaluacion, self.ids())
        self.assertTrue(self.servicio.tiene_importancias(self.evaluacion))


class PrepararValoracionesTests(TestCase):
    """Al guardar la importancia quedan listas las valoraciones pendientes de los subfactores."""

    def setUp(self):
        crear_catalogo_con_factores({'Compatibilidad': 3, 'Documentación': 2}, subfactores=2)
        self.decisor = crear_decisor('prepara@guios.test')
        self.evaluacion = registrar_evaluacion(self.decisor)
        self.servicio = ImportanciaFactoresService()

    def ids(self, **por_nombre):
        return {f.factor_id: por_nombre.get(f.nombre, f.is_) for f in self.servicio.filas(self.evaluacion)}

    def valoraciones(self):
        return ValoracionSubfactor.objects.filter(evaluacion_factor__evaluacion=self.evaluacion)

    def test_crea_una_valoracion_pendiente_por_subfactor_de_factor_relevante(self):
        self.servicio.guardar(self.evaluacion, self.ids())
        self.assertEqual(self.valoraciones().count(), 4)
        self.assertFalse(self.valoraciones().exclude(estado_validacion=ValoracionSubfactor.PENDIENTE).exists())
        self.assertFalse(self.valoraciones().filter(valor_ia__isnull=False).exists())

    def test_los_factores_excluidos_no_generan_valoraciones(self):
        self.servicio.guardar(self.evaluacion, self.ids(Documentación=1))
        nombres = set(self.valoraciones().values_list('evaluacion_factor__factor__nombre', flat=True))
        self.assertEqual(nombres, {'Compatibilidad'})
        self.assertEqual(self.valoraciones().count(), 2)

    def test_guardar_otra_vez_no_duplica_y_ajusta_los_cambios(self):
        self.servicio.guardar(self.evaluacion, self.ids())
        self.servicio.guardar(self.evaluacion, self.ids())
        self.assertEqual(self.valoraciones().count(), 4)
        self.servicio.guardar(self.evaluacion, self.ids(Documentación=1))
        self.assertEqual(self.valoraciones().count(), 2)
        self.servicio.guardar(self.evaluacion, self.ids())
        self.assertEqual(self.valoraciones().count(), 4)

    def test_ignora_subfactores_inactivos(self):
        Subfactor.objects.filter(descripcion__startswith='Compatibilidad').update(activo=False)
        self.servicio.guardar(self.evaluacion, self.ids())
        self.assertEqual(self.valoraciones().count(), 2)

    def test_con_avance_ya_no_deja_cambiar_la_importancia(self):
        self.servicio.guardar(self.evaluacion, self.ids())
        self.valoraciones().update(valor_ia=3)
        with self.assertRaises(ImportanciaInvalidaError):
            self.servicio.guardar(self.evaluacion, self.ids(Documentación=1))
        self.assertEqual(self.valoraciones().count(), 4)
