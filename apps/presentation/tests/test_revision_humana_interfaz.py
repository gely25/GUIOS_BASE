from datetime import date

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.application.services.preguntas import PreguntasService
from apps.application.services.revision_humana import RevisionHumanaService
from apps.data.models import (BorradorRevisionHumana, CatalogoVersion, Dimension, Documento, Evaluacion, EvaluacionFactor,
    Evidencia, Factor, FragmentoDocumento, LoteHU09, Organizacion, RevisionHumana, Software,
    Subfactor, Usuario, ValoracionSubfactor)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RevisionHumanaInterfazTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
        org = Organizacion.objects.create(nombre='Org revisión')
        cls.actor = Usuario.objects.create_user('decisor@revision.test', 'Clave-test-123', nombre='Decisor', organizacion=org)
        cls.otro = Usuario.objects.create_user('otro@revision.test', 'Clave-test-123', nombre='Otro', organizacion=org)
        cls.admin = Usuario.objects.create_superuser('admin@revision.test', 'Clave-test-123', nombre='Admin')
        cat = CatalogoVersion.objects.create(version='HU11 interfaz', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(organizacion=org, usuario=cls.actor, software=Software.objects.create(nombre='Software propio HU11'), catalogo=cat)
        cls.ajena = Evaluacion.objects.create(organizacion=org, usuario=cls.otro, software=Software.objects.create(nombre='Software privado HU11'), catalogo=cat)
        dim = Dimension.objects.create(nombre='Tecnológica')
        for nombre, ir, valor in [('Compatibilidad', 3, 4), ('Seguridad', 4, None), ('Excluido', 1, None)]:
            f = Factor.objects.create(dimension=dim, nombre=nombre, alcance=Factor.EXTERNO)
            ef = EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=f, importancia_relativa=ir)
            sf = Subfactor.objects.create(factor=f, descripcion='Requisito ' + nombre)
            v = ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=sf, valor_ia=valor,
                justificacion_ia='Propuesta de prueba ODF.' if valor else None)
            if ir == 3:
                cls.v = v
            elif ir == 4:
                cls.manual = v
            else:
                cls.excluida = v
        doc = Documento.objects.create(evaluacion=cls.ev, usuario=cls.actor, nombre='Documento propio', tipo='PDF', ubicacion='demo.pdf')
        Evidencia.objects.create(valoracion=cls.v, fragmento=FragmentoDocumento.objects.create(documento=doc, contenido='Fragmento propio ODF 1.2.', pagina=2))
        otro_doc = Documento.objects.create(evaluacion=cls.ajena, usuario=cls.otro, nombre='Documento privado', tipo='PDF', ubicacion='privado.pdf')
        Evidencia.objects.create(valoracion=cls.v, fragmento=FragmentoDocumento.objects.create(documento=otro_doc, contenido='Fragmento secreto ajeno.'))

    def setUp(self):
        self.url = reverse('presentation:decisor-revision-valoraciones')
        self.client.force_login(self.actor)

    def get(self, **kwargs):
        return self.client.get(self.url, {'etapa': 'validacion', **kwargs})

    def payload(self, v=None, **extra):
        v = v or self.v
        return {'etapa': 'validacion', 'evaluacion': self.ev.pk, 'valoracion': v.pk,
                'accion': 'resolver_hu11', 'modo': 'CONFIRMAR', 'valor': '4',
                'justificacion': 'Revisión de prueba.',
                'version': RevisionHumanaService.obtener(self.actor, self.ev.pk, v.pk)['version'], **extra}

    def test_lista_evaluaciones_propias_y_enlace_hu09(self):
        res = self.get()
        self.assertContains(res, 'Software propio HU11')
        self.assertNotContains(res, 'Software privado HU11')
        self.assertContains(self.client.get(self.url), 'Ir a validación humana (HU11)')

    def test_comparacion_fuentes_y_exclusion(self):
        p = PreguntasService.registrar_vacios(self.actor, self.ev.pk, self.v.pk, ['¿Formatos?'])[0]
        PreguntasService.responder(self.actor, self.ev.pk, p.pk, 'Admite ODF.')
        res = self.get(evaluacion=self.ev.pk, valoracion=self.v.pk)
        self.assertContains(res, '4/4')
        self.assertContains(res, 'Fragmento propio ODF 1.2.')
        self.assertContains(res, 'Declaración del decisor')
        self.assertContains(res, 'Admite ODF.')
        self.assertNotContains(res, 'Fragmento secreto ajeno.')
        self.assertNotContains(res, 'Requisito Excluido')
        self.assertEqual(res.context['total'], 2)
        self.assertFalse(RevisionHumana.objects.exists())

    def test_confirma_y_muestra_historial(self):
        res = self.client.post(self.url, self.payload(), follow=True)
        self.assertContains(res, 'Decisión humana registrada')
        self.assertContains(res, 'Revisión de prueba.')
        self.assertEqual(res.context['revisadas'], 1)
        self.assertContains(res, 'Solo lectura')
        self.assertEqual(RevisionHumana.objects.get().valor, 4)

    def test_modifica_conservando_propuesta(self):
        res = self.client.post(self.url, self.payload(modo='MODIFICAR', valor='3'), follow=True)
        self.assertContains(res, '3/4')
        self.assertContains(res, '4/4')
        self.v.refresh_from_db()
        self.assertEqual((self.v.valor_ia, self.v.valor_confirmado), (4, 3))

    def test_manual_sin_propuesta(self):
        res = self.get(evaluacion=self.ev.pk, valoracion=self.manual.pk)
        self.assertContains(res, 'Valoración manual')
        self.assertNotContains(res, 'Confirmar propuesta')
        res = self.client.post(self.url, self.payload(self.manual, modo='MANUAL', valor='2'), follow=True)
        self.assertContains(res, '2/4')
        self.assertIsNone(RevisionHumana.objects.get().valor_ia)

    def test_rechaza_decision_incompatible_y_conserva_borrador(self):
        res = self.client.post(self.url, self.payload(valor='3'))
        self.assertContains(res, 'La acción no corresponde', status_code=400)
        self.assertContains(res, 'Revisión de prueba.', status_code=400)
        self.assertFalse(RevisionHumana.objects.exists())

    def test_version_obsoleta_no_se_actualiza_sin_consulta(self):
        datos = self.payload()
        ValoracionSubfactor.objects.filter(pk=self.v.pk).update(justificacion_ia='Propuesta nueva.')
        res = self.client.post(self.url, datos)
        self.assertContains(res, 'La información cambió', status_code=400)
        self.assertEqual(res.context['seleccion']['version'], datos['version'])
        self.assertFalse(RevisionHumana.objects.exists())

    def test_propiedad_y_exclusion(self):
        self.assertEqual(self.get(evaluacion=self.ajena.pk).status_code, 403)
        self.assertEqual(self.get(evaluacion=self.ev.pk, valoracion=self.excluida.pk).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.payload(valoracion=self.excluida.pk)).status_code, 403)
        self.client.force_login(self.otro)
        self.assertEqual(self.get(evaluacion=self.ev.pk).status_code, 403)

    def test_rol_y_csrf(self):
        datos = self.payload()
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.actor)
        self.assertEqual(cliente.post(self.url, datos).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.get(evaluacion=self.ev.pk).status_code, 403)
        self.assertEqual(self.client.post(self.url, datos).status_code, 403)
        self.client.logout()
        self.assertEqual(self.get(evaluacion=self.ev.pk).status_code, 302)

    def test_solo_lectura_en_lote_o_cierre(self):
        datos = self.payload()
        lote = LoteHU09.objects.create(evaluacion=self.ev, solicitante=self.actor)
        self.assertNotContains(self.get(evaluacion=self.ev.pk), 'Registrar decisión definitiva')
        self.assertEqual(self.client.post(self.url, datos).status_code, 400)
        lote.delete()
        Evaluacion.objects.filter(pk=self.ev.pk).update(estado='FINALIZADA')
        self.assertNotContains(self.get(evaluacion=self.ev.pk), 'Registrar decisión definitiva')
        self.assertEqual(self.client.post(self.url, datos).status_code, 400)
        self.assertFalse(RevisionHumana.objects.exists())

    def test_identificadores_y_accion_invalidos(self):
        self.assertEqual(self.get(evaluacion='x').status_code, 400)
        self.assertEqual(self.get(evaluacion=self.ev.pk, valoracion='x').status_code, 400)
        self.assertEqual(self.client.post(self.url, self.payload(accion='invalida')).status_code, 400)
        self.assertEqual(self.client.post(self.url, self.payload(valor='5')).status_code, 400)


    def guardar(self, v=None, **extra):
        return self.client.post(self.url, self.payload(v, accion='guardar_borrador_hu11',
            version_borrador='0', **extra))

    def token(self, v):
        b = BorradorRevisionHumana.objects.get(valoracion=v)
        return f'{v.pk}:{b.version}:{b.huella_contexto}'

    def lote(self, tokens, confirmar='1'):
        return self.client.post(self.url, {'etapa': 'validacion', 'evaluacion': self.ev.pk,
            'accion': 'resolver_lote_hu11', 'seleccion': tokens, 'confirmar_lote': confirmar}, follow=True)

    def test_borrador_parcial_persiste_sin_confirmar(self):
        res = self.guardar(modo='', valor='', justificacion='Texto en construcción.')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['version_borrador'], '1')
        self.assertEqual(BorradorRevisionHumana.objects.get().justificacion, 'Texto en construcción.')
        self.v.refresh_from_db()
        self.assertIsNone(self.v.valor_confirmado)
        self.assertFalse(RevisionHumana.objects.exists())
        res = self.get(evaluacion=self.ev.pk, valoracion=self.v.pk)
        self.assertContains(res, 'Texto en construcción.')
        self.assertEqual(res.context['revisadas'], 0)
        self.assertEqual(res.context['cantidad_borradores'], 1)
        self.assertEqual(res.context['borradores'], [])

    def test_borrador_version_concurrente(self):
        self.assertEqual(self.guardar().status_code, 200)
        self.assertEqual(self.guardar(justificacion='Conflicto').status_code, 400)
        res = self.client.post(self.url, self.payload(accion='guardar_borrador_hu11', version_borrador='1', justificacion='Actualizado'))
        self.assertEqual(res.json()['version_borrador'], '2')
        self.assertEqual(BorradorRevisionHumana.objects.get().justificacion, 'Actualizado')

    def test_borrador_propiedad_csrf_y_cierre(self):
        data = self.payload(accion='guardar_borrador_hu11', version_borrador='0')
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.actor)
        self.assertEqual(c.post(self.url, data).status_code, 403)
        self.client.force_login(self.otro)
        self.assertEqual(self.client.post(self.url, data).status_code, 403)
        self.client.force_login(self.actor)
        Evaluacion.objects.filter(pk=self.ev.pk).update(estado='FINALIZADA')
        self.assertEqual(self.client.post(self.url, data).status_code, 400)
        self.assertFalse(BorradorRevisionHumana.objects.exists())

    def test_borrador_no_sobrescribe_contexto_obsoleto(self):
        data = self.payload(accion='guardar_borrador_hu11', version_borrador='0')
        ValoracionSubfactor.objects.filter(pk=self.v.pk).update(justificacion_ia='Nueva propuesta.')
        self.assertEqual(self.client.post(self.url, data).status_code, 400)
        self.assertFalse(BorradorRevisionHumana.objects.exists())

    def test_decision_individual_exige_version_del_borrador(self):
        self.assertEqual(self.guardar().status_code, 200)
        self.assertEqual(self.client.post(self.url, self.payload(version_borrador='0')).status_code, 400)
        self.assertFalse(RevisionHumana.objects.exists())
        self.assertEqual(self.client.post(self.url, self.payload(version_borrador='1')).status_code, 302)
        self.assertFalse(BorradorRevisionHumana.objects.exists())
        self.assertEqual(RevisionHumana.objects.count(), 1)

    def test_lote_solo_seleccionados_y_confirmacion_explicita(self):
        self.assertEqual(self.guardar().status_code, 200)
        self.assertEqual(self.guardar(self.manual, modo='MANUAL', valor='2').status_code, 200)
        token = self.token(self.v)
        self.assertContains(self.lote([token], confirmar=''), 'Confirme expresamente')
        self.assertFalse(RevisionHumana.objects.exists())
        self.assertContains(self.lote([token]), 'Decisiones humanas registradas: 1')
        self.assertEqual(RevisionHumana.objects.count(), 1)
        self.assertTrue(BorradorRevisionHumana.objects.filter(valoracion=self.manual).exists())

    def test_lote_atomico_si_cambia_una_fuente(self):
        self.assertEqual(self.guardar().status_code, 200)
        self.assertEqual(self.guardar(self.manual, modo='MANUAL', valor='2').status_code, 200)
        tokens = [self.token(self.v), self.token(self.manual)]
        PreguntasService.registrar_vacios(self.actor, self.ev.pk, self.manual.pk, ['¿Información nueva?'])
        self.lote(tokens)
        self.assertFalse(RevisionHumana.objects.exists())
        self.assertEqual(BorradorRevisionHumana.objects.count(), 2)
        self.v.refresh_from_db()
        self.assertIsNone(self.v.valor_confirmado)

    def test_lote_no_confirma_dos_veces_ni_incompletos(self):
        self.assertEqual(self.guardar().status_code, 200)
        token = self.token(self.v)
        self.lote([token, token])
        self.assertFalse(RevisionHumana.objects.exists())
        self.assertEqual(self.guardar(self.manual, modo='MANUAL', valor='').status_code, 200)
        self.lote([token, self.token(self.manual)])
        self.assertFalse(RevisionHumana.objects.exists())

    def test_lote_completo_preserva_modo_y_propuesta(self):
        self.assertEqual(self.guardar(modo='MODIFICAR', valor='3').status_code, 200)
        self.assertEqual(self.guardar(self.manual, modo='MANUAL', valor='2').status_code, 200)
        res = self.lote([self.token(self.v), self.token(self.manual)])
        self.assertEqual(res.context['revisadas'], 2)
        self.assertContains(res, 'VALIDACIÓN MANUAL')
        self.assertFalse(BorradorRevisionHumana.objects.exists())
        self.assertEqual(set(RevisionHumana.objects.values_list('modo', flat=True)), {'MODIFICAR', 'MANUAL'})
        self.v.refresh_from_db()
        self.assertEqual((self.v.valor_ia, self.v.valor_confirmado), (4, 3))

    def test_filtros_y_borrador_obsoleto_visibles(self):
        self.assertEqual(self.guardar().status_code, 200)
        ValoracionSubfactor.objects.filter(pk=self.v.pk).update(justificacion_ia='Cambio posterior.')
        res = self.get(evaluacion=self.ev.pk, valoracion=self.v.pk)
        self.assertContains(res, 'hu11-buscar')
        self.assertContains(res, 'hu11-filtro')
        self.assertContains(res, 'Las fuentes cambiaron desde el último borrador')
        self.assertContains(res, 'Revisión masiva de borradores')

    def test_reapertura_explicita_muestra_historial_y_bloquea_calculo(self):
        self.client.post(self.url, self.payload())
        self.client.post(self.url, self.payload(self.manual, modo='MANUAL', valor='2'))
        res = self.get(evaluacion=self.ev.pk, valoracion=self.v.pk)
        self.assertContains(res, 'Calcular y guardar PM y FODA')
        self.assertContains(res, 'Reabrir valoración')
        datos = self.payload(accion='reabrir_hu11', motivo='Nueva evidencia.', confirmar_reapertura='1')
        res = self.client.post(self.url, datos, follow=True)
        self.assertContains(res, 'Valoración reabierta')
        self.assertContains(res, 'Nueva evidencia.')
        self.assertContains(res, 'Cálculo no disponible')
        self.assertContains(res, 'Comparación con la última decisión invalidada')
        self.assertEqual(res.context['revisadas'], 1)
        self.assertEqual(RevisionHumana.objects.count(), 2)
        self.assertTrue(res.context['seleccion']['editable'])

    def test_reapertura_sin_confirmacion_o_csrf_no_cambia_decision(self):
        self.client.post(self.url, self.payload())
        datos = self.payload(accion='reabrir_hu11', motivo='Motivo')
        res = self.client.post(self.url, datos, follow=True)
        self.assertContains(res, 'Confirme expresamente la reapertura')
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.actor)
        self.assertEqual(protegido.post(self.url, dict(datos, confirmar_reapertura='1')).status_code, 403)
        self.v.refresh_from_db()
        self.assertEqual(self.v.valor_confirmado, 4)

    def test_reapertura_no_visible_para_evaluacion_cerrada(self):
        self.client.post(self.url, self.payload())
        Evaluacion.objects.filter(pk=self.ev.pk).update(estado='FINALIZADA')
        res = self.get(evaluacion=self.ev.pk, valoracion=self.v.pk)
        self.assertNotContains(res, 'Confirmar reapertura')

    def test_borrador_obsoleto_excluido_del_lote_sin_perder_texto(self):
        self.assertEqual(self.guardar().status_code, 200)
        self.assertEqual(self.guardar(self.manual, modo='MANUAL', valor='2').status_code, 200)
        ValoracionSubfactor.objects.filter(pk=self.v.pk).update(justificacion_ia='Nueva propuesta posterior.')
        res = self.get(evaluacion=self.ev.pk, valoracion=self.v.pk)
        self.assertContains(res, 'Borradores desactualizados: 1')
        self.assertEqual([item['v'].pk for item in res.context['borradores']], [self.manual.pk])
        self.assertEqual(res.context['cantidad_borradores'], 2)
        self.assertEqual(BorradorRevisionHumana.objects.get(valoracion=self.v).justificacion, 'Revisión de prueba.')
        res = self.client.post(self.url, self.payload(accion='guardar_borrador_hu11', version_borrador='1'))
        self.assertEqual(res.status_code, 200)
        res = self.get(evaluacion=self.ev.pk, valoracion=self.v.pk)
        self.assertEqual(len(res.context['borradores']), 2)
        self.assertEqual(res.context['borradores_obsoletos'], [])

    def test_pantalla_privada_no_se_almacena_en_cache(self):
        res = self.get(evaluacion=self.ev.pk, valoracion=self.v.pk)
        self.assertEqual(res.status_code, 200)
        self.assertIn('no-store', res['Cache-Control'])
        self.assertIn('private', res['Cache-Control'])

    def test_reapertura_anula_token_antiguo_de_lote(self):
        self.assertEqual(self.guardar().status_code, 200)
        token = self.token(self.v)
        self.lote([token])
        version = RevisionHumanaService.obtener(self.actor, self.ev.pk, self.v.pk)['version']
        RevisionHumanaService.reabrir(self.actor, self.ev.pk, self.v.pk, 'Revisión posterior', version)
        self.assertEqual(self.guardar().status_code, 200)
        self.assertNotEqual(token, self.token(self.v))
        self.lote([token])
        self.v.refresh_from_db()
        self.assertIsNone(self.v.valor_confirmado)
        self.assertEqual(RevisionHumana.objects.count(), 1)
        self.assertTrue(BorradorRevisionHumana.objects.filter(valoracion=self.v).exists())
