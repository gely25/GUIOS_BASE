"""Caso de prueba HU09; no importa ni genera evidencia real."""
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.data.models import (CatalogoVersion, Dimension, Documento, Evaluacion, EvaluacionFactor,
                              Evidencia, Factor, FragmentoDocumento, Software, Subfactor, Usuario,
                              ValoracionSubfactor)


class Command(BaseCommand):
    help = 'Crea una evaluación ficticia HU09 para el decisor demo; solo en bases _dev.'

    @transaction.atomic
    def handle(self, *args, **options):
        if not str(connection.settings_dict['NAME']).endswith('_dev'):
            raise CommandError('Solo se permite ejecutar en bases de desarrollo _dev.')
        actor = Usuario.objects.filter(correo='decisor.demo@guios.local', activo=True, rol=Usuario.DECISOR).first()
        if not actor or not actor.organizacion_id:
            raise CommandError('Se necesita el decisor demo activo con organización.')
        catalogo, _ = CatalogoVersion.objects.get_or_create(version='DEMO-HU09', defaults={'fecha_creacion': date.today(), 'estado': 'HISTORICO'})
        software, _ = Software.objects.get_or_create(nombre='DEMO HU09 (datos ficticios)')
        evaluacion, creada = Evaluacion.objects.get_or_create(usuario=actor, organizacion=actor.organizacion, software=software, catalogo=catalogo)
        if not creada:
            self.stdout.write(f'Caso existente, sin modificar: evaluación #{evaluacion.pk}.')
            return
        dimension, _ = Dimension.objects.get_or_create(nombre='DEMO HU09 · Tecnológica')
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
            if nombre == 'Compatibilidad':
                doc = Documento.objects.create(evaluacion=evaluacion, usuario=actor, nombre='DEMO HU09 · evidencia ficticia', tipo='TXT', ubicacion='demo://hu09')
                fragmento = FragmentoDocumento.objects.create(documento=doc, pagina=1, contenido='DATO FICTICIO DE PRUEBA: se menciona ODF, sin indicar las versiones compatibles.')
                Evidencia.objects.create(valoracion=v, fragmento=fragmento, referencia='Ejemplo sintético; no corresponde a un documento real.')
        self.stdout.write(self.style.SUCCESS(f'Caso ficticio creado: evaluación #{evaluacion.pk}.'))
