"""HU12: PM y clasificación FODA a partir de valoraciones confirmadas."""
from datetime import date
from decimal import Decimal
from fractions import Fraction

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings

from apps.application.services.pm_foda import PmFodaService as Servicio, _redondear
from apps.application.services.revision_humana import RevisionHumanaService
from apps.data.models import (CatalogoVersion, Dimension, Evaluacion, EvaluacionFactor, Factor,
                              Organizacion, Software, Subfactor, Usuario, ValoracionSubfactor)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PmFodaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        org = Organizacion.objects.create(nombre='Org HU12')
        cls.actor = Usuario.objects.create_user('hu12@test.local', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cls.otro = Usuario.objects.create_user('otro12@test.local', 'Clave-test-123', nombre='Otro', organizacion=org)
        catalogo = CatalogoVersion.objects.create(version='HU12 test', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor,
                                           software=Software.objects.create(nombre='Soft HU12'), catalogo=catalogo)
        dim = Dimension.objects.create(nombre='Tecnológica')
        cls.f_ext = Factor.objects.create(dimension=dim, nombre='Compatibilidad', alcance=Factor.EXTERNO)
        cls.f_int = Factor.objects.create(dimension=dim, nombre='Usabilidad', alcance=Factor.INTERNO)
        cls.f_amb = Factor.objects.create(dimension=dim, nombre='Soporte', alcance=Factor.AMBOS)
        cls.v = {}
        for factor, ir, valores in [(cls.f_ext, 3, (4, 4, 3)), (cls.f_int, 4, (2, 3)), (cls.f_amb, 3, (4, 3))]:
            ef = EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=factor, importancia_relativa=ir)
            for i, valor in enumerate(valores):
                sf = Subfactor.objects.create(factor=factor, descripcion=f'{factor.nombre} {i}')
                cls.v[(factor.nombre, i)] = (ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=sf), valor)
        # Factor excluido: no debe participar.
        EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=Factor.objects.create(
            dimension=dim, nombre='Excluido', alcance=Factor.INTERNO), importancia_relativa=1, relevante=False)

    def confirmar_todo(self):
        for (nombre, _), (v, valor) in self.v.items():
            version = RevisionHumanaService.obtener(self.actor, self.ev.pk, v.pk)['version']
            RevisionHumanaService.resolver(self.actor, self.ev.pk, v.pk, 'MANUAL', valor, 'Confirmada en prueba.', version)

    def ef(self, factor):
        return EvaluacionFactor.objects.get(evaluacion=self.ev, factor=factor)

    def test_vista_previa_sin_valoraciones_confirmadas_no_esta_lista(self):
        r = Servicio.vista_previa(self.actor, self.ev.pk)
        self.assertFalse(r['lista'])
        self.assertTrue(r['motivo'])

    def test_calcula_y_guarda_pm_y_foda(self):
        self.confirmar_todo()
        filas = Servicio.calcular_y_guardar(self.actor, self.ev.pk, {self.f_amb.pk: 'interno'})
        self.assertEqual(len(filas), 3)
        ext, interno, amb = self.ef(self.f_ext), self.ef(self.f_int), self.ef(self.f_amb)
        self.assertEqual((ext.ponderacion_media, ext.clasificacion_foda), (Decimal('3.67'), 'Oportunidad'))
        self.assertEqual((interno.ponderacion_media, interno.clasificacion_foda), (Decimal('2.50'), 'Debilidad'))
        self.assertEqual((amb.ponderacion_media, amb.clasificacion_foda), (Decimal('3.50'), 'Fortaleza'))
        excluido = EvaluacionFactor.objects.get(evaluacion=self.ev, relevante=False)
        self.assertIsNone(excluido.ponderacion_media)

    def test_soporte_externo_da_oportunidad(self):
        self.confirmar_todo()
        Servicio.calcular_y_guardar(self.actor, self.ev.pk, {self.f_amb.pk: 'externo'})
        self.assertEqual(self.ef(self.f_amb).clasificacion_foda, 'Oportunidad')

    def test_exige_elegir_alcance_del_factor_mixto_y_no_guarda_nada(self):
        self.confirmar_todo()
        for alcances in (None, {}, {self.f_amb.pk: ''}, {self.f_amb.pk: 'ambos'}):
            with self.subTest(alcances=alcances), self.assertRaises(ValidationError):
                Servicio.calcular_y_guardar(self.actor, self.ev.pk, alcances)
        self.assertIsNone(self.ef(self.f_ext).ponderacion_media)

    def test_ignora_elecciones_sobre_factores_con_alcance_fijo(self):
        self.confirmar_todo()
        Servicio.calcular_y_guardar(self.actor, self.ev.pk, {self.f_amb.pk: 'interno', self.f_ext.pk: 'interno'})
        self.assertEqual(self.ef(self.f_ext).clasificacion_foda, 'Oportunidad')

    def test_rechaza_si_faltan_valoraciones_confirmadas(self):
        (v, valor), = [self.v[('Compatibilidad', 0)]]
        version = RevisionHumanaService.obtener(self.actor, self.ev.pk, v.pk)['version']
        RevisionHumanaService.resolver(self.actor, self.ev.pk, v.pk, 'MANUAL', valor, 'Solo una.', version)
        with self.assertRaises(ValidationError):
            Servicio.calcular_y_guardar(self.actor, self.ev.pk, {self.f_amb.pk: 'interno'})
        self.assertIsNone(self.ef(self.f_ext).ponderacion_media)

    def test_otro_decisor_no_puede_calcular(self):
        self.confirmar_todo()
        with self.assertRaises(PermissionDenied):
            Servicio.calcular_y_guardar(self.otro, self.ev.pk, {self.f_amb.pk: 'interno'})

    def test_evaluacion_cerrada_no_admite_calculo(self):
        self.confirmar_todo()
        Evaluacion.objects.filter(pk=self.ev.pk).update(estado='CERRADA')
        with self.assertRaises(ValidationError):
            Servicio.calcular_y_guardar(self.actor, self.ev.pk, {self.f_amb.pk: 'interno'})

    def test_vista_previa_recupera_la_eleccion_guardada(self):
        self.confirmar_todo()
        Servicio.calcular_y_guardar(self.actor, self.ev.pk, {self.f_amb.pk: 'externo'})
        r = Servicio.vista_previa(self.actor, self.ev.pk)
        self.assertTrue(r['lista'] and r['guardado'])
        soporte = next(f for f in r['filas'] if f['factor'] == 'Soporte')
        self.assertEqual((soporte['alcance'], soporte['foda']), ('externo', 'Oportunidad'))

    def test_reabrir_una_valoracion_retira_pm_y_foda(self):
        self.confirmar_todo()
        Servicio.calcular_y_guardar(self.actor, self.ev.pk, {self.f_amb.pk: 'interno'})
        v, _ = self.v[('Compatibilidad', 0)]
        version = RevisionHumanaService.obtener(self.actor, self.ev.pk, v.pk)['version']
        RevisionHumanaService.reabrir(self.actor, self.ev.pk, v.pk, 'Corregir dato.', version)
        self.assertIsNone(self.ef(self.f_ext).ponderacion_media)
        self.assertIsNone(self.ef(self.f_amb).clasificacion_foda)
        self.assertFalse(Servicio.vista_previa(self.actor, self.ev.pk)['lista'])

    def test_la_pm_mostrada_coincide_con_la_guardada(self):
        # 17/8 = 2,125: pantalla y base deben redondear igual (2.13, mitad hacia arriba).
        self.assertEqual(_redondear(Fraction(17, 8)), Decimal('2.13'))
        self.confirmar_todo()
        filas = Servicio.calcular_y_guardar(self.actor, self.ev.pk, {self.f_amb.pk: 'interno'})
        for fila in filas:
            self.assertEqual(fila['pm_texto'], str(self.ef(Factor.objects.get(pk=fila['factor_id'])).ponderacion_media))
