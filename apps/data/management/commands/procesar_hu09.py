"""Trabajador independiente para la cola HU09 (una instancia local)."""
import time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from apps.application.services.lotes_hu09 import LotesHU09Service
from apps.data.models import LoteHU09
from apps.external_services.ollama_suficiencia import OllamaSuficiencia
from apps.external_services.ollama_embeddings import OllamaEmbeddings
from apps.external_services.ollama_preguntas import AnalisisNoDisponible


class Command(BaseCommand):
    help = 'Procesa lotes de suficiencia HU09; ejecutar en una terminal separada.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Procesa como máximo un lote y termina.')
        parser.add_argument('--recuperar', type=int, metavar='ID', help='Reencola un lote interrumpido. Detenga todos los workers primero.')

    def handle(self, *args, **options):
        if options['recuperar'] is not None:
            if not LoteHU09.objects.filter(pk=options['recuperar'], estado='EN_PROCESO').update(estado='EN_COLA'):
                raise CommandError('No existe un lote interrumpido con ese ID.')
            self.stdout.write('Lote reencolado; conserva los resultados parciales.')
            return
        try:
            proveedor = OllamaSuficiencia(settings.HU09_OLLAMA_MODEL)
            vectorizador = OllamaEmbeddings(settings.HU09_EMBEDDING_MODEL) if settings.HU09_EMBEDDING_MODEL else None
        except AnalisisNoDisponible as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write('Worker HU09 listo. Ctrl+C para detener.')
        try:
            while True:
                close_old_connections()
                lote = LotesHU09Service.tomar()
                if lote:
                    self.stdout.write(f'Procesando lote #{lote.pk}')
                    LotesHU09Service.procesar(lote, proveedor, settings.HU09_OLLAMA_MODEL, vectorizador)
                    self.stdout.write(f'Lote #{lote.pk} finalizado.')
                if options['once']:
                    return
                if not lote:
                    time.sleep(2)
        except KeyboardInterrupt:
            self.stdout.write('Worker detenido. Si había un lote en curso, recupérelo antes de reiniciar.')
