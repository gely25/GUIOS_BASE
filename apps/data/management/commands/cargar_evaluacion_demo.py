"""
Crea una evaluación de demostración CON resultado para ver las pantallas de Resultados e
Informe (HU14) en desarrollo, mientras HU11-HU13 no generan resultados reales.

Pertenece al decisor de demostración (`decisor.demo@guios.local`), así que antes hay que correr
`cargar_datos_demo` y `cargar_catalogo_demo`. Es repetible: reemplaza la evaluación demo anterior.
Solo corre sobre una base cuyo nombre termine en `_dev`.

Uso:  python manage.py cargar_evaluacion_demo
"""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.data.models import (
    CatalogoVersion,
    Documento,
    Evaluacion,
    EvaluacionFactor,
    Evidencia,
    Factor,
    FragmentoDocumento,
    ResultadoEvaluacion,
    Software,
    Subfactor,
    Usuario,
    ValoracionSubfactor,
)

CORREO_DECISOR = 'decisor.demo@guios.local'
SOFTWARE_DEMO = 'LibreOffice (evaluación demo)'
# Cuántos factores del catálogo se cargan con valoraciones y evidencia de ejemplo.
FACTORES_CON_DETALLE = 3


def _foda(pm, alcance):
    alta = pm >= 3
    if alcance == 'interno':
        return 'Fortaleza' if alta else 'Debilidad'
    return 'Oportunidad' if alta else 'Amenaza'


class Command(BaseCommand):
    help = 'Crea una evaluación de demostración con resultado para el decisor demo.'

    @transaction.atomic
    def handle(self, *args, **opciones):
        base = connection.settings_dict['NAME']
        if not base.endswith('_dev'):
            raise CommandError(
                f'Por seguridad solo corre en una base de desarrollo (nombre termina en _dev); '
                f'la actual es "{base}".')
        try:
            decisor = Usuario.objects.get(correo=CORREO_DECISOR)
        except Usuario.DoesNotExist:
            raise CommandError('Falta el decisor demo: corre antes `python manage.py cargar_datos_demo`.')
        catalogo = CatalogoVersion.objects.filter(estado='ACTIVO').order_by('-fecha_creacion').first()
        factores = list(Factor.objects.filter(activo=True).order_by('dimension_id', 'factor_id'))
        if catalogo is None or not factores:
            raise CommandError('Falta el catálogo: corre antes `python manage.py cargar_catalogo_demo`.')

        anteriores = Evaluacion.objects.filter(usuario=decisor, software__nombre=SOFTWARE_DEMO)
        # La evidencia protege a su fragmento: se borra primero para poder reemplazar la evaluación.
        Evidencia.objects.filter(valoracion__evaluacion_factor__evaluacion__in=anteriores).delete()
        anteriores.delete()

        software, _ = Software.objects.get_or_create(
            nombre=SOFTWARE_DEMO, defaults={'version': '24.8', 'proveedor': 'The Document Foundation'})
        evaluacion = Evaluacion.objects.create(
            organizacion=decisor.organizacion, usuario=decisor, software=software,
            catalogo=catalogo, estado='FINALIZADA', fecha_fin=timezone.now())

        documento = Documento.objects.create(
            evaluacion=evaluacion, usuario=decisor, nombre='guia-instalacion-libreoffice.pdf',
            tipo='PDF', version='1.0', hash_sha256='0' * 64, ubicacion='demo/guia-instalacion-libreoffice.pdf')
        fragmento = FragmentoDocumento.objects.create(
            documento=documento, pagina=12, seccion='Compatibilidad de formatos',
            contenido='LibreOffice abre y guarda los formatos de Microsoft Office y soporta ODF de forma nativa.')

        pms = [Decimal('3.50'), Decimal('2.25'), Decimal('3.00'), Decimal('1.75')]
        for posicion, factor in enumerate(factores):
            pm = pms[posicion % len(pms)]
            ef = EvaluacionFactor.objects.create(
                evaluacion=evaluacion, factor=factor, importancia_sugerida=3,
                importancia_decisor=3, importancia_relativa=3, ponderacion_media=pm,
                clasificacion_foda=_foda(pm, 'externo' if factor.alcance == 'ambos' else factor.alcance))
            if posicion >= FACTORES_CON_DETALLE:
                continue
            subfactor, _ = Subfactor.objects.get_or_create(
                factor=factor, descripcion=f'Subfactor de demostración de {factor.nombre}')
            valoracion = ValoracionSubfactor.objects.create(
                evaluacion_factor=ef, subfactor=subfactor, valor_ia=3, valor_confirmado=3,
                justificacion_ia='La documentación describe soporte para los formatos requeridos.',
                justificacion_decisor='Confirmado tras revisar la guía.',
                estado_validacion='CONFIRMADA', validado_por=decisor, fecha_validacion=timezone.now())
            Evidencia.objects.create(
                valoracion=valoracion, fragmento=fragmento, relevancia=Decimal('0.92'),
                justificacion='El fragmento menciona de forma explícita los formatos soportados.')

        ResultadoEvaluacion.objects.create(
            evaluacion=evaluacion, version_regla='demo-1',
            recomendacion='Recomendación B: es posible adoptar, con matices.',
            explicacion=('Se detectaron debilidades y amenazas en factores de importancia opcional.\n'
                         'Se sugiere una segunda evaluación solo con los subfactores que no cumplen el mínimo.'))
        self.stdout.write(self.style.SUCCESS(
            f'Evaluación demo n.º {evaluacion.evaluacion_id} creada para {CORREO_DECISOR}. '
            f'Entra como decisor y abre Resultados o Informe.'))
