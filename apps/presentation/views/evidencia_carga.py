"""
Apoyo de la pantalla de Carga documental para vincular evidencia con menos trabajo manual.

Nada de aquí cambia la lógica existente de HU07/HU08:
- `cobertura` y `opciones_subfactores` solo leen.
- `datos_respaldo` usa `RetrievalService.buscar_por_subfactor` tal cual (solo lectura).
- `vincular_en_lote` crea evidencias con el mismo `get_or_create` de la acción individual
  «vincular_evidencia», pero para varias a la vez y solo con lo que la persona confirmó.
"""
import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db.models import Count

from apps.data.models import Documento, Evidencia, FragmentoDocumento

TOP_POR_SUBFACTOR = 3
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


STOP = {'para', 'como', 'esta', 'este', 'estos', 'estas', 'entre', 'sobre', 'desde', 'hasta', 'cuando', 'donde',
        'tiene', 'tienen', 'puede', 'pueden', 'cada', 'otros', 'otras', 'bien', 'sino', 'pero', 'aunque', 'según'}
UMBRAL_MIN = 0.05
UMBRAL_ALTA = 0.30
UMBRAL_MEDIA = 0.15
VENTANA = 520
MAX_TEXTO = 4000


def _nivel(similitud):
    return 'alta' if similitud >= UMBRAL_ALTA else 'media' if similitud >= UMBRAL_MEDIA else 'baja'


def _raices(texto):
    """Raíces (6 letras) de las palabras significativas del subfactor, para mostrar por qué se sugiere un pasaje."""
    vistas, raices = set(), []
    for palabra in re.findall(r'[a-záéíóúñü]{5,}', (texto or '').lower()):
        raiz = palabra[:6]
        if palabra not in STOP and raiz not in vistas:
            vistas.add(raiz)
            raices.append(raiz)
    return raices


def _ventana(texto, comunes):
    posiciones = [texto.lower().find(c) for c in comunes if texto.lower().find(c) >= 0]
    if not posiciones or len(texto) <= VENTANA:
        corte = texto[:VENTANA]
        return corte if len(texto) <= VENTANA else corte.rstrip() + '…'
    inicio = max(min(posiciones) - VENTANA // 3, 0)
    corte = texto[inicio:inicio + VENTANA].strip()
    return ('…' if inicio else '') + corte + ('…' if inicio + VENTANA < len(texto) else '')


def datos_respaldo(servicio_retrieval, evaluacion, valoraciones, url_base, hay_indexados):
    """
    Datos para la pantalla «Respaldo de los subfactores»: por cada subfactor, el respaldo ya guardado y,
    si aún no tiene, los pasajes más parecidos (solo lectura; no crea nada).
    """
    valoraciones = list(valoraciones)
    guardados = {}
    for e in (Evidencia.objects.filter(valoracion_id__in=[v.pk for v in valoraciones])
              .select_related('fragmento__documento').order_by('pk')):
        guardados.setdefault(e.valoracion_id, []).append({
            'documento': e.fragmento.documento.nombre,
            'ubicacion': e.referencia or servicio_retrieval._formatear_ubicacion(e.fragmento),
        })
    resultado = []
    for v in valoraciones:
        candidatos = []
        if hay_indexados and v.pk not in guardados:
            try:
                encontrados = servicio_retrieval.buscar_por_subfactor(
                    evaluacion_id=evaluacion.evaluacion_id, subfactor_id=v.subfactor_id,
                    top_k=TOP_POR_SUBFACTOR, umbral_similitud=UMBRAL_MIN)
            except ValidationError:
                encontrados = []
            raices = _raices(v.subfactor.descripcion)
            for r in encontrados:
                texto = ' '.join((r['contenido'] or '').split())
                comunes = [c for c in raices if c in texto.lower()]
                nombre = r['documento_nombre']
                candidatos.append({
                    'valor': f"{v.pk}:{r['fragmento_id']}:{r['similitud']}",
                    'documento': nombre,
                    'tipo': (nombre.rsplit('.', 1)[-1] if '.' in nombre else '').upper(),
                    'ubicacion': r['ubicacion_referencia'],
                    'nivel': _nivel(r['similitud']),
                    'extracto': _ventana(texto, comunes),
                    'texto': texto[:MAX_TEXTO],
                    'comunes': comunes[:6],
                    'url': f"{url_base}&doc_id={r['documento_id']}&fragmento_id={r['fragmento_id']}&panel=1",
                })
        resultado.append({
            'id': v.pk,
            'factor': v.evaluacion_factor.factor.nombre,
            'texto': v.subfactor.descripcion,
            'guardados': guardados.get(v.pk, []),
            'candidatos': candidatos,
        })
    return resultado


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