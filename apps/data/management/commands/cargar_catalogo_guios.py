"""
Carga el catálogo GUIOS 2021 (3 dimensiones, 18 factores, 61 subfactores) como versión `v1-2021`.

Uso: python manage.py cargar_catalogo_guios

Es repetible: no duplica nada si se corre otra vez. Lee `apps/data/semillas/guios_2021/`.
IL e IS se recalculan con las reglas de GUIOS (no se importan).
Si ya hay otra versión ACTIVA, `v1-2021` se guarda como HISTORICO.
"""

import csv
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.business_rules.rules_engine import EntradaFactor, recalcular_indicadores
from apps.data.models import CatalogoVersion, Dimension, Factor, IndicadorFactor, Subfactor

SEMILLAS = Path(__file__).resolve().parents[2] / 'semillas' / 'guios_2021'
VERSION_INICIAL = 'v1-2021'


def leer_tsv(nombre):
    with open(SEMILLAS / nombre, encoding='utf-8', newline='') as archivo:
        return [fila for fila in csv.DictReader(archivo, delimiter='\t') if any(fila.values())]


def leer_semillas():
    """Devuelve [(dimension, factor, alcance, ie, tc_2021, [subfactores])] en el orden del archivo."""
    factores = {f['Factor']: f for f in leer_tsv('factores.tsv')}
    orden, subfactores, dimension_de = [], {}, {}
    for fila in leer_tsv('subfactores.tsv'):
        nombre = fila['Factor']
        if nombre not in subfactores:
            orden.append(nombre)
            subfactores[nombre] = []
            dimension_de[nombre] = fila['Dimensión']
        subfactores[nombre].append(fila['Subfactor'].strip())

    if set(orden) != set(factores):
        raise CommandError('factores.tsv y subfactores.tsv no tienen los mismos factores.')
    return [
        (dimension_de[n], n, factores[n]['Alcance'], int(factores[n]['IE']),
         int(factores[n]['TC_2021']), subfactores[n])
        for n in orden
    ]


class Command(BaseCommand):
    help = 'Carga el catálogo GUIOS 2021 (factores, subfactores e indicadores) como versión v1-2021.'

    @transaction.atomic
    def handle(self, *args, **opciones):
        datos = leer_semillas()

        factores = []
        for dimension, nombre, alcance, ie, tc, textos in datos:
            dim, _ = Dimension.objects.get_or_create(nombre=dimension)
            factor, _ = Factor.objects.get_or_create(
                dimension=dim, nombre=nombre, defaults={'alcance': alcance})
            for texto in textos:
                Subfactor.objects.get_or_create(factor=factor, descripcion=texto)
            factores.append((factor, len(textos), ie, tc))

        version = CatalogoVersion.objects.filter(version=VERSION_INICIAL).first()
        if version is None:
            hay_activa = CatalogoVersion.objects.filter(estado=CatalogoVersion.ACTIVO).exists()
            version = CatalogoVersion.objects.create(
                version=VERSION_INICIAL, fecha_creacion=date(2021, 1, 1),
                estado=CatalogoVersion.HISTORICO if hay_activa else CatalogoVersion.ACTIVO)

        _, calculados = recalcular_indicadores(
            [EntradaFactor(clave=f.pk, ns=ns, tc=tc, ie=ie) for f, ns, ie, tc in factores])
        for factor, ns, ie, tc in factores:
            c = calculados[factor.pk]
            IndicadorFactor.objects.update_or_create(
                catalogo=version, factor=factor,
                defaults={
                    'numero_subfactores': ns, 'total_citas_base': tc, 'total_citas': tc,
                    'relacion_ri': c.relacion_ri, 'importancia_experto': ie,
                    'importancia_literatura': c.il, 'importancia_sugerida': c.is_,
                })

        if opciones['verbosity']:
            self.stdout.write(self.style.SUCCESS(
                f'[OK] Catálogo {version.version} ({version.get_estado_display()}): '
                f'{len(factores)} factores, {sum(ns for _, ns, _, _ in factores)} subfactores.'))
