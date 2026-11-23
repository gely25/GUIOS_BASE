"""Datos de ejemplo compartidos por las pruebas del informe (HU14)."""

from decimal import Decimal

from django.utils import timezone

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
    ResultadoEvaluacion,
    Software,
    Subfactor,
    Usuario,
    ValoracionSubfactor,
)


def crear_decisor(correo="decisor@guios.test", nombre="Dario Decisor"):
    organizacion, _ = Organizacion.objects.get_or_create(nombre="Universidad de Prueba")
    return Usuario.objects.create_user(
        correo=correo, password="Clave-Segura-123", nombre=nombre,
        rol=Usuario.DECISOR, organizacion=organizacion)


def crear_evaluacion(decisor, con_resultado=True, software="LibreOffice"):
    """Evaluación con 2 factores relevantes, 1 no relevante, 1 valoración con evidencia y 1 documento."""
    CatalogoVersion.objects.filter(estado='ACTIVO').update(estado='HISTORICO')
    dimension, _ = Dimension.objects.get_or_create(nombre="Tecnológica")
    compat = Factor.objects.create(dimension=dimension, nombre="Compatibilidad", alcance="externo")
    forma = Factor.objects.create(dimension=dimension, nombre="Formación", alcance="interno")
    oculto = Factor.objects.create(dimension=dimension, nombre="Soporte", alcance="ambos")
    catalogo, _ = CatalogoVersion.objects.get_or_create(
        version="2021", defaults={"fecha_creacion": timezone.now().date()})

    evaluacion = Evaluacion.objects.create(
        organizacion=decisor.organizacion, usuario=decisor, catalogo=catalogo, estado="FINALIZADA",
        software=Software.objects.create(nombre=software, version="24.8", proveedor="TDF"),
        fecha_fin=timezone.now())

    ef_compat = EvaluacionFactor.objects.create(
        evaluacion=evaluacion, factor=compat, importancia_sugerida=3, importancia_decisor=4,
        importancia_relativa=4, ponderacion_media=Decimal("3.50"), clasificacion_foda="Oportunidad")
    EvaluacionFactor.objects.create(
        evaluacion=evaluacion, factor=forma, importancia_sugerida=2, importancia_decisor=2,
        importancia_relativa=2, ponderacion_media=Decimal("2.00"), clasificacion_foda="Debilidad")
    EvaluacionFactor.objects.create(evaluacion=evaluacion, factor=oculto, relevante=False,
                                    ponderacion_media=Decimal("1.00"), clasificacion_foda="Amenaza")

    subfactor = Subfactor.objects.create(factor=compat, descripcion="Abre y guarda formatos de Office")
    valoracion = ValoracionSubfactor.objects.create(
        evaluacion_factor=ef_compat, subfactor=subfactor, valor_ia=3, valor_confirmado=4,
        justificacion_ia="La guía lo declara.", justificacion_decisor="Lo comprobé en la prueba piloto.",
        estado_validacion="CONFIRMADA")
    documento = Documento.objects.create(
        evaluacion=evaluacion, usuario=decisor, nombre="guia.pdf", tipo="PDF", version="1.0",
        hash_sha256="a" * 64, ubicacion="demo/guia.pdf")
    fragmento = FragmentoDocumento.objects.create(
        documento=documento, pagina=7, seccion="Formatos",
        contenido="Soporta   ODF y\nformatos de Microsoft Office.")
    Evidencia.objects.create(valoracion=valoracion, fragmento=fragmento, relevancia=Decimal("0.90"))

    if con_resultado:
        ResultadoEvaluacion.objects.create(
            evaluacion=evaluacion, version_regla="1.0",
            recomendacion="Recomendación B: es posible adoptar, con matices.",
            explicacion="Hay una debilidad en Formación.\nSe sugiere reforzar la capacitación.")
    return evaluacion
