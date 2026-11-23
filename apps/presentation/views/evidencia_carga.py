"""
Apoyo de la pantalla de Carga documental para vincular evidencia con menos trabajo manual.

Nada de aquí cambia la lógica existente de HU07/HU08:
- `cobertura` y `opciones_subfactores` solo leen.
- `sugerencias` usa `RetrievalService.buscar_por_subfactor` tal cual (solo lectura).
- `vincular_en_lote` crea evidencias con el mismo `get_or_create` de la acción individual
  «vincular_evidencia», pero para varias a la vez y solo con lo que la persona confirmó.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db.models import Count

from apps.data.models import Documento, Evidencia, FragmentoDocumento

TOP_POR_SUBFACTOR = 3
UMBRAL_SUGERENCIA = 0.10
UMBRAL_PRESELECCION = 0.30
EXTRACTO = 260
MAX_NOMBRES_SIN_EVIDENCIA = 10


def _conteo_evidencias(valoraciones):
    ids = [v.pk for v in valoraciones]
    filas = (Evidencia.objects.filter(valoracion_id__in=ids)
             .values('valoracion_id').annotate(n=Count('pk')))
    return {f['valoracion_id']: f['n'] for f in filas}


def opciones_subfactores(valoraciones):
    """Subfactores agrupados por factor, con cuántas evidencias tiene cada uno (sin evidencia primero)."""
    conteo = _conteo_evidencias(valoraciones)
    grupos, orden = {}, []
    for v in valoraciones:
        factor = v.evaluacion_factor.factor
        if factor.pk not in grupos:
            grupos[factor.pk] = {'factor': factor.nombre, 'items': []}
            orden.append(factor.pk)
        grupos[factor.pk]['items'].append({
            'valoracion_id': v.pk,
            'subfactor_id': v.subfactor_id,
            'descripcion': v.subfactor.descripcion,
            'n': conteo.get(v.pk, 0),
        })
    resultado = []
    for pk in orden:
        grupo = grupos[pk]
        grupo['items'].sort(key=lambda i: (i['n'] > 0, i['valoracion_id']))
        resultado.append(grupo)
    return resultado


def cobertura(evaluacion, valoraciones, estado_embeddings):
    """Resumen de lo cargado y de cuántos subfactores ya tienen evidencia."""
    conteo = _conteo_evidencias(valoraciones)
    sin = [v for v in valoraciones if conteo.get(v.pk, 0) == 0]
    total = len(valoraciones)
    con = total - len(sin)
    nombres = [f'{v.evaluacion_factor.factor.nombre}: {v.subfactor.descripcion}' for v in sin]
    return {
        'documentos': Documento.objects.filter(evaluacion=evaluacion).count(),
        'fragmentos': estado_embeddings.get('total_fragmentos', 0),
        'listos': estado_embeddings.get('indexados', 0),
        'total_subfactores': total,
        'con_evidencia': con,
        'sin_evidencia': len(sin),
        'porcentaje': round(con * 100 / total) if total else 0,
        'nombres_sin_evidencia': nombres[:MAX_NOMBRES_SIN_EVIDENCIA],
        'mas_sin_evidencia': max(len(nombres) - MAX_NOMBRES_SIN_EVIDENCIA, 0),
        'puede_sugerir': bool(sin) and estado_embeddings.get('indexados', 0) > 0,
    }


def sugerencias(servicio_retrieval, evaluacion, valoraciones):
    """Fragmentos más parecidos para cada subfactor que aún no tiene evidencia (solo lectura)."""
    conteo = _conteo_evidencias(valoraciones)
    grupos = []
    for v in valoraciones:
        if conteo.get(v.pk, 0):
            continue
        try:
            encontrados = servicio_retrieval.buscar_por_subfactor(
                evaluacion_id=evaluacion.evaluacion_id, subfactor_id=v.subfactor_id,
                top_k=TOP_POR_SUBFACTOR, umbral_similitud=UMBRAL_SUGERENCIA)
        except ValidationError:
            continue
        if not encontrados:
            continue
        items = []
        for i, r in enumerate(encontrados):
            texto = ' '.join((r['contenido'] or '').split())
            items.append({
                'valor': f"{v.pk}:{r['fragmento_id']}:{r['similitud']}",
                'documento': r['documento_nombre'],
                'ubicacion': r['ubicacion_referencia'],
                'extracto': texto if len(texto) <= EXTRACTO else texto[:EXTRACTO].rstrip() + '…',
                'porcentaje': round(r['similitud'] * 100),
                'marcado': i == 0 and r['similitud'] >= UMBRAL_PRESELECCION,
            })
        grupos.append({
            'factor': v.evaluacion_factor.factor.nombre,
            'subfactor': v.subfactor.descripcion,
            'items': items,
        })
    total = sum(len(g['items']) for g in grupos)
    return {
        'grupos': grupos,
        'subfactores': len(grupos),
        'propuestas': total,
        'marcadas': sum(1 for g in grupos for i in g['items'] if i['marcado']),
        'sin_candidatos': len([v for v in valoraciones if conteo.get(v.pk, 0) == 0]) - len(grupos),
    }


def vincular_en_lote(servicio_retrieval, evaluacion, valoraciones, seleccion):
    """Crea las evidencias confirmadas. `seleccion`: textos «valoracion_id:fragmento_id:similitud»."""
    validas = {v.pk: v for v in valoraciones}
    creadas = existentes = 0
    for texto in seleccion:
        partes = (texto or '').split(':')
        if len(partes) != 3 or not partes[0].isdigit() or not partes[1].isdigit():
            continue
        valoracion = validas.get(int(partes[0]))
        fragmento = FragmentoDocumento.objects.select_related('documento').filter(
            pk=int(partes[1]), documento__evaluacion=evaluacion).first()
        if valoracion is None or fragmento is None:
            continue
        try:
            relevancia = Decimal(partes[2]).quantize(Decimal('0.01'))
        except InvalidOperation:
            relevancia = None
        _, creada = Evidencia.objects.get_or_create(
            valoracion=valoracion, fragmento=fragmento,
            defaults={'referencia': servicio_retrieval._formatear_ubicacion(fragmento), 'relevancia': relevancia})
        creadas += 1 if creada else 0
        existentes += 0 if creada else 1
    return creadas, existentes