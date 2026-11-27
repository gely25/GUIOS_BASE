from datetime import date
from unittest.mock import patch

from django.test import TestCase

from apps.application.services.ai import AIService
from apps.application.services.lotes_hu09 import LotesHU09Service
from apps.application.services.preparacion_hu10 import PreparacionHU10Service
from apps.application.services.preguntas import PreguntasService
from apps.data.management.commands.cargar_piloto_hu09_hu10 import CORREO_DEMO, VERSION, preparar
from apps.data.models import CatalogoVersion, LoteHU09, Organizacion, Usuario, ValoracionSubfactor


class PilotoHU09HU10Tests(TestCase):
    def test_preparacion_idempotente_y_flujo_de_dos_subfactores(self):
        catalogo_activo = CatalogoVersion.objects.filter(estado=CatalogoVersion.ACTIVO).first()
        if not catalogo_activo:
            catalogo_activo = CatalogoVersion.objects.create(version='catalogo-activo', fecha_creacion=date.today())
        actor = Usuario.objects.create_user(
            CORREO_DEMO, 'ficticia', nombre='Decisor demo',
            organizacion=Organizacion.objects.create(nombre='Demo'),
        )
        clave_original = actor.password
        primero = preparar()
        repetido = preparar()
        eid = primero['evaluacion_id']
        self.assertEqual(repetido['evaluacion_id'], eid)
        self.assertFalse(repetido['creada'])
        self.assertEqual(primero['decisor_id'], actor.pk)
        self.assertEqual(len(primero['subfactores_elegibles']), 2)
        self.assertFalse(LoteHU09.objects.exists())
        actor.refresh_from_db()
        self.assertEqual(actor.password, clave_original)
        catalogo_activo.refresh_from_db()
        self.assertEqual(catalogo_activo.estado, CatalogoVersion.ACTIVO)
        self.assertEqual(CatalogoVersion.objects.get(version=VERSION).estado, CatalogoVersion.HISTORICO)

        def suficiencia(entrada):
            referencia, = [fuente['id'] for fuente in entrada['fuentes']]
            self.assertTrue(referencia.startswith('R:'))
            return {'estado': 'SUFICIENTE', 'justificacion': 'Declaración clara.',
                    'referencias': [referencia], 'preguntas': []}

        lote = LotesHU09Service.encolar(actor, eid)
        self.assertEqual(lote.objetivos, primero['subfactores_elegibles'])
        with patch.object(PreguntasService, '_contexto', wraps=PreguntasService._contexto) as contexto:
            procesado = LotesHU09Service.procesar(LotesHU09Service.tomar(), suficiencia, 'mock')
        self.assertCountEqual([llamada.args[1] for llamada in contexto.call_args_list],
                              [vid for vid in lote.objetivos for _ in range(2)])
        self.assertEqual(procesado.estado, 'FINALIZADO')
        filas = PreparacionHU10Service.obtener(actor, eid)['subfactores']
        self.assertEqual([f['estado'] for f in filas], ['PROPUESTA_HABILITADA'] * 2)

        def valorar(entrada):
            valor = 1 if 'LDAP' in entrada['subfactor'] else 4
            return {'valor_preliminar': valor, 'justificacion': 'Declaración del caso sintético.',
                    'referencias': [entrada['fuentes'][0]['id']]}

        with patch.object(PreguntasService, '_contexto', wraps=PreguntasService._contexto) as contexto:
            self.assertEqual(AIService.generar_propuestas_pendientes(actor, eid, valorar)['generadas'], 2)
        alcances = [llamada.args[1] for llamada in contexto.call_args_list]
        self.assertCountEqual(alcances, [None, *(vid for vid in lote.objetivos for _ in range(2))])
        self.assertEqual(set(ValoracionSubfactor.objects.filter(evaluacion_factor__evaluacion_id=eid)
                             .values_list('valor_ia', 'valor_confirmado')), {(1, None), (4, None)})
