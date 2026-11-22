from datetime import date
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.application.services.ai import AIService
from apps.application.services.preguntas import PreguntasService
from apps.application.services.revision_humana import RevisionHumanaService
from apps.application.services.suficiencia import SuficienciaService
from apps.data.models import (
    CatalogoVersion,
    Dimension,
    Documento,
    Evaluacion,
    EvaluacionFactor,
    Evidencia,
    Factor,
    FragmentoDocumento,
    Organizacion,
    Software,
    Subfactor,
    Usuario,
    ValoracionSubfactor,
)
from apps.external_services.ollama_preguntas import AnalisisNoDisponible


@override_settings(
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    HU09_OLLAMA_MODEL='qwen2.5:1.5b',
    HU10_OLLAMA_MODEL='qwen2.5:1.5b',
    HU09_EMBEDDING_MODEL='',
)
class HU10ValoracionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre='Organización HU10')
        cls.actor = Usuario.objects.create_user('decisor@hu10.test', 'Clave-test-123', nombre='Jorge', organizacion=org)
        cat = CatalogoVersion.objects.create(version='v1-hu10', fecha_creacion=date.today())
        cls.ev = Evaluacion.objects.create(
            organizacion=org,
            usuario=cls.actor,
            software=Software.objects.create(nombre='LibreOffice'),
            catalogo=cat,
        )
        dim = Dimension.objects.create(nombre='Tecnológica')
        factor = Factor.objects.create(dimension=dim, nombre='Interoperabilidad', alcance=Factor.EXTERNO)
        ef = EvaluacionFactor.objects.create(evaluacion=cls.ev, factor=factor, importancia_relativa=4)
        subfactor = Subfactor.objects.create(factor=factor, descripcion='Soporte de formatos abiertos ODF')
        cls.val = ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=subfactor)

        doc = Documento.objects.create(
            evaluacion=cls.ev,
            usuario=cls.actor,
            nombre='manual_tecnico.pdf',
            tipo='PDF',
            ubicacion='evaluaciones/1/manual_tecnico.pdf',
        )
        frag = FragmentoDocumento.objects.create(
            documento=doc,
            pagina=4,
            contenido='Soporte nativo completo para ISO/IEC 26300 (ODF 1.3).',
        )
        cls.evidencia = Evidencia.objects.create(
            valoracion=cls.val,
            fragmento=frag,
            referencia='Página 4 · Sección 2.1',
        )

    def _habilitar_subfactor(self):
        SuficienciaService.analizar(
            self.actor,
            self.ev.pk,
            self.val.pk,
            lambda _: {
                'estado': 'SUFICIENTE',
                'justificacion': 'El documento acredita soporte nativo ODF 1.3.',
                'referencias': [f'E:{self.evidencia.pk}'],
                'preguntas': [],
            },
            'qwen2.5:1.5b',
        )

    def test_rechaza_subfactor_no_habilitado(self):
        with self.assertRaises(ValidationError):
            AIService.generar_propuesta_preliminar(
                self.actor,
                self.ev.pk,
                self.val.pk,
                lambda _: {'valor_preliminar': 4, 'justificacion': 'Cumple.', 'referencias': [f'E:{self.evidencia.pk}']},
            )

    def test_rechaza_referencia_inexistente_del_modelo(self):
        self._habilitar_subfactor()
        with self.assertRaises(AnalisisNoDisponible):
            AIService.generar_propuesta_preliminar(
                self.actor,
                self.ev.pk,
                self.val.pk,
                lambda _: {'valor_preliminar': 4, 'justificacion': 'Cumple.', 'referencias': ['E:99999']},
            )
        self.val.refresh_from_db()
        self.assertIsNone(self.val.valor_ia)

    def test_genera_y_guarda_propuesta_para_hu11(self):
        self._habilitar_subfactor()
        resultado = AIService.generar_propuesta_preliminar(
            self.actor,
            self.ev.pk,
            self.val.pk,
            lambda _: {
                'valor_preliminar': 4,
                'justificacion': 'Cumple plenamente con estándares abiertos ISO/IEC 26300.',
                'referencias': [f'E:{self.evidencia.pk}'],
            },
        )
        self.assertEqual(resultado['valor_ia'], 4)
        self.val.refresh_from_db()
        self.assertEqual(self.val.valor_ia, 4)
        self.assertIn(f'E:{self.evidencia.pk}', self.val.justificacion_ia)
        self.assertEqual(self.val.estado_validacion, ValoracionSubfactor.PENDIENTE)
        self.assertIsNone(self.val.valor_confirmado)

        # HU11 recibe la propuesta original intacta
        seleccion_hu11 = RevisionHumanaService.obtener(self.actor, self.ev.pk, self.val.pk)
        self.assertEqual(seleccion_hu11['valor_ia'], 4)
        self.assertIn('ISO/IEC 26300', seleccion_hu11['justificacion_ia'])

    def test_flujo_web_hu10_y_enlace_a_hu11(self):
        self._habilitar_subfactor()
        self.client.force_login(self.actor)
        url = reverse('presentation:decisor-revision-valoraciones')
        with patch('apps.presentation.views.preguntas.OllamaValoracion') as mock_ollama:
            mock_ollama.return_value.return_value = {
                'valor_preliminar': 3,
                'justificacion': 'Cumple parcialmente según la evidencia documental.',
                'referencias': [f'E:{self.evidencia.pk}'],
            }
            resp = self.client.post(url, {'evaluacion': self.ev.pk, 'valoracion': self.val.pk, 'accion': 'valorar_hu10'})
            self.assertEqual(resp.status_code, 302)

        pagina = self.client.get(url, {'evaluacion': self.ev.pk})
        self.assertContains(pagina, 'Propuesta preliminar IA (HU10): 3/4')
        self.assertContains(pagina, 'Ver en documento (comprobar ubicación)')

    def test_detecta_cambio_de_contexto_antes_de_guardar(self):
        self._habilitar_subfactor()

        def proveedor_que_muta_contexto(_):
            PreguntasService.registrar_vacios(self.actor, self.ev.pk, self.val.pk, ['¿Se soporta ODF 1.4?'])
            return {
                'valor_preliminar': 4,
                'justificacion': 'Cumple.',
                'referencias': [f'E:{self.evidencia.pk}'],
            }

        with self.assertRaises(ValidationError):
            AIService.generar_propuesta_preliminar(self.actor, self.ev.pk, self.val.pk, proveedor_que_muta_contexto)