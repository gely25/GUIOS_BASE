from datetime import date
from fractions import Fraction

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings

from apps.application.services.preguntas import PreguntasService
from apps.application.services.revision_humana import RevisionHumanaService as Servicio
from apps.business_rules.pm import calcular_pm
from apps.data.models import (CatalogoVersion, Dimension, Documento, Evaluacion, EvaluacionFactor,
    Evidencia, Factor, FragmentoDocumento, LoteHU09, Organizacion, RevisionHumana, Software,
    Subfactor, Usuario, ValoracionSubfactor)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RevisionHumanaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='INACTIVO')
        org = Organizacion.objects.create(nombre='Org HU11')
        cls.actor = Usuario.objects.create_user('revision@test.local', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cls.otro = Usuario.objects.create_user('otro@test.local', 'Clave-test-123', nombre='Otro', organizacion=org)
        cls.admin = Usuario.objects.create_superuser('admin@test.local', 'Clave-test-123', nombre='Admin')
        software = Software.objects.create(nombre='Software prueba HU11')
        catalogo = CatalogoVersion.objects.create(version='HU11 test', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor, software=software, catalogo=catalogo)
        cls.ajena = Evaluacion.objects.create(organizacion=org, usuario=cls.otro, software=software, catalogo=catalogo)
        dim = Dimension.objects.create(nombre='Tecnológica')
        factor = Factor.objects.create(dimension=dim, nombre='Compatibilidad', alcance=Factor.EXTERNO)
        cls.ef = EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=factor, importancia_relativa=3)
        cls.sf = Subfactor.objects.create(factor=factor, descripcion='Formatos admitidos')
        sf2 = Subfactor.objects.create(factor=factor, descripcion='Compatibilidad de versiones')
        cls.v = ValoracionSubfactor.objects.create(evaluacion_factor=cls.ef, subfactor=cls.sf,
            valor_ia=4, justificacion_ia='Admite ODF según la propuesta.')
        cls.v2 = ValoracionSubfactor.objects.create(evaluacion_factor=cls.ef, subfactor=sf2)
        doc = Documento.objects.create(evaluacion=cls.ev, usuario=cls.actor, nombre='Evidencia', tipo='PDF', ubicacion='test.pdf')
        frag = FragmentoDocumento.objects.create(documento=doc, pagina=2, contenido='Admite ODF 1.2.')
        cls.e = Evidencia.objects.create(valoracion=cls.v, fragmento=frag)
        ajeno = Documento.objects.create(evaluacion=cls.ajena, usuario=cls.otro, nombre='Ajeno', tipo='PDF', ubicacion='ajeno.pdf')
        Evidencia.objects.create(valoracion=cls.v, fragmento=FragmentoDocumento.objects.create(documento=ajeno, contenido='Privado'))

    def resolver(self, v=None, modo='CONFIRMAR', valor=4, justificacion='Revisado por el decisor.', version=None):
        v = v or self.v
        if version is None:
            version = Servicio.obtener(self.actor, self.ev.pk, v.pk)['version']
        return Servicio.resolver(self.actor, self.ev.pk, v.pk, modo, valor, justificacion, version)

    def test_confirmar_conserva_propuesta_y_auditoria(self):
        r = self.resolver()
        self.v.refresh_from_db()
        self.assertEqual((self.v.valor_ia, self.v.valor_confirmado, self.v.estado_validacion), (4, 4, 'CONFIRMADA'))
        self.assertEqual(self.v.validado_por_id, self.actor.pk)
        self.assertEqual(r.fecha, self.v.fecha_validacion)
        self.assertEqual(r.valor_ia, 4)
        self.assertEqual(r.fuentes[0]['id'], f'E:{self.e.pk}')
        self.assertNotIn('Privado', str(r.fuentes))

    def test_modificar_conserva_original_y_justificacion(self):
        r = self.resolver(modo='MODIFICAR', valor=3, justificacion='  Cobertura parcial.  ')
        self.v.refresh_from_db()
        self.assertEqual((self.v.valor_ia, self.v.valor_confirmado, self.v.estado_validacion), (4, 3, 'MODIFICADA'))
        self.assertEqual(self.v.justificacion_ia, r.justificacion_ia)
        self.assertEqual(self.v.justificacion_decisor, 'Cobertura parcial.')

    def test_manual_sin_ia_no_inventa_propuesta(self):
        r = self.resolver(self.v2, modo='MANUAL', valor=2)
        self.v2.refresh_from_db()
        self.assertIsNone(self.v2.valor_ia)
        self.assertIsNone(r.valor_ia)
        self.assertEqual(self.v2.valor_confirmado, 2)
        self.assertEqual(r.modo, 'MANUAL')

    def test_rechaza_accion_incompatible(self):
        for modo, valor in [('CONFIRMAR', 3), ('MODIFICAR', 4), ('MANUAL', 2), ('INVALIDO', 4)]:
            with self.subTest(modo=modo), self.assertRaises(ValidationError):
                self.resolver(modo=modo, valor=valor)
        self.assertFalse(RevisionHumana.objects.exists())

    def test_rechaza_escala_y_justificacion_invalidas(self):
        for valor in [True, 0, 5, '4', 4.0]:
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                self.resolver(valor=valor)
        with self.assertRaises(ValidationError):
            self.resolver(justificacion='   ')
        self.assertFalse(RevisionHumana.objects.exists())

    def test_propiedad_y_rol(self):
        for actor in [self.otro, self.admin]:
            with self.assertRaises(PermissionDenied):
                Servicio.obtener(actor, self.ev.pk, self.v.pk)
            with self.assertRaises(PermissionDenied):
                Servicio.resolver(actor, self.ev.pk, self.v.pk, 'CONFIRMAR', 4, 'Revisión', '')

    def test_rechaza_evaluacion_cerrada(self):
        version = Servicio.obtener(self.actor, self.ev.pk, self.v.pk)['version']
        Evaluacion.objects.filter(pk=self.ev.pk).update(estado='FINALIZADA')
        self.assertFalse(Servicio.obtener(self.actor, self.ev.pk, self.v.pk)['editable'])
        with self.assertRaises(ValidationError):
            self.resolver(version=version)

    def test_rechaza_factor_excluido(self):
        EvaluacionFactor.objects.filter(pk=self.ef.pk).update(importancia_relativa=1)
        with self.assertRaises(PermissionDenied):
            Servicio.obtener(self.actor, self.ev.pk, self.v.pk)

    def test_bloquea_propuesta_o_contexto_obsoleto(self):
        version = Servicio.obtener(self.actor, self.ev.pk, self.v.pk)['version']
        ValoracionSubfactor.objects.filter(pk=self.v.pk).update(valor_ia=3)
        with self.assertRaises(ValidationError):
            self.resolver(version=version)
        version = Servicio.obtener(self.actor, self.ev.pk, self.v.pk)['version']
        FragmentoDocumento.objects.filter(pk=self.e.fragmento_id).update(contenido='Admite ODF 1.3.')
        with self.assertRaises(ValidationError):
            self.resolver(modo='MODIFICAR', valor=4, version=version)
        self.assertFalse(RevisionHumana.objects.exists())

    def test_no_reescribe_confirmacion(self):
        version = Servicio.obtener(self.actor, self.ev.pk, self.v.pk)['version']
        self.resolver(version=version)
        with self.assertRaises((PermissionDenied, ValidationError)):
            self.resolver(version=version)
        self.assertEqual(RevisionHumana.objects.count(), 1)

    def test_lote_activo_bloquea_decisiones_y_calculo(self):
        version = Servicio.obtener(self.actor, self.ev.pk, self.v.pk)['version']
        LoteHU09.objects.create(evaluacion=self.ev, solicitante=self.actor)
        with self.assertRaises(ValidationError):
            self.resolver(version=version)
        with self.assertRaises(ValidationError):
            Servicio.para_calculo(self.actor, self.ev.pk)

    def test_calculo_espera_todas_y_entrega_valores_humanos(self):
        self.resolver(modo='MODIFICAR', valor=3)
        with self.assertRaises(ValidationError):
            Servicio.para_calculo(self.actor, self.ev.pk)
        self.resolver(self.v2, 'MANUAL', 2, 'No dispongo de información.')
        datos = Servicio.para_calculo(self.actor, self.ev.pk)['factores'][0]['valoraciones']
        self.assertEqual(calcular_pm([d['valor'] for d in datos]), Fraction(5, 2))
        self.assertEqual(datos[1]['justificacion'], 'No dispongo de información.')

    def test_calculo_no_ignora_subfactor_faltante(self):
        self.resolver()
        self.resolver(self.v2, 'MANUAL', 2)
        Subfactor.objects.create(factor=self.ef.factor, descripcion='Subfactor no inicializado')
        with self.assertRaises(ValidationError):
            Servicio.para_calculo(self.actor, self.ev.pk)

    def test_respuestas_se_distinguen_de_documentos_y_no_se_modifican(self):
        p = PreguntasService.registrar_vacios(self.actor, self.ev.pk, self.v.pk, ['¿Formatos?'])[0]
        PreguntasService.responder(self.actor, self.ev.pk, p.pk, 'Admite ODF 1.2.')
        r = self.resolver()
        p.refresh_from_db()
        self.assertEqual(p.respuesta, 'Admite ODF 1.2.')
        self.assertEqual({f['origen'] for f in r.fuentes}, {'DOCUMENTO', 'DECLARACION_DECISOR'})

    def reabrir(self, v=None, motivo='Nueva revisión de evidencia.', version=None):
        v = v or self.v
        if version is None:
            version = Servicio.obtener(self.actor, self.ev.pk, v.pk)['version']
        return Servicio.reabrir(self.actor, self.ev.pk, v.pk, motivo, version)

    def test_reapertura_conserva_decision_y_archiva_resultados(self):
        from apps.data.models import ResultadoEvaluacion, ReaperturaRevisionHumana
        anterior = self.resolver()
        self.resolver(self.v2, 'MANUAL', 2)
        EvaluacionFactor.objects.filter(pk=self.ef.pk).update(ponderacion_media=3, clasificacion_foda='Oportunidad')
        ResultadoEvaluacion.objects.create(evaluacion=self.ev, recomendacion='Anterior', explicacion='Prueba', version_regla='1')
        evento = self.reabrir()
        self.v.refresh_from_db()
        self.v2.refresh_from_db()
        self.ef.refresh_from_db()
        self.assertEqual((self.v.valor_ia, self.v.valor_confirmado, self.v.estado_validacion), (4, None, 'PENDIENTE'))
        self.assertIsNone(self.v.fecha_validacion)
        self.assertIsNone(self.v.validado_por_id)
        self.assertIsNone(self.v.justificacion_decisor)
        self.assertEqual(self.v2.valor_confirmado, 2)
        self.assertEqual(evento.decision_anterior['revision_id'], anterior.pk)
        self.assertEqual(evento.resultados_anteriores['resultado']['recomendacion'], 'Anterior')
        self.assertIsNone(self.ef.ponderacion_media)
        self.assertIsNone(self.ef.clasificacion_foda)
        self.assertFalse(ResultadoEvaluacion.objects.filter(evaluacion=self.ev).exists())
        self.assertEqual(RevisionHumana.objects.count(), 2)
        self.assertEqual(ReaperturaRevisionHumana.objects.count(), 1)
        with self.assertRaises(ValidationError):
            Servicio.para_calculo(self.actor, self.ev.pk)

    def test_reapertura_invalida_version_previa_y_permite_nueva_decision(self):
        version_pendiente = Servicio.obtener(self.actor, self.ev.pk, self.v.pk)['version']
        self.resolver()
        self.reabrir()
        with self.assertRaises(ValidationError):
            self.resolver(version=version_pendiente)
        nuevo = self.resolver(modo='MODIFICAR', valor=3)
        self.assertEqual(nuevo.valor, 3)
        self.assertEqual(RevisionHumana.objects.count(), 2)
        self.v.refresh_from_db()
        self.assertEqual(self.v.valor_confirmado, 3)

    def test_reapertura_rechaza_motivo_vacio_y_version_obsoleta(self):
        from apps.data.models import ReaperturaRevisionHumana
        self.resolver()
        for motivo, version in [(' ', None), ('Motivo', 'obsoleta')]:
            with self.assertRaises(ValidationError):
                self.reabrir(motivo=motivo, version=version)
        self.assertFalse(ReaperturaRevisionHumana.objects.exists())
        self.v.refresh_from_db()
        self.assertEqual(self.v.valor_confirmado, 4)

    def test_reapertura_exige_propietario_y_evaluacion_abierta(self):
        self.resolver()
        version = Servicio.obtener(self.actor, self.ev.pk, self.v.pk)['version']
        for actor in (self.otro, self.admin):
            with self.assertRaises(PermissionDenied):
                Servicio.reabrir(actor, self.ev.pk, self.v.pk, 'Motivo', version)
        LoteHU09.objects.create(evaluacion=self.ev, solicitante=self.actor)
        with self.assertRaises(ValidationError):
            self.reabrir(version=version)
        LoteHU09.objects.all().delete()
        Evaluacion.objects.filter(pk=self.ev.pk).update(estado='FINALIZADA')
        with self.assertRaises(ValidationError):
            self.reabrir(version=version)
        self.assertFalse(Servicio.obtener(self.actor, self.ev.pk, self.v.pk)['reabrible'])

    def test_vista_previa_pm_foda_no_persiste_y_usa_valores_humanos(self):
        self.assertFalse(Servicio.vista_previa(self.actor, self.ev.pk)['lista_pm'])
        self.resolver(modo='MODIFICAR', valor=3)
        self.resolver(self.v2, 'MANUAL', 2)
        previa = Servicio.vista_previa(self.actor, self.ev.pk)
        self.assertTrue(previa['lista_pm'])
        self.assertTrue(previa['lista_foda'])
        self.assertEqual(previa['factores'][0]['pm_exacta'], '5/2')
        self.assertEqual(previa['factores'][0]['foda'], 'Amenaza')
        self.ef.refresh_from_db()
        self.assertIsNone(self.ef.ponderacion_media)
        self.assertIsNone(self.ef.clasificacion_foda)
        Factor.objects.filter(pk=self.ef.factor_id).update(alcance=Factor.AMBOS)
        previa = Servicio.vista_previa(self.actor, self.ev.pk)
        self.assertTrue(previa['lista_pm'])
        self.assertFalse(previa['lista_foda'])
        self.assertIsNone(previa['factores'][0]['foda'])

    def test_calculo_rechaza_fuentes_modificadas_despues_de_confirmar(self):
        self.resolver()
        self.resolver(self.v2, 'MANUAL', 2)
        FragmentoDocumento.objects.filter(pk=self.e.fragmento_id).update(contenido='Nueva evidencia.')
        with self.assertRaises(ValidationError):
            Servicio.para_calculo(self.actor, self.ev.pk)
        self.assertFalse(Servicio.vista_previa(self.actor, self.ev.pk)['lista_pm'])

    def test_calculo_rechaza_valor_sin_auditoria(self):
        from django.utils import timezone
        self.resolver(self.v2, 'MANUAL', 2)
        ValoracionSubfactor.objects.filter(pk=self.v.pk).update(valor_confirmado=4,
            estado_validacion='CONFIRMADA', justificacion_decisor='Sin registro',
            fecha_validacion=timezone.now(), validado_por=self.actor)
        with self.assertRaises(ValidationError):
            Servicio.para_calculo(self.actor, self.ev.pk)

    def test_huella_calculo_cambia_incluso_si_se_reconfirma_mismo_valor(self):
        self.resolver()
        self.resolver(self.v2, 'MANUAL', 2)
        anterior = Servicio.para_calculo(self.actor, self.ev.pk)['huella']
        self.assertEqual(Servicio.validar_calculo(self.actor, self.ev.pk, anterior)['huella'], anterior)
        self.reabrir()
        self.resolver()
        self.assertNotEqual(Servicio.para_calculo(self.actor, self.ev.pk)['huella'], anterior)
        with self.assertRaises(ValidationError):
            Servicio.validar_calculo(self.actor, self.ev.pk, anterior)

    def test_calculo_pendiente_no_carga_fuentes_ni_auditorias(self):
        from unittest.mock import patch
        with patch.object(PreguntasService, 'contexto', side_effect=AssertionError('Consulta innecesaria')):
            with self.assertRaises(ValidationError):
                Servicio.para_calculo(self.actor, self.ev.pk)

    def test_calculo_rechaza_modo_historico_incompatible(self):
        registro = self.resolver()
        self.resolver(self.v2, 'MANUAL', 2)
        RevisionHumana.objects.filter(pk=registro.pk).update(modo='MANUAL')
        with self.assertRaises(ValidationError):
            Servicio.para_calculo(self.actor, self.ev.pk)

    def test_calculo_61_subfactores_consultas_acotadas(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self.resolver()
        self.resolver(self.v2, 'MANUAL', 2)
        for i in range(59):
            sf = Subfactor.objects.create(factor=self.ef.factor, descripcion=f'Requisito adicional {i}')
            v = ValoracionSubfactor.objects.create(evaluacion_factor=self.ef, subfactor=sf)
            self.resolver(v, 'MANUAL', 2)
        with CaptureQueriesContext(connection) as consultas:
            datos = Servicio.para_calculo(self.actor, self.ev.pk)
        self.assertEqual(len(datos['factores'][0]['valoraciones']), 61)
        self.assertLessEqual(len(consultas), 18)
