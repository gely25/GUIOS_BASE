"""Prepara un piloto sintético sin invocar IA ni iniciar lotes."""
import json
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.urls import reverse

from apps.application.services.lotes_hu09 import LotesHU09Service
from apps.application.services.preguntas import PreguntasService
from apps.data.models import (CatalogoVersion, Dimension, Evaluacion, EvaluacionFactor, Factor,
                              Software, Subfactor, Usuario, ValoracionSubfactor)
from benchmarks.local_ia import verificar_base_migrada


CORREO_DEMO = 'decisor.demo@guios.local'
VERSION = 'PILOTO-SINTETICO-HU09-HU10-v1'
CASOS = (
    ('Compatibilidad ODF', 'Exportación nativa de documentos de texto en ODT según ODF 1.3.',
     'En este caso ficticio comprobé que la aplicación exporta documentos de texto de forma nativa a ODT '
     'en ODF 1.3. Exporté tres documentos, validé su formato ODF 1.3 y volví a abrirlos correctamente '
     'sin usar conversores ni complementos.'),
    ('Autenticación LDAPv3', 'Autenticación de usuarios contra un directorio LDAPv3.',
     'En este caso ficticio verifiqué el acceso de los usuarios: la aplicación solo admite cuentas locales '
     'y no implementa autenticación LDAPv3. El manual de administración confirma la ausencia de LDAPv3 '
     'y la prueba de integración no pudo autenticar usuarios del directorio.'),
)


@transaction.atomic
def preparar():
    # El bloqueo del decisor hace idempotente el alta incluso si se invoca en dos terminales.
    actor = Usuario.objects.select_for_update().filter(correo=CORREO_DEMO, activo=True, rol=Usuario.DECISOR).first()
    if not actor or not actor.organizacion_id or not actor.has_usable_password():
        raise CommandError('Se requiere el decisor demo activo con organización y acceso existente.')
    catalogo, _ = CatalogoVersion.objects.get_or_create(
        version=VERSION, defaults={'fecha_creacion': date.today(), 'estado': CatalogoVersion.HISTORICO},
    )
    if catalogo.estado != CatalogoVersion.HISTORICO:
        raise CommandError('El catálogo del piloto debe estar aislado como histórico.')
    evaluacion = Evaluacion.objects.filter(usuario=actor, catalogo=catalogo).order_by('pk').first()
    creada = evaluacion is None
    if creada:
        evaluacion = Evaluacion.objects.create(
            organizacion_id=actor.organizacion_id, usuario=actor, catalogo=catalogo,
            software=Software.objects.create(nombre='Piloto sintético HU09/HU10'),
        )
        dimension, _ = Dimension.objects.get_or_create(nombre='PILOTO SINTÉTICO HU09/HU10 · Técnica')
        for nombre, criterio, respuesta in CASOS:
            factor, _ = Factor.objects.get_or_create(
                dimension=dimension, nombre=nombre, defaults={'alcance': Factor.EXTERNO, 'activo': False},
            )
            subfactor, _ = Subfactor.objects.get_or_create(
                factor=factor, descripcion=criterio, defaults={'activo': False},
            )
            if factor.activo or subfactor.activo:
                raise CommandError('Los elementos del piloto no deben alterar el catálogo activo.')
            vinculo = EvaluacionFactor.objects.create(
                evaluacion=evaluacion, factor=factor, importancia_relativa=3,
            )
            valoracion = ValoracionSubfactor.objects.create(evaluacion_factor=vinculo, subfactor=subfactor)
            pregunta, = PreguntasService.registrar_vacios(
                actor, evaluacion.pk, valoracion.pk, [f'¿Qué información verificable existe sobre {criterio[:-1]}?'],
            )
            PreguntasService.responder(actor, evaluacion.pk, pregunta.pk, respuesta)
    objetivos = LotesHU09Service.objetivos(actor, evaluacion.pk)
    if creada and len(objetivos) != 2:
        raise CommandError('La preparación no produjo exactamente dos subfactores elegibles.')
    return {
        'creada': creada, 'evaluacion_id': evaluacion.pk, 'decisor_id': actor.pk, 'acceso_demo': CORREO_DEMO,
        'subfactores_elegibles': objetivos,
        'ruta': f'{reverse("presentation:decisor-revision-valoraciones")}?evaluacion={evaluacion.pk}',
    }


class Command(BaseCommand):
    help = 'Prepara dos subfactores sintéticos para HU09/HU10 solo en guios_pro_ai_dev.'

    def handle(self, *args, **options):
        verificar_base_migrada()
        self.stdout.write(json.dumps(preparar(), ensure_ascii=False))
