from datetime import date

from django.core.exceptions import ValidationError, PermissionDenied
from apps.application.services.lotes_hu09 import LotesHU09Service as Lotes
from apps.data.models import LoteHU09
from apps.external_services.ollama_preguntas import AnalisisNoDisponible
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.application.services.preguntas import PreguntasService
from apps.data.models import (CatalogoVersion, Dimension, Evaluacion, EvaluacionFactor, Factor,
                              Organizacion, PreguntaComplementaria, Software, Subfactor, Usuario,
                              ValoracionSubfactor)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], HU09_EMBEDDING_MODEL='', HU09_OLLAMA_MODEL='qwen3:4b-instruct')
class LotesHU09Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='INACTIVO')
        org = Organizacion.objects.create(nombre='Organización')
        cls.actor = Usuario.objects.create_user('propietario@hu09.test', 'Clave-test-123', nombre='Propietario', organizacion=org)
        cls.otro = Usuario.objects.create_user('otro@hu09.test', 'Clave-test-123', nombre='Otro', organizacion=org)
        cls.admin = Usuario.objects.create_superuser('admin@hu09.test', 'Clave-test-123', nombre='Admin')
        cat = CatalogoVersion.objects.create(version='prueba', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor, software=Software.objects.create(nombre='Software propio'), catalogo=cat)
        cls.ajena = Evaluacion.objects.create(organizacion=org, usuario=cls.otro, software=Software.objects.create(nombre='Software ajeno'), catalogo=cat)
        dim = Dimension.objects.create(nombre='Tecnológica')
        for nombre, ir in [('Seguridad', 3), ('Excluido', 1)]:
            f = Factor.objects.create(dimension=dim, nombre=nombre, alcance=Factor.EXTERNO)
            ef = EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=f, importancia_relativa=ir)
            sf = Subfactor.objects.create(factor=f, descripcion='Requisito ' + nombre)
            ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=sf)

    def setUp(self):
        self.url = reverse('presentation:decisor-revision-valoraciones')
        self.client.force_login(self.actor)

    def post(self, accion, **extra):
        return self.client.post(self.url, {'evaluacion': self.ev.pk, 'accion': accion, **extra})

    def lote(self):
        return Lotes.encolar(self.actor, self.ev.pk)

    def proveedor(self, entrada):
        return {'estado': 'INSUFICIENTE', 'justificacion': 'Faltan datos.', 'referencias': [], 'preguntas': ['¿Existe un procedimiento documentado?']}

    def test_encola_solo_relevantes_y_es_idempotente(self):
        lote = self.lote()
        self.assertEqual(len(lote.objetivos), 1)
        self.assertEqual(self.lote().pk, lote.pk)
        self.assertEqual(LoteHU09.objects.count(), 1)

    def test_subfactores_con_pendientes_no_encolan(self):
        PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)
        with self.assertRaises(ValidationError):
            self.lote()

    def test_tomar_y_procesar_genera_resultado_persistente(self):
        lote = self.lote()
        tomado = Lotes.tomar()
        self.assertEqual(tomado.pk, lote.pk)
        self.assertIsNone(Lotes.tomar())
        Lotes.procesar(tomado, self.proveedor, 'qwen3:4b-instruct')
        estado = Lotes.estado(self.actor, self.ev.pk)
        self.assertEqual(estado['estado'], 'FINALIZADO')
        self.assertEqual(estado['procesados'], 1)
        self.assertEqual(estado['preguntas_nuevas'], 1)
        self.assertEqual(PreguntaComplementaria.objects.count(), 1)

    def test_cambio_durante_espera_omite_subfactor(self):
        self.lote()
        PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)
        Lotes.procesar(Lotes.tomar(), self.proveedor, 'qwen3:4b-instruct')
        self.assertEqual(Lotes.estado(self.actor, self.ev.pk)['omitidos'], 1)

    def test_fallo_proveedor_persiste_error(self):
        self.lote()
        def fallo(entrada):
            raise AnalisisNoDisponible('No disponible')
        Lotes.procesar(Lotes.tomar(), fallo, 'qwen3:4b-instruct')
        self.assertEqual(Lotes.estado(self.actor, self.ev.pk)['errores'], 1)
        self.assertEqual(PreguntaComplementaria.objects.count(), 0)

    def test_no_encola_evaluacion_ajena_o_cerrada(self):
        with self.assertRaises(PermissionDenied):
            Lotes.encolar(self.actor, self.ajena.pk)
        Evaluacion.objects.filter(pk=self.ev.pk).update(estado='FINALIZADA')
        with self.assertRaises(ValidationError):
            self.lote()

    def test_estado_json_y_propiedad(self):
        self.assertEqual(self.post('lote').status_code, 302)
        res = self.client.get(self.url, {'evaluacion': self.ev.pk, 'estado_lote': 1})
        self.assertEqual(res.json()['lote']['estado'], 'EN_COLA')
        self.assertEqual(res['Cache-Control'], 'no-store')
        self.assertEqual(self.client.get(self.url, {'evaluacion': self.ajena.pk, 'estado_lote': 1}).status_code, 403)

    def test_lote_exige_csrf(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.actor)
        self.assertEqual(c.post(self.url, {'evaluacion': self.ev.pk, 'accion': 'lote'}).status_code, 403)

    def test_analisis_individual_bloqueado_con_lote_activo(self):
        lote = self.lote()
        res = self.post('suficiencia', valoracion=lote.objetivos[0])
        self.assertContains(res, 'Hay un análisis masivo activo', status_code=400)


    def test_salida_invalida_registra_error_y_permite_reintento(self):
        primero = self.lote()
        Lotes.procesar(Lotes.tomar(), lambda e: {'estado': 'INVENTADO'}, 'prueba')
        estado = Lotes.estado(self.actor, self.ev.pk)
        self.assertEqual(estado['errores'], 1)
        self.assertEqual(estado['omitidos'], 0)
        self.assertEqual(estado['estado'], 'FINALIZADO')
        self.assertFalse(PreguntaComplementaria.objects.exists())
        segundo = self.lote()
        self.assertNotEqual(primero.pk, segundo.pk)
        Lotes.procesar(Lotes.tomar(), self.proveedor, 'prueba')
        self.assertEqual(Lotes.estado(self.actor, self.ev.pk)['preguntas_nuevas'], 1)
