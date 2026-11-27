"""
Servicio de Aplicación: AIService.

Capa: application. Valoraciones preliminares con evidencia verificable apoyadas en IA (HU10).
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.data.models import ValoracionSubfactor
from apps.external_services.ai_errors import AnalisisNoDisponible
from .preguntas import PreguntasService
from .preparacion_hu10 import PreparacionHU10Service
from .tareas_ia import en_orden, solicitar

ESCALA_HU10 = {
    1: 'No cumple',
    2: 'Desconozco / No sé',
    3: 'Cumple parcialmente',
    4: 'Cumple',
}


def formatear_justificacion_hu10(justificacion: str, referencias: list[str]) -> str:
    texto = (justificacion or '').strip()
    refs_limpias = [r.strip() for r in referencias if isinstance(r, str) and r.strip()]
    if not refs_limpias:
        return texto
    etiqueta_refs = f"Fuentes citadas: {', '.join(refs_limpias)}"
    if etiqueta_refs in texto:
        return texto
    return f"{texto}\n{etiqueta_refs}"


class AIService:
    """Generación de propuestas preliminares de valoración (1 a 4) con trazabilidad de fuentes (HU10)."""

    @staticmethod
    def _construir_entrada(fila: dict) -> dict:
        fuentes_ia = []
        for fuente in fila['fuentes']:
            item = {
                'id': fuente['id'],
                'origen': fuente['origen'],
                'contenido': fuente['contenido'],
            }
            if fuente.get('documento'):
                item['documento'] = fuente['documento']
            if fuente.get('pagina'):
                item['pagina'] = fuente['pagina']
            if fuente.get('referencia'):
                item['referencia'] = fuente['referencia']
            if fuente.get('pregunta'):
                item['pregunta'] = fuente['pregunta']
            fuentes_ia.append(item)

        return {
            'evaluacion_id': fila.get('evaluacion_id'),
            'valoracion_id': fila['valoracion_id'],
            'dimension': fila['dimension'],
            'factor': fila['factor'],
            'subfactor': fila['subfactor'],
            'importancia_relativa': fila['ir'],
            'suficiencia': fila['suficiencia'],
            'fuentes': fuentes_ia,
            'sin_informacion': fila['sin_informacion'],
        }

    @staticmethod
    def _validar_respuesta_modelo(respuesta, ids_validos: set[str]) -> tuple[int, str, list[str]]:
        if not isinstance(respuesta, dict) or set(respuesta.keys()) != {'valor_preliminar', 'justificacion', 'referencias'}:
            raise AnalisisNoDisponible('La IA devolvió una propuesta de valoración con formato inválido.')

        valor = respuesta.get('valor_preliminar')
        if type(valor) is not int or valor not in (1, 2, 3, 4):
            raise AnalisisNoDisponible('La puntuación preliminar debe ser un entero entre 1 y 4.')

        justificacion = respuesta.get('justificacion')
        if not isinstance(justificacion, str) or not justificacion.strip() or len(justificacion.strip()) > 1500:
            raise AnalisisNoDisponible('La justificación preliminar del modelo es inválida.')

        referencias_raw = respuesta.get('referencias')
        if not isinstance(referencias_raw, list) or not referencias_raw:
            raise AnalisisNoDisponible('La propuesta preliminar debe citar al menos una fuente verificable.')

        referencias = []
        for ref in referencias_raw:
            if not isinstance(ref, str) or ref.strip() not in ids_validos:
                raise AnalisisNoDisponible('El modelo citó una fuente inexistente o no permitida en el contexto.')
            if ref.strip() not in referencias:
                referencias.append(ref.strip())

        return valor, justificacion.strip(), referencias

    @classmethod
    def generar_propuesta_preliminar(cls, actor, evaluacion_id: int, valoracion_id: int, proveedor,
                                    *, solo_pendiente=False) -> dict | None:
        """
        Genera y persiste la propuesta preliminar (1..4) para un subfactor habilitado (PROPUESTA_HABILITADA),
        conservando la propuesta original para revisión humana en HU11.
        """
        preparacion = PreparacionHU10Service.obtener(actor, evaluacion_id, valoracion_id)
        fila = next(iter(preparacion['subfactores']), None)
        if fila is None:
            raise ValidationError('Subfactor no disponible en esta evaluación.')
        if fila['estado'] != 'PROPUESTA_HABILITADA':
            raise ValidationError(
                'El subfactor aún no está habilitado para valoración preliminar (requiere suficiencia propuesta y fuentes vigentes).'
            )
        if not fila['fuentes']:
            raise ValidationError('No existen fuentes verificables vinculadas para sustentar la propuesta.')

        ids_validos = {f['id'] for f in fila['fuentes']}
        entrada = cls._construir_entrada(dict(fila, evaluacion_id=evaluacion_id))
        anterior = ValoracionSubfactor.objects.filter(pk=valoracion_id).values_list(
            'valor_ia', 'justificacion_ia',
        ).first()
        if anterior is None:
            raise ValidationError('Subfactor no disponible en esta evaluación.')
        if solo_pendiente and anterior[0] in ESCALA_HU10:
            return None

        # Invocar al proveedor fuera de la transacción de escritura.
        salida_modelo = solicitar(
            proveedor, entrada, ['evaluacion', evaluacion_id, valoracion_id, fila['huella']], actor.pk,
        )
        valor, justificacion, referencias = cls._validar_respuesta_modelo(salida_modelo, ids_validos)
        justificacion_persistida = formatear_justificacion_hu10(justificacion, referencias)

        with transaction.atomic():
            evaluacion = PreguntasService._evaluacion(actor, evaluacion_id, escritura=True)
            valoracion = PreguntasService._valoracion_editable(evaluacion, valoracion_id)
            vigente = PreparacionHU10Service._validar_vigencia(evaluacion, valoracion.pk, fila['huella'])
            if cls._construir_entrada(dict(vigente, evaluacion_id=evaluacion_id)) != entrada:
                raise ValidationError('La suficiencia o las fuentes cambiaron durante el análisis. Repita la operación.')

            actual = (valoracion.valor_ia, valoracion.justificacion_ia)
            propuesta = (valor, justificacion_persistida)
            if solo_pendiente and actual[0] in ESCALA_HU10:
                return None
            if actual != propuesta:
                if actual != anterior:
                    raise ValidationError('La propuesta cambió durante el análisis. Revise la valoración vigente.')
                valoracion.valor_ia, valoracion.justificacion_ia = propuesta
                valoracion.save(update_fields=['valor_ia', 'justificacion_ia'])

        return {
            'valoracion_id': valoracion.pk,
            'valor_ia': valor,
            'etiqueta': ESCALA_HU10[valor],
            'justificacion': justificacion,
            'justificacion_ia': justificacion_persistida,
            'referencias': referencias,
        }

    @classmethod
    def generar_propuestas_pendientes(cls, actor, evaluacion_id: int, proveedor) -> dict:
        """Genera propuestas preliminares para todos los subfactores habilitados que aún no tienen valor_ia."""
        preparacion = PreparacionHU10Service.obtener(actor, evaluacion_id)
        habilitados_ids = [
            f['valoracion_id']
            for f in preparacion['subfactores']
            if f['estado'] == 'PROPUESTA_HABILITADA'
        ]
        existentes = set(
            ValoracionSubfactor.objects.filter(
                valoracion_id__in=habilitados_ids,
                valor_ia__in=(1, 2, 3, 4),
            ).values_list('valoracion_id', flat=True)
        )
        pendientes = [vid for vid in habilitados_ids if vid not in existentes]

        generadas = 0
        errores = []
        def generar(vid):
            try:
                propuesta = cls.generar_propuesta_preliminar(actor, evaluacion_id, vid, proveedor, solo_pendiente=True)
            except (ValidationError, AnalisisNoDisponible) as exc:
                return False, ' '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
            return propuesta is not None, None

        for generada, error in en_orden(proveedor, generar, pendientes):
            generadas += generada
            if error is not None:
                errores.append(error)

        return {
            'total_habilitados': len(habilitados_ids),
            'pendientes': len(pendientes),
            'generadas': generadas,
            'errores': errores,
        }
