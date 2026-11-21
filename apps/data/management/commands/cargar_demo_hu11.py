"""Caso de prueba HU11 con propuestas ficticias; no invoca IA."""
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.data.models import (CatalogoVersion, Dimension, Documento, Evaluacion, EvaluacionFactor,
                              Evidencia, Factor, FragmentoDocumento, Software, Subfactor, Usuario,
                              ValoracionSubfactor)


class Command(BaseCommand):
    help = 'Crea una evaluación ficticia HU11 para el decisor demo; solo en bases _dev.'

    def add_arguments(self, parser):
        parser.add_argument("--variante", choices=["base", "borradores"], default="base")

    @transaction.atomic
    def handle(self, *args, **options):
        if not str(connection.settings_dict['NAME']).endswith('_dev'):
            raise CommandError('Solo se permite ejecutar en bases de desarrollo _dev.')
        actor = Usuario.objects.filter(correo='decisor.demo@guios.local', activo=True, rol=Usuario.DECISOR).first()
        if not actor or not actor.organizacion_id:
            raise CommandError('Se necesita el decisor demo activo con organización.')
        catalogo, _ = CatalogoVersion.objects.get_or_create(version='DEMO-HU11', defaults={'fecha_creacion': date.today(), 'estado': 'DEMO'})
        nombre = 'DEMO HU11 (datos ficticios)' if options['variante'] == 'base' else 'DEMO HU11 · Borradores (datos ficticios)'
        software, _ = Software.objects.get_or_create(nombre=nombre)
        evaluacion, creada = Evaluacion.objects.get_or_create(usuario=actor, organizacion=actor.organizacion, software=software, catalogo=catalogo)
        if not creada:
            self.stdout.write(f'Caso existente, sin modificar: evaluación #{evaluacion.pk}.')
            return
        dimension, _ = Dimension.objects.get_or_create(nombre='DEMO HU11 · Tecnológica')
        for nombre, texto, ir in [
            ('Compatibilidad', 'Formatos de archivo admitidos', 3),
            ('Seguridad', 'Procedimiento de actualizaciones de seguridad', 4),
            ('Interoperabilidad', 'Integración con sistemas institucionales', 3),
            ('Factor excluido', 'Requisito no relevante para esta evaluación', 1),
        ]:
            factor, _ = Factor.objects.get_or_create(dimension=dimension, nombre=nombre, defaults={'alcance': Factor.EXTERNO, 'activo': False})
            subfactor, _ = Subfactor.objects.get_or_create(factor=factor, descripcion=texto, defaults={'activo': False})
            ef = EvaluacionFactor.objects.create(evaluacion=evaluacion, factor=factor, importancia_relativa=ir, relevante=ir != 1)
            v = ValoracionSubfactor.objects.create(evaluacion_factor=ef, subfactor=subfactor)
            if nombre in ('Compatibilidad', 'Seguridad'):
                v.valor_ia = 4 if nombre == 'Compatibilidad' else 3
                v.justificacion_ia = 'PROPUESTA FICTICIA DE DEMOSTRACIÓN: no representa una ejecución de HU10.'
                v.save(update_fields=['valor_ia', 'justificacion_ia'])
            if nombre == 'Compatibilidad':
                doc = Documento.objects.create(evaluacion=evaluacion, usuario=actor, nombre='DEMO HU11 · evidencia ficticia', tipo='TXT', ubicacion='demo://hu11')
                fragmento = FragmentoDocumento.objects.create(documento=doc, pagina=1, contenido='DATO FICTICIO DE PRUEBA: se menciona ODF, sin indicar las versiones compatibles.')
                Evidencia.objects.create(valoracion=v, fragmento=fragmento, referencia='Ejemplo sintético; no corresponde a un documento real.')
        self.stdout.write(self.style.SUCCESS(f'Caso ficticio creado: evaluación #{evaluacion.pk}.'))
