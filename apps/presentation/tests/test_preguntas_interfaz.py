from datetime import date

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.application.services.preguntas import PreguntasService
from apps.data.models import (CatalogoVersion, Dimension, Evaluacion, EvaluacionFactor, Factor,
                              Organizacion, PreguntaComplementaria, Software, Subfactor, Usuario,
                              ValoracionSubfactor)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], HU09_EMBEDDING_MODEL='', GUIOS_AI_BACKEND='ollama')
class PreguntasInterfazTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
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

    def test_lista_solo_evaluaciones_propias(self):
        res = self.client.get(self.url)
        self.assertContains(res, 'Software propio')
        self.assertNotContains(res, 'Software ajeno')

    def test_vista_agrupa_y_excluye_ir_uno(self):
        res = self.client.get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(res, 'Requisito Seguridad')
        self.assertNotContains(res, 'Requisito Excluido')
        self.assertContains(res, 'Sin evidencia vinculada ni respuestas')
        self.assertEqual(PreguntaComplementaria.objects.count(), 0)

    def test_detectar_y_repetir(self):
        self.assertEqual(self.post('detectar').status_code, 302)
        self.assertEqual(self.post('detectar').status_code, 302)
        self.assertEqual(PreguntaComplementaria.objects.count(), 1)

    def test_responder_y_mostrar_progreso(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        self.assertEqual(self.post('responder', pregunta=p.pk, respuesta='Respuesta de prueba').status_code, 302)
        res = self.client.get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(res, 'Respuesta de prueba')
        self.assertEqual(res.context['respondidas'], 1)
        self.assertEqual(res.context['pendientes'], 0)

    def test_respuesta_vacia_se_rechaza(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        res = self.post('responder', pregunta=p.pk, respuesta=' ')
        self.assertContains(res, 'La respuesta debe contener', status_code=400)
        p.refresh_from_db()
        self.assertEqual(p.respuesta, '')

    def test_evaluacion_ajena_prohibida(self):
        self.assertEqual(self.client.get(self.url, {'evaluacion': self.ajena.pk}).status_code, 403)
        self.assertEqual(self.post('detectar', evaluacion=self.ajena.pk).status_code, 403)

    def test_admin_y_anonimo_no_acceden(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_evaluacion_cerrada_solo_lectura(self):
        PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)
        Evaluacion.objects.filter(pk=self.ev.pk).update(estado='FINALIZADA')
        res = self.client.get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(res, 'Solo lectura')
        self.assertNotContains(res, 'Guardar respuesta')
        self.assertEqual(self.post('detectar').status_code, 400)

    def test_post_exige_csrf(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.actor)
        self.assertEqual(c.post(self.url, {'evaluacion': self.ev.pk, 'accion': 'detectar'}).status_code, 403)

    def test_identificadores_y_accion_invalidos(self):
        self.assertEqual(self.client.get(self.url, {'evaluacion': 'abc'}).status_code, 400)
        self.assertEqual(self.post('desconocida').status_code, 400)
        self.assertEqual(self.post('responder', pregunta='abc').status_code, 400)

    def test_boton_no_lo_se_registra_desconocimiento(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        self.assertEqual(self.post('desconozco', pregunta=p.pk).status_code, 302)
        res = self.client.get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(res, 'Información desconocida')
        self.assertContains(res, 'Desconocida')
        self.assertEqual(res.context['desconocidas'], 1)
        self.assertEqual(res.context['respondidas'], 1)
        p.refresh_from_db()
        self.assertEqual(p.respuesta, 'No lo sé')

    @override_settings(HU09_OLLAMA_MODEL='')
    def test_ia_desactivada_conserva_modo_manual(self):
        v = ValoracionSubfactor.objects.get(evaluacion_factor__evaluacion=self.ev, evaluacion_factor__importancia_relativa=3)
        res = self.post('analizar', valoracion=v.pk)
        self.assertContains(res, 'no está configurado', status_code=400)
        self.assertFalse(PreguntaComplementaria.objects.exists())

    @override_settings(HU09_OLLAMA_MODEL='qwen3:4b-instruct')
    def test_ia_propuesta_para_subfactor_seleccionado(self):
        from unittest.mock import patch
        v = ValoracionSubfactor.objects.get(evaluacion_factor__evaluacion=self.ev, evaluacion_factor__importancia_relativa=3)
        with patch('apps.presentation.views.preguntas.OllamaPreguntas') as proveedor:
            proveedor.return_value.return_value = ['¿Cada cuánto se actualiza?']
            self.assertEqual(self.post('analizar', valoracion=v.pk).status_code, 302)
            proveedor.return_value.assert_called_once()
        self.assertEqual(PreguntaComplementaria.objects.get().texto, '¿Cada cuánto se actualiza?')
        self.assertContains(self.client.get(self.url, {'evaluacion': self.ev.pk}), 'Analizar vacíos con IA')

    @override_settings(HU09_OLLAMA_MODEL='qwen3:4b-instruct')
    def test_ia_proveedor_no_disponible_no_crea_preguntas(self):
        from unittest.mock import patch
        from apps.external_services.ollama_preguntas import AnalisisNoDisponible
        v = ValoracionSubfactor.objects.get(evaluacion_factor__evaluacion=self.ev, evaluacion_factor__importancia_relativa=3)
        with patch('apps.presentation.views.preguntas.OllamaPreguntas') as proveedor:
            proveedor.return_value.side_effect = AnalisisNoDisponible('Proveedor no disponible')
            self.assertContains(self.post('analizar', valoracion=v.pk), 'Proveedor no disponible', status_code=400)
        self.assertFalse(PreguntaComplementaria.objects.exists())

    @override_settings(HU09_OLLAMA_MODEL='qwen3:4b-instruct')
    def test_ia_no_analiza_subfactor_excluido(self):
        from unittest.mock import patch
        v = ValoracionSubfactor.objects.get(evaluacion_factor__evaluacion=self.ev, evaluacion_factor__importancia_relativa=1)
        with patch('apps.presentation.views.preguntas.OllamaPreguntas') as proveedor:
            self.assertEqual(self.post('analizar', valoracion=v.pk).status_code, 400)
            proveedor.return_value.assert_not_called()
        self.assertFalse(PreguntaComplementaria.objects.exists())

    def test_descartar_excluye_del_progreso_y_muestra_historial(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        self.assertEqual(self.post('descartar', pregunta=p.pk).status_code, 302)
        res = self.client.get(self.url, {'evaluacion': self.ev.pk})
        self.assertEqual(res.context['total'], 0)
        self.assertEqual(res.context['descartadas'], 1)
        self.assertContains(res, 'Historial de preguntas descartadas')
        self.assertNotContains(res, 'Guardar respuesta')
        self.assertEqual(self.post('responder', pregunta=p.pk, respuesta='Texto').status_code, 400)

    @override_settings(HU09_OLLAMA_MODEL='qwen3:4b-instruct')
    def test_cupo_lleno_oculta_analisis(self):
        v = ValoracionSubfactor.objects.get(evaluacion_factor__evaluacion=self.ev, evaluacion_factor__importancia_relativa=3)
        PreguntasService.registrar_vacios(self.actor, self.ev.pk, v.pk, ['¿Una?', '¿Dos?', '¿Tres?'])
        res = self.client.get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(res, 'Cupo de preguntas pendientes alcanzado')
        self.assertNotContains(res, 'Analizar vacíos con IA')

    def test_descartar_requiere_csrf(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.actor)
        self.assertEqual(c.post(self.url, {'evaluacion': self.ev.pk, 'accion': 'descartar', 'pregunta': p.pk}).status_code, 403)
        p.refresh_from_db()
        self.assertIsNone(p.fecha_descarte)

    def test_restaurar_desde_historial_actualiza_progreso(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        PreguntasService.descartar(self.actor, self.ev.pk, p.pk)
        self.assertContains(self.client.get(self.url, {'evaluacion': self.ev.pk}), 'Restaurar pregunta')
        self.assertEqual(self.post('restaurar', pregunta=p.pk).status_code, 302)
        res = self.client.get(self.url, {'evaluacion': self.ev.pk})
        self.assertEqual(res.context['total'], 1)
        self.assertEqual(res.context['descartadas'], 0)

    @override_settings(HU09_OLLAMA_MODEL='qwen3:4b-instruct', HU09_EMBEDDING_MODEL='bge-m3')
    def test_embeddings_configurados_se_utilizan(self):
        from unittest.mock import patch
        v = ValoracionSubfactor.objects.get(evaluacion_factor__evaluacion=self.ev, evaluacion_factor__importancia_relativa=3)
        with patch('apps.presentation.views.preguntas.OllamaPreguntas') as generador, patch('apps.presentation.views.preguntas.OllamaEmbeddings') as embeddings:
            generador.return_value.return_value = ['¿Qué versiones admite?', '¿Cuáles son las ediciones compatibles?']
            embeddings.return_value.return_value = [[1, 0], [1, 0]]
            self.assertEqual(self.post('analizar', valoracion=v.pk).status_code, 302)
            embeddings.assert_called_once_with('bge-m3')
        self.assertEqual(PreguntaComplementaria.objects.count(), 1)

    @override_settings(HU09_OLLAMA_MODEL='qwen3:4b-instruct', HU09_EMBEDDING_MODEL='bge-m3')
    def test_fallo_embeddings_no_guarda(self):
        from unittest.mock import patch
        from apps.external_services.ollama_preguntas import AnalisisNoDisponible
        v = ValoracionSubfactor.objects.get(evaluacion_factor__evaluacion=self.ev, evaluacion_factor__importancia_relativa=3)
        with patch('apps.presentation.views.preguntas.OllamaPreguntas') as generador, patch('apps.presentation.views.preguntas.OllamaEmbeddings') as embeddings:
            generador.return_value.return_value = ['¿Qué versiones admite?']
            embeddings.return_value.side_effect = AnalisisNoDisponible('Embeddings no disponibles')
            self.assertContains(self.post('analizar', valoracion=v.pk), 'Embeddings no disponibles', status_code=400)
        self.assertFalse(PreguntaComplementaria.objects.exists())

    @override_settings(HU09_OLLAMA_MODEL='qwen3:4b-instruct')
    def test_suficiencia_muestra_resultado_orientativo(self):
        from unittest.mock import patch
        vid = PreguntasService.contexto(self.actor, self.ev.pk)[0]['valoracion_id']
        with patch('apps.presentation.views.preguntas.OllamaSuficiencia') as proveedor:
            proveedor.return_value.return_value = {'estado': 'INSUFICIENTE', 'justificacion': 'Sin fuentes disponibles', 'referencias': [], 'preguntas': []}
            self.assertEqual(self.post('suficiencia', valoracion=vid).status_code, 302)
        res = self.client.get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(res, 'Revisión manual necesaria')
        self.assertContains(res, 'Sin fuentes disponibles')
        self.assertContains(res, 'Rondas de suficiencia: 1/3')

    def test_autoguardado_persiste_y_actualiza_contadores(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        res = self.post('autoguardar', pregunta=p.pk, respuesta='Procedimiento documentado', version='')
        self.assertEqual(res.status_code, 200)
        datos = res.json()
        p.refresh_from_db()
        self.assertEqual(p.respuesta, 'Procedimiento documentado')
        self.assertEqual(datos['estado'], 'APORTADA')
        self.assertEqual(datos['respondidas'], 1)
        self.assertEqual(datos['version'], p.fecha_respuesta.isoformat())

    def test_autoguardado_rechaza_version_obsoleta(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        PreguntasService.responder(self.actor, self.ev.pk, p.pk, 'Respuesta actual')
        res = self.post('autoguardar', pregunta=p.pk, respuesta='Borrador anterior', version='')
        self.assertEqual(res.status_code, 400)
        p.refresh_from_db()
        self.assertEqual(p.respuesta, 'Respuesta actual')

    def test_autoguardado_exige_version_y_no_admite_vacio(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        self.assertEqual(self.post('autoguardar', pregunta=p.pk, respuesta='Texto').status_code, 400)
        self.assertEqual(self.post('autoguardar', pregunta=p.pk, respuesta=' ', version='').status_code, 400)
        p.refresh_from_db()
        self.assertEqual(p.respuesta, '')

    def test_autoguardado_exige_propietario_y_csrf(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.actor)
        self.assertEqual(c.post(self.url, {'evaluacion': self.ev.pk, 'accion': 'autoguardar', 'pregunta':p.pk, 'respuesta':'Texto', 'version':''}).status_code, 403)
        self.client.force_login(self.otro)
        self.assertEqual(self.post('autoguardar', pregunta=p.pk, respuesta='Texto', version='').status_code, 403)

    def test_autoguardado_no_reescribe_respuesta_identica(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        primero = self.post('autoguardar', pregunta=p.pk, respuesta='No lo sé', version='').json()
        segundo = self.post('autoguardar', pregunta=p.pk, respuesta='No lo sé', version=primero['version']).json()
        self.assertEqual(primero['version'], segundo['version'])
        self.assertEqual(segundo['desconocidas'], 1)

    def test_indice_filtros_y_version_en_formulario(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        res = self.client.get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(res, 'id="hu09-buscar"')
        self.assertContains(res, 'id="hu09-filtro"')
        self.assertContains(res, f'href="#subfactor-{p.valoracion_id}"')
        self.assertContains(res, 'name="version"')


    def test_autoguardado_distingue_relleno_de_desconocimiento(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        datos = self.post('autoguardar', pregunta=p.pk, respuesta='sadasd', version='').json()
        self.assertEqual(datos['estado'], 'NO_INFORMATIVA')
        self.assertEqual(datos['no_informativas'], 1)
        self.assertEqual(datos['desconocidas'], 0)
        self.assertContains(self.client.get(self.url, {'evaluacion': self.ev.pk}), 'Sin aporte')

    @override_settings(HU09_OLLAMA_MODEL='qwen3:4b-instruct')
    def test_historial_y_estado_entrega_visibles(self):
        from unittest.mock import patch
        vid = PreguntasService.contexto(self.actor, self.ev.pk)[0]['valoracion_id']
        with patch('apps.presentation.views.preguntas.OllamaSuficiencia') as proveedor:
            proveedor.return_value.return_value = {'estado': 'INSUFICIENTE', 'justificacion': 'Sin fuentes', 'referencias': [], 'preguntas': []}
            self.assertEqual(self.post('suficiencia', valoracion=vid).status_code, 302)
        res = self.client.get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(res, 'Historial de suficiencia (1)')
        self.assertContains(res, 'Preparación para HU10:')
        self.assertContains(res, 'Sin fuentes')


    def test_descartar_respondida_visible_y_conserva_respuesta(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        datos = self.post('autoguardar', pregunta=p.pk, respuesta='ODF 1.3', version='').json()
        self.assertContains(self.client.get(self.url, {'evaluacion': self.ev.pk}), 'Descartar pregunta')
        self.assertEqual(self.post('descartar', pregunta=p.pk, version=datos['version']).status_code, 400)
        self.assertEqual(self.post('descartar', pregunta=p.pk, confirmar='1', version=datos['version']).status_code, 302)
        res = self.client.get(self.url, {'evaluacion': self.ev.pk})
        self.assertEqual(res.context['total'], 0)
        self.assertEqual(res.context['respondidas'], 0)
        self.assertEqual(res.context['descartadas'], 1)
        self.assertContains(res, 'Respuesta conservada:')
        self.assertContains(res, 'ODF 1.3')
        self.assertEqual(self.post('restaurar', pregunta=p.pk).status_code, 302)
        res = self.client.get(self.url, {'evaluacion': self.ev.pk})
        self.assertEqual(res.context['respondidas'], 1)
        self.assertContains(res, 'ODF 1.3')

    def test_descartar_confirmada_no_elude_version_ni_propiedad(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        datos = self.post('autoguardar', pregunta=p.pk, respuesta='No lo sé', version='').json()
        self.assertEqual(self.post('descartar', pregunta=p.pk, confirmar='1', version='').status_code, 400)
        self.client.force_login(self.otro)
        self.assertEqual(self.post('descartar', pregunta=p.pk, confirmar='1', version=datos['version']).status_code, 403)
        p.refresh_from_db()
        self.assertIsNone(p.fecha_descarte)

    def test_dialogo_descarte_y_tecleo_repetitivo(self):
        p = PreguntasService.detectar_sin_evidencia(self.actor, self.ev.pk)[0]
        datos = self.post('autoguardar', pregunta=p.pk, respuesta='adssadsad', version='').json()
        self.assertEqual(datos['estado'], 'NO_INFORMATIVA')
        res = self.client.get(self.url, {'evaluacion': self.ev.pk})
        self.assertContains(res, 'id="hu09-confirmar-descarte"')
        self.assertContains(res, 'id="hu09-cancelar-descarte"')
        self.assertContains(res, 'id="hu09-aceptar-descarte"')
        self.assertContains(res, 'Sin aporte')
        self.assertEqual(self.post('descartar', pregunta=p.pk, version=datos['version']).status_code, 400)
        self.assertEqual(self.post('descartar', pregunta=p.pk, confirmar='1', version=datos['version']).status_code, 302)
