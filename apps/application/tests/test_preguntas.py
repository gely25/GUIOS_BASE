from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings

from apps.application.services.preguntas import PreguntasService as Servicio
from apps.data.models import (CatalogoVersion, Dimension, Documento, Evaluacion, EvaluacionFactor,
                              Evidencia, Factor, FragmentoDocumento, Organizacion, PreguntaComplementaria,
                              Software, Subfactor, Usuario, ValoracionSubfactor)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PreguntasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='INACTIVO')
        org = Organizacion.objects.create(nombre='Organización prueba')
        cls.actor = Usuario.objects.create_user('decisor@test.local', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cls.otro = Usuario.objects.create_user('otro@test.local', 'Clave-test-123', nombre='Otro', organizacion=org)
        cls.admin = Usuario.objects.create_superuser('admin@test.local', 'Clave-test-123', nombre='Admin')
        software = Software.objects.create(nombre='Software prueba')
        catalogo = CatalogoVersion.objects.create(version='prueba', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor, software=software, catalogo=catalogo)
        cls.ev2 = Evaluacion.objects.create(organizacion=org, usuario=cls.otro, software=software, catalogo=catalogo)
        dim = Dimension.objects.create(nombre='Tecnológica')
        for nombre, ir, relevante in [('Compatibilidad', 3, True), ('Excluido', 1, True), ('No seleccionado', 3, False), ('Sin IR', None, True)]:
            f = Factor.objects.create(dimension=dim, nombre=nombre, alcance=Factor.EXTERNO)
            ef = EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=f, importancia_relativa=ir, relevante=relevante)
            sf = Subfactor.objects.create(factor=f, descripcion=f'Información de {nombre}')
            v = ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=sf)
            if nombre == 'Compatibilidad':
                cls.v = v
        cls.doc = Documento.objects.create(evaluacion=cls.ev, usuario=cls.actor, nombre='Documento', tipo='PDF', ubicacion='prueba.pdf')
        cls.doc2 = Documento.objects.create(evaluacion=cls.ev2, usuario=cls.otro, nombre='Ajeno', tipo='PDF', ubicacion='ajeno.pdf')

    def evidencia(self, texto, documento=None):
        frag = FragmentoDocumento.objects.create(documento=documento or self.doc, contenido=texto, pagina=2)
        return Evidencia.objects.create(valoracion=self.v, fragmento=frag)

    def generar(self):
        return Servicio.detectar_sin_evidencia(self.actor, self.ev.pk)

    def test_solo_subfactores_relevantes_con_ir_definida(self):
        preguntas = self.generar()
        self.assertEqual(len(preguntas), 1)
        self.assertEqual(preguntas[0].valoracion_id, self.v.pk)
        self.assertIn('Compatibilidad', preguntas[0].texto)

    def test_no_duplica_preguntas(self):
        self.generar()
        self.assertEqual(self.generar(), [])
        self.assertEqual(PreguntaComplementaria.objects.count(), 1)

    def test_fragmento_no_equivale_a_suficiencia(self):
        self.evidencia('Hay información parcial.')
        self.assertEqual(self.generar(), [])
        ctx = Servicio.contexto(self.actor, self.ev.pk)[0]
        self.assertEqual(ctx['estado_informacion'], 'REVISION_PENDIENTE')
        self.assertEqual(ctx['evidencias'][0]['pagina'], 2)

    def test_fragmento_vacio_o_ajeno_no_cubre_el_subfactor(self):
        self.evidencia('   ')
        self.evidencia('Información privada ajena', self.doc2)
        self.assertEqual(len(self.generar()), 1)
        self.assertEqual(Servicio.contexto(self.actor, self.ev.pk)[0]['evidencias'], [])

    def test_registra_vacios_especificos_sin_duplicar(self):
        preguntas = Servicio.registrar_vacios(self.actor, self.ev.pk, self.v.pk, ['¿Qué formatos admite?', ' ¿QUÉ formatos admite? '])
        self.assertEqual(len(preguntas), 1)
        self.assertEqual(preguntas[0].origen, 'ANALISIS')

    def test_respuesta_persistente_y_trazable(self):
        pregunta = self.generar()[0]
        Servicio.responder(self.actor, self.ev.pk, pregunta.pk, '  Admite ODF.  ')
        pregunta.refresh_from_db()
        self.assertEqual(pregunta.respuesta, 'Admite ODF.')
        self.assertEqual(pregunta.respondido_por_id, self.actor.pk)
        self.assertIsNotNone(pregunta.fecha_respuesta)
        ctx = Servicio.contexto(self.actor, self.ev.pk)[0]
        self.assertEqual(ctx['preguntas'][0]['respuesta'], 'Admite ODF.')
        self.assertEqual(ctx['estado_informacion'], 'REVISION_PENDIENTE')
        self.assertEqual(self.generar(), [])

    def test_rechaza_respuesta_vacia(self):
        pregunta = self.generar()[0]
        with self.assertRaises(ValidationError):
            Servicio.responder(self.actor, self.ev.pk, pregunta.pk, '   ')

    def test_rechaza_preguntas_invalidas_sin_guardar_parcialmente(self):
        with self.assertRaises(ValidationError):
            Servicio.registrar_vacios(self.actor, self.ev.pk, self.v.pk, ['¿Válida?', ' '])
        self.assertFalse(PreguntaComplementaria.objects.exists())

    def test_no_permite_acceso_ajeno_o_administrador(self):
        p = self.generar()[0]
        for actor in (self.otro, self.admin):
            with self.assertRaises(PermissionDenied):
                Servicio.contexto(actor, self.ev.pk)
            with self.assertRaises(PermissionDenied):
                Servicio.responder(actor, self.ev.pk, p.pk, 'No autorizado')

    def test_no_permite_editar_evaluacion_cerrada(self):
        p = self.generar()[0]
        self.ev.estado = 'FINALIZADA'
        self.ev.save(update_fields=['estado'])
        with self.assertRaises(ValidationError):
            Servicio.responder(self.actor, self.ev.pk, p.pk, 'Respuesta')

    def test_no_altera_valoraciones_ni_puntuaciones(self):
        p = self.generar()[0]
        Servicio.responder(self.actor, self.ev.pk, p.pk, 'Respuesta')
        self.v.refresh_from_db()
        self.assertIsNone(self.v.valor_ia)
        self.assertIsNone(self.v.valor_confirmado)
        self.assertEqual(self.v.estado_validacion, ValoracionSubfactor.PENDIENTE)

    def test_no_modifica_valoracion_confirmada(self):
        p = self.generar()[0]
        self.v.valor_confirmado = 3
        self.v.save(update_fields=['valor_confirmado'])
        with self.assertRaises(PermissionDenied):
            Servicio.responder(self.actor, self.ev.pk, p.pk, 'Respuesta')

    def test_desconocimiento_no_es_evidencia(self):
        p = self.generar()[0]
        for respuesta in ('No lo sé', 'no lose', 'no lo se x2', 'Desconozco'):
            Servicio.responder(self.actor, self.ev.pk, p.pk, respuesta)
            fila = Servicio.contexto(self.actor, self.ev.pk)[0]
            self.assertEqual(fila['estado_informacion'], 'DESCONOCE')
            self.assertEqual(fila['preguntas'][0]['estado_respuesta'], 'DESCONOCE')
        self.assertEqual(self.generar(), [])

    def test_negacion_tecnica_si_aporta_informacion(self):
        p = self.generar()[0]
        Servicio.responder(self.actor, self.ev.pk, p.pk, 'No admite ODF.')
        self.assertEqual(Servicio.contexto(self.actor, self.ev.pk)[0]['estado_informacion'], 'REVISION_PENDIENTE')

    def test_analizador_recibe_evidencia_y_registra_vacios(self):
        from apps.application.services.analisis_preguntas import AnalisisPreguntasService
        self.evidencia('Admite ODF.')
        entradas = []
        def analizador(entrada):
            entradas.append(entrada)
            return ['¿Qué versiones de ODF admite?']
        nuevas = AnalisisPreguntasService.analizar(self.actor, self.ev.pk, analizador)
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]['evidencias'][0]['contenido'], 'Admite ODF.')
        self.assertEqual(len(nuevas), 1)
        self.assertEqual(nuevas[0].origen, 'ANALISIS')
        self.assertEqual(AnalisisPreguntasService.analizar(self.actor, self.ev.pk, analizador), [])
        self.v.refresh_from_db()
        self.assertIsNone(self.v.valor_ia)

    def test_analizador_invalido_no_registra(self):
        from apps.application.services.analisis_preguntas import AnalisisPreguntasService
        with self.assertRaises(ValidationError):
            AnalisisPreguntasService.analizar(self.actor, self.ev.pk, lambda entrada: ['¿Válida?', ' '])
        self.assertFalse(PreguntaComplementaria.objects.exists())

    def test_analizador_descarta_resultado_obsoleto(self):
        from apps.application.services.analisis_preguntas import AnalisisPreguntasService
        p = self.generar()[0]
        def analizador(entrada):
            Servicio.responder(self.actor, self.ev.pk, p.pk, 'Admite ODF.')
            return ['¿Qué versiones admite?']
        with self.assertRaises(ValidationError):
            AnalisisPreguntasService.analizar(self.actor, self.ev.pk, analizador)
        self.assertEqual(PreguntaComplementaria.objects.count(), 1)

    def test_ia_respeta_cupo_acumulado(self):
        from apps.application.services.analisis_preguntas import AnalisisPreguntasService
        from unittest.mock import Mock
        self.generar()
        analizador = Mock(return_value=['¿Qué formatos admite?', '¿Qué versiones utiliza?', '¿Qué limitaciones tiene?'])
        nuevas = AnalisisPreguntasService.analizar(self.actor, self.ev.pk, analizador)
        self.assertEqual(analizador.call_args.args[0]['max_preguntas'], 2)
        self.assertEqual(len(nuevas), 2)
        analizador.reset_mock()
        self.assertEqual(AnalisisPreguntasService.analizar(self.actor, self.ev.pk, analizador), [])
        analizador.assert_not_called()
        self.assertEqual(PreguntaComplementaria.objects.count(), 3)

    def test_ia_filtra_variantes_textuales(self):
        from apps.application.services.analisis_preguntas import AnalisisPreguntasService
        Servicio.registrar_vacios(self.actor, self.ev.pk, self.v.pk, ['¿Qué versiones de ODF admite?'])
        nuevas = AnalisisPreguntasService.analizar(self.actor, self.ev.pk, lambda entrada: [
            'QUE VERSIONES DE ODF ADMITE?', '¿Qué otros formatos admite?', '¿Qué OTROS formatos admite?'])
        self.assertEqual([p.texto for p in nuevas], ['¿Qué otros formatos admite?'])

    def test_descarte_conserva_historial_y_no_regenera(self):
        from apps.application.services.analisis_preguntas import AnalisisPreguntasService
        p = self.generar()[0]
        Servicio.descartar(self.actor, self.ev.pk, p.pk)
        p.refresh_from_db()
        self.assertEqual(p.descartada_por_id, self.actor.pk)
        self.assertIsNotNone(p.fecha_descarte)
        ctx = Servicio.contexto(self.actor, self.ev.pk)[0]
        self.assertEqual(ctx['preguntas'], [])
        self.assertEqual(ctx['preguntas_descartadas'][0]['pregunta_id'], p.pk)
        self.assertEqual(self.generar(), [])
        def proveedor(entrada):
            self.assertEqual(entrada['preguntas_descartadas'], [p.texto])
            return [p.texto]
        self.assertEqual(AnalisisPreguntasService.analizar(self.actor, self.ev.pk, proveedor), [])
        self.assertEqual(PreguntaComplementaria.objects.count(), 1)

    def test_exige_confirmacion_para_descartar_y_no_responde_descartadas(self):
        p = self.generar()[0]
        Servicio.responder(self.actor, self.ev.pk, p.pk, 'Admite ODF.')
        with self.assertRaises(ValidationError):
            Servicio.descartar(self.actor, self.ev.pk, p.pk)
        otra = Servicio.registrar_vacios(self.actor, self.ev.pk, self.v.pk, ['¿Qué versiones?'])[0]
        Servicio.descartar(self.actor, self.ev.pk, otra.pk)
        with self.assertRaises(ValidationError):
            Servicio.responder(self.actor, self.ev.pk, otra.pk, '1.3')

    def test_descarte_ajeno_y_evaluacion_cerrada(self):
        p = self.generar()[0]
        with self.assertRaises(PermissionDenied):
            Servicio.descartar(self.otro, self.ev.pk, p.pk)
        Evaluacion.objects.filter(pk=self.ev.pk).update(estado='FINALIZADA')
        with self.assertRaises(ValidationError):
            Servicio.descartar(self.actor, self.ev.pk, p.pk)
        p.refresh_from_db()
        self.assertIsNone(p.fecha_descarte)

    def test_embeddings_filtran_parafrasis_y_descartadas(self):
        from apps.application.services.analisis_preguntas import AnalisisPreguntasService
        anterior = Servicio.registrar_vacios(self.actor, self.ev.pk, self.v.pk, ['¿Qué versiones de ODF admite?'])[0]
        Servicio.descartar(self.actor, self.ev.pk, anterior.pk)
        def vectorizador(textos):
            self.assertEqual(textos[0], anterior.texto)
            return [[1, 0], [.99, .01], [0, 1], [.01, .99]]
        nuevas = AnalisisPreguntasService.analizar(self.actor, self.ev.pk, lambda entrada: [
            '¿Cuáles son las ediciones compatibles de ODF?', '¿Qué formatos distintos soporta?',
            '¿Qué otros tipos de archivo admite?'], vectorizador=vectorizador)
        self.assertEqual([p.texto for p in nuevas], ['¿Qué formatos distintos soporta?'])

    def test_embeddings_preservan_diferencias_numericas(self):
        from apps.application.services.analisis_preguntas import AnalisisPreguntasService
        Servicio.registrar_vacios(self.actor, self.ev.pk, self.v.pk, ['¿Admite ODF 1.2?'])
        nuevas = AnalisisPreguntasService.analizar(self.actor, self.ev.pk, lambda entrada: ['¿Admite ODF 1.3?'],
                                                  vectorizador=lambda textos: [[1, 0], [1, 0]])
        self.assertEqual(len(nuevas), 1)

    def test_embeddings_invalidos_no_guardan_propuestas(self):
        from apps.application.services.analisis_preguntas import AnalisisPreguntasService
        with self.assertRaises(ValidationError):
            AnalisisPreguntasService.analizar(self.actor, self.ev.pk, lambda entrada: ['¿Qué versiones?'],
                                             vectorizador=lambda textos: [[0, 0]])
        self.assertFalse(PreguntaComplementaria.objects.exists())

    def test_restauracion_conserva_auditoria_y_es_idempotente(self):
        from django.contrib.admin.models import LogEntry
        import json
        p = self.generar()[0]
        Servicio.descartar(self.actor, self.ev.pk, p.pk)
        p.refresh_from_db()
        anterior = p.fecha_descarte.isoformat()
        Servicio.restaurar(self.actor, self.ev.pk, p.pk)
        Servicio.restaurar(self.actor, self.ev.pk, p.pk)
        p.refresh_from_db()
        self.assertIsNone(p.fecha_descarte)
        self.assertIsNone(p.descartada_por_id)
        log = LogEntry.objects.get(object_id=str(p.pk), user_id=self.actor.pk)
        self.assertEqual(json.loads(log.change_message)['fecha_descarte'], anterior)
        self.assertEqual(len(Servicio.contexto(self.actor, self.ev.pk)[0]['preguntas']), 1)

    def test_restauracion_respeta_cupo_y_propietario(self):
        p = self.generar()[0]
        Servicio.descartar(self.actor, self.ev.pk, p.pk)
        with self.assertRaises(PermissionDenied):
            Servicio.restaurar(self.otro, self.ev.pk, p.pk)
        Servicio.registrar_vacios(self.actor, self.ev.pk, self.v.pk, ['¿Una?', '¿Dos?', '¿Tres?'])
        with self.assertRaises(ValidationError):
            Servicio.restaurar(self.actor, self.ev.pk, p.pk)
        p.refresh_from_db()
        self.assertIsNotNone(p.fecha_descarte)

    def test_restauracion_rechaza_evaluacion_cerrada(self):
        p = self.generar()[0]
        Servicio.descartar(self.actor, self.ev.pk, p.pk)
        Evaluacion.objects.filter(pk=self.ev.pk).update(estado='FINALIZADA')
        with self.assertRaises(ValidationError):
            Servicio.restaurar(self.actor, self.ev.pk, p.pk)

    def test_suficiencia_requiere_fuentes_informativas(self):
        from apps.application.services.suficiencia import SuficienciaService
        p = self.generar()[0]
        Servicio.responder(self.actor, self.ev.pk, p.pk, 'No lo sé')
        with self.assertRaises(ValidationError):
            SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, lambda e: {
                'estado': 'SUFICIENTE', 'justificacion': 'Hay respuesta', 'referencias': [f'R:{p.pk}'], 'preguntas': []}, 'prueba')

    def test_suficiencia_con_fuente_y_reutilizacion(self):
        from apps.application.services.suficiencia import SuficienciaService
        evidencia = self.evidencia('Admite ODF 1.3')
        def proveedor(e):
            self.assertEqual(e['fuentes'][0]['id'], f'E:{evidencia.pk}')
            return {'estado': 'SUFICIENTE', 'justificacion': 'Versión indicada', 'referencias': [f'E:{evidencia.pk}'], 'preguntas': []}
        r, cantidad = SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, proveedor, 'prueba')
        self.assertEqual((r.estado, cantidad, r.rondas), ('SUFICIENCIA_PROPUESTA', 0, 1))
        r2, _ = SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, lambda e: self.fail('No debe invocarse'), 'prueba')
        self.assertEqual(r.pk, r2.pk)
        self.v.refresh_from_db()
        self.assertIsNone(self.v.valor_ia)
        self.assertIsNone(self.v.valor_confirmado)

    def test_suficiencia_lista_vacia_no_equivale_a_suficiente(self):
        from apps.application.services.suficiencia import SuficienciaService
        r, n = SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, lambda e: {
            'estado': 'INSUFICIENTE', 'justificacion': 'No hay información', 'referencias': [], 'preguntas': []}, 'prueba')
        self.assertEqual((r.estado, n), ('REVISION_MANUAL', 0))

    def test_suficiencia_adaptativa_y_cambio_de_contexto(self):
        from apps.application.services.suficiencia import SuficienciaService
        r, n = SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, lambda e: {
            'estado': 'INSUFICIENTE', 'justificacion': 'Faltan versiones', 'referencias': [], 'preguntas': ['¿Qué versiones admite?']}, 'prueba')
        self.assertEqual((r.estado, n), ('FALTAN_DATOS', 1))
        self.assertTrue(SuficienciaService.adjuntar(Servicio.contexto(self.actor, self.ev.pk))[0]['suficiencia_vigente'])
        p = PreguntaComplementaria.objects.get(valoracion=self.v)
        Servicio.responder(self.actor, self.ev.pk, p.pk, 'Admite ODF 1.3')
        self.assertFalse(SuficienciaService.adjuntar(Servicio.contexto(self.actor, self.ev.pk))[0]['suficiencia_vigente'])
        r, n = SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, lambda e: {
            'estado': 'SUFICIENTE', 'justificacion': 'Versión especificada', 'referencias': [f'R:{p.pk}'], 'preguntas': []}, 'prueba')
        self.assertEqual((r.estado, r.rondas, n), ('SUFICIENCIA_PROPUESTA', 2, 0))

    def test_suficiencia_limita_tres_rondas(self):
        from apps.application.services.suficiencia import SuficienciaService
        for i in range(3):
            r, n = SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, lambda e: {
                'estado': 'INSUFICIENTE', 'justificacion': 'Falta dato', 'referencias': [], 'preguntas': [f'¿Dato {i}?']}, 'prueba')
            self.assertEqual(n, 1)
            p = PreguntaComplementaria.objects.get(valoracion=self.v, texto=f'¿Dato {i}?')
            Servicio.responder(self.actor, self.ev.pk, p.pk, 'No lo sé')
        r, n = SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, lambda e: self.fail('Límite alcanzado'), 'prueba')
        self.assertEqual((r.estado, r.rondas, n), ('REVISION_MANUAL', 3, 0))

    def test_suficiencia_no_analiza_con_pendientes_o_actor_ajeno(self):
        from apps.application.services.suficiencia import SuficienciaService
        self.generar()
        for actor, error in [(self.actor, ValidationError), (self.otro, PermissionDenied)]:
            with self.assertRaises(error):
                SuficienciaService.analizar(actor, self.ev.pk, self.v.pk, lambda e: self.fail('No debe invocarse'), 'prueba')

    def test_suficiencia_descarta_resultado_obsoleto(self):
        from apps.application.services.suficiencia import SuficienciaService
        from apps.data.models import AnalisisSuficiencia
        def proveedor(e):
            self.evidencia('Nuevo dato')
            return {'estado': 'INSUFICIENTE', 'justificacion': 'Faltan datos', 'referencias': [], 'preguntas': ['¿Dato?']}
        with self.assertRaises(ValidationError):
            SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, proveedor, 'prueba')
        self.assertFalse(AnalisisSuficiencia.objects.exists())
        self.assertFalse(PreguntaComplementaria.objects.exists())

    def test_analisis_legacy_no_elude_revision_adaptativa(self):
        from apps.application.services.suficiencia import SuficienciaService
        from apps.application.services.analisis_preguntas import AnalisisPreguntasService
        SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, lambda e: {
            'estado': 'INSUFICIENTE', 'justificacion': 'Sin datos', 'referencias': [], 'preguntas': []}, 'prueba')
        with self.assertRaises(ValidationError):
            AnalisisPreguntasService.analizar(self.actor, self.ev.pk, lambda e: self.fail('No debe invocarse'), valoracion_id=self.v.pk)


    def test_relleno_no_es_fuente_y_conserva_texto(self):
        from apps.application.services.suficiencia import _entrada
        p = self.generar()[0]
        Servicio.responder(self.actor, self.ev.pk, p.pk, 'sadasd')
        f = Servicio.contexto(self.actor, self.ev.pk)[0]
        self.assertEqual(f['estado_informacion'], 'SIN_APORTE')
        self.assertEqual(f['preguntas'][0]['estado_respuesta'], 'NO_INFORMATIVA')
        self.assertEqual(f['preguntas'][0]['respuesta'], 'sadasd')
        self.assertEqual(_entrada(f)['fuentes'], [])
        Servicio.responder(self.actor, self.ev.pk, p.pk, 'ODF')
        self.assertEqual(len(_entrada(Servicio.contexto(self.actor, self.ev.pk)[0])['fuentes']), 1)

    def test_historial_registra_rondas_sin_duplicar_reutilizacion(self):
        from apps.application.services.suficiencia import SuficienciaService
        from apps.data.models import HistorialSuficiencia
        e = self.evidencia('Admite ODF')
        def proveedor(entrada):
            return {'estado': 'SUFICIENTE', 'justificacion': 'Formato identificado', 'referencias': [f'E:{e.pk}'], 'preguntas': []}
        for _ in range(2):
            SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, proveedor, 'prueba')
        self.assertEqual(HistorialSuficiencia.objects.count(), 1)
        self.evidencia('Admite PDF')
        SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, proveedor, 'prueba')
        self.assertEqual(list(HistorialSuficiencia.objects.values_list('rondas', flat=True)), [2, 1])
        self.assertEqual(set(HistorialSuficiencia.objects.values_list('actor_id', flat=True)), {self.actor.pk})

    def test_entrega_hu10_distingue_fuentes_y_no_valora(self):
        from apps.application.services.preparacion_hu10 import PreparacionHU10Service as H
        from apps.application.services.suficiencia import SuficienciaService
        p = self.generar()[0]
        Servicio.responder(self.actor, self.ev.pk, p.pk, 'ODF 1.3')
        e = self.evidencia('Formato ODF')
        SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, lambda entrada: {
            'estado': 'SUFICIENTE', 'justificacion': 'Datos aportados', 'referencias': [f'E:{e.pk}', f'R:{p.pk}'], 'preguntas': []}, 'prueba')
        f = H.obtener(self.actor, self.ev.pk)['subfactores'][0]
        self.assertEqual(f['estado'], 'PROPUESTA_HABILITADA')
        self.assertEqual([fuente['origen'] for fuente in f['fuentes']], ['DOCUMENTO', 'DECLARACION_DECISOR'])
        self.assertEqual(H.validar_vigencia(self.actor, self.ev.pk, self.v.pk, f['huella']), f)
        self.v.refresh_from_db()
        self.assertIsNone(self.v.valor_ia)
        self.assertIsNone(self.v.valor_confirmado)
        Servicio.responder(self.actor, self.ev.pk, p.pk, 'ODF 1.2')
        with self.assertRaises(ValidationError):
            H.validar_vigencia(self.actor, self.ev.pk, self.v.pk, f['huella'])

    def test_entrega_hu10_exige_propietario_y_relevancia(self):
        from apps.application.services.preparacion_hu10 import PreparacionHU10Service as H
        for actor in (self.otro, self.admin):
            with self.assertRaises(PermissionDenied):
                H.obtener(actor, self.ev.pk)
        self.assertEqual([f['valoracion_id'] for f in H.obtener(self.actor, self.ev.pk)['subfactores']], [self.v.pk])

    def test_entrega_hu10_no_confunde_desconocimiento_con_suficiencia(self):
        from apps.application.services.preparacion_hu10 import PreparacionHU10Service as H
        from apps.application.services.suficiencia import SuficienciaService
        p = self.generar()[0]
        self.assertEqual(H.obtener(self.actor, self.ev.pk)['subfactores'][0]['estado'], 'PREGUNTAS_PENDIENTES')
        Servicio.responder(self.actor, self.ev.pk, p.pk, 'No lo sé')
        SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, lambda entrada: {
            'estado': 'INSUFICIENTE', 'justificacion': 'No hay datos', 'referencias': [], 'preguntas': []}, 'prueba')
        f = H.obtener(self.actor, self.ev.pk)['subfactores'][0]
        self.assertEqual(f['estado'], 'REVISION_MANUAL')
        self.assertEqual(f['fuentes'], [])
        self.assertEqual(f['sin_informacion'][0]['estado'], 'DESCONOCE')
        with self.assertRaises(ValidationError):
            H.validar_vigencia(self.actor, self.ev.pk, self.v.pk, f['huella'])

    def test_entrega_hu10_bloquea_lote_y_cierre(self):
        from apps.application.services.preparacion_hu10 import PreparacionHU10Service as H
        from apps.data.models import LoteHU09
        LoteHU09.objects.create(evaluacion=self.ev, solicitante=self.actor, objetivos=[self.v.pk])
        self.assertEqual(H.obtener(self.actor, self.ev.pk)['subfactores'][0]['estado'], 'ANALISIS_EN_CURSO')
        Evaluacion.objects.filter(pk=self.ev.pk).update(estado='FINALIZADA')
        self.assertEqual(H.obtener(self.actor, self.ev.pk)['subfactores'][0]['estado'], 'SOLO_LECTURA')


    def test_descarta_y_restaura_respondida_sin_perder_datos(self):
        from apps.application.services.suficiencia import SuficienciaService
        from apps.application.services.preparacion_hu10 import PreparacionHU10Service as H
        from apps.data.models import HistorialSuficiencia
        p = self.generar()[0]
        p = Servicio.responder(self.actor, self.ev.pk, p.pk, 'ODF 1.3')
        version = p.fecha_respuesta.isoformat()
        SuficienciaService.analizar(self.actor, self.ev.pk, self.v.pk, lambda e: {
            'estado': 'SUFICIENTE', 'justificacion': 'Formato identificado',
            'referencias': [f'R:{p.pk}'], 'preguntas': []}, 'prueba')
        inicial = H.obtener(self.actor, self.ev.pk)['subfactores'][0]
        self.assertEqual(inicial['estado'], 'PROPUESTA_HABILITADA')
        Servicio.descartar(self.actor, self.ev.pk, p.pk, confirmar=True, version=version)
        f = H.obtener(self.actor, self.ev.pk)['subfactores'][0]
        self.assertEqual(f['fuentes'], [])
        self.assertEqual(f['estado'], 'ANALISIS_PENDIENTE')
        self.assertEqual(Servicio.contexto(self.actor, self.ev.pk)[0]['preguntas_descartadas'][0]['respuesta'], 'ODF 1.3')
        Servicio.restaurar(self.actor, self.ev.pk, p.pk)
        p.refresh_from_db()
        self.assertEqual(p.respuesta, 'ODF 1.3')
        self.assertEqual(p.respondido_por_id, self.actor.pk)
        self.assertEqual(p.fecha_respuesta.isoformat(), version)
        self.assertIsNone(p.fecha_descarte)
        self.assertEqual(H.obtener(self.actor, self.ev.pk)['subfactores'][0]['estado'], 'ANALISIS_PENDIENTE')
        self.assertEqual(HistorialSuficiencia.objects.count(), 1)
        with self.assertRaises(ValidationError):
            H.validar_vigencia(self.actor, self.ev.pk, self.v.pk, inicial['huella'])

    def test_descartar_respondida_exige_version_actual(self):
        p = self.generar()[0]
        p = Servicio.responder(self.actor, self.ev.pk, p.pk, 'No lo sé')
        anterior = p.fecha_respuesta.isoformat()
        p = Servicio.responder(self.actor, self.ev.pk, p.pk, 'Sin datos técnicos')
        for version in (None, anterior):
            with self.assertRaises(ValidationError):
                Servicio.descartar(self.actor, self.ev.pk, p.pk, confirmar=True, version=version)
        p.refresh_from_db()
        self.assertIsNone(p.fecha_descarte)

    def test_restaura_respondida_sin_ocupar_cupo_de_pendientes(self):
        p = self.generar()[0]
        p = Servicio.responder(self.actor, self.ev.pk, p.pk, 'No lo sé')
        Servicio.descartar(self.actor, self.ev.pk, p.pk, confirmar=True, version=p.fecha_respuesta.isoformat())
        Servicio.registrar_vacios(self.actor, self.ev.pk, self.v.pk, ['¿Una?', '¿Dos?', '¿Tres?'])
        Servicio.restaurar(self.actor, self.ev.pk, p.pk)
        p.refresh_from_db()
        self.assertIsNone(p.fecha_descarte)
        self.assertEqual(p.respuesta, 'No lo sé')

    def test_contexto_61_subfactores_sin_consultas_n_mas_uno(self):
        ef = self.v.evaluacion_factor
        for n in range(60):
            sf = Subfactor.objects.create(factor=ef.factor, descripcion=f'Subfactor de carga {n}')
            v = ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=sf)
            Servicio.registrar_vacios(self.actor, self.ev.pk, v.pk, [f'¿Dato {n}?'])
        self.evidencia('ODF')
        self.evidencia('Documento ajeno', self.doc2)
        # Actor, evaluación, valoraciones y dos prefetches de relaciones.
        with self.assertNumQueries(5):
            filas = Servicio.contexto(self.actor, self.ev.pk)
        self.assertEqual(len(filas), 61)
        self.assertEqual(sum(len(f['preguntas']) for f in filas), 60)
        self.assertEqual(sum(len(f['evidencias']) for f in filas), 1)
        with self.assertNumQueries(5):
            fila = Servicio.contexto(self.actor, self.ev.pk, valoracion_id=self.v.pk)
        self.assertEqual(len(fila), 1)
        self.assertEqual(fila[0], next(f for f in filas if f['valoracion_id'] == self.v.pk))

    def test_tecleo_repetitivo_no_se_utiliza_como_fuente(self):
        from apps.application.services.preguntas import estado_respuesta
        from apps.application.services.suficiencia import _entrada
        for texto in ('adssadsad', 'asdasdasd', 'SADSADSAD'):
            self.assertEqual(estado_respuesta(texto), 'NO_INFORMATIVA')
        for texto in ('ODF', 'SAS', 'ADS', 'ODF 1.3', 'No admite ODF 1.3', 'ADS y S3'):
            self.assertEqual(estado_respuesta(texto), 'APORTADA')
        p = self.generar()[0]
        Servicio.responder(self.actor, self.ev.pk, p.pk, 'adssadsad')
        fila = Servicio.contexto(self.actor, self.ev.pk)[0]
        self.assertEqual(fila['preguntas'][0]['respuesta'], 'adssadsad')
        self.assertEqual(fila['estado_informacion'], 'SIN_APORTE')
        self.assertEqual(_entrada(fila)['fuentes'], [])
