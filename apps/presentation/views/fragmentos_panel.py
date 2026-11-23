"""
Datos del panel lateral de fragmentos de la Carga documental.

Solo lee: pagina, filtra y ordena los fragmentos de un documento y marca cuáles ya están
vinculados como evidencia. Guardar un vínculo sigue haciéndolo la acción
«vincular_evidencia» de la vista de carga documental.
"""
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator

from apps.data.models import Evidencia, FragmentoDocumento

POR_PAGINA = 10
MAX_CHIPS = 10
MAX_SECCIONES = 12
ESTADOS = (('todos', 'Todos'), ('sin', 'Sin vincular'), ('vinculados', 'Vinculados'))


def _grupos_ubicacion(fragmentos):
    """Chips para moverse por el documento: rangos de páginas, hojas o secciones."""
    paginas = [p for p in fragmentos.values_list('pagina', flat=True) if p is not None]
    if paginas:
        minimo, maximo = min(paginas), max(paginas)
        paso = 10
        while ((maximo - minimo) // paso) + 1 > MAX_CHIPS:
            paso *= 2
        inicio = ((minimo - 1) // paso) * paso + 1
        grupos = []
        while inicio <= maximo:
            fin = inicio + paso - 1
            grupos.append((f'p:{inicio}-{fin}', f'Pág. {inicio}–{fin}'))
            inicio += paso
        return grupos
    hojas = sorted({h for h in fragmentos.values_list('hoja', flat=True) if h})
    if hojas:
        return [(f'h:{h}', h) for h in hojas[:MAX_CHIPS * 2]]
    secciones = sorted({s for s in fragmentos.values_list('seccion', flat=True) if s})
    if 0 < len(secciones) <= MAX_SECCIONES:
        return [(f's:{s}', s) for s in secciones]
    return []


def _aplicar_ubicacion(fragmentos, ubic):
    if ubic.startswith('p:') and '-' in ubic[2:]:
        desde, _, hasta = ubic[2:].partition('-')
        if desde.isdigit() and hasta.isdigit():
            return fragmentos.filter(pagina__gte=int(desde), pagina__lte=int(hasta))
    if ubic.startswith('h:'):
        return fragmentos.filter(hoja=ubic[2:])
    if ubic.startswith('s:'):
        return fragmentos.filter(seccion=ubic[2:])
    return fragmentos


def contexto_panel(request, evaluacion, documento, servicio_retrieval, valoraciones, parsear_tabla, destacado_id):
    """Devuelve el contexto del panel para `documento` según los parámetros GET."""
    eval_id = evaluacion.evaluacion_id
    ubic = (request.GET.get('ubic') or '').strip()
    estado = request.GET.get('estado') if request.GET.get('estado') in ('sin', 'vinculados') else 'todos'
    sugerido_raw = (request.GET.get('sugerido') or '').strip()
    pagina_raw = (request.GET.get('pagina') or '').strip()

    base = FragmentoDocumento.objects.filter(documento=documento).order_by('fragmento_id')
    total = base.count()
    grupos = _grupos_ubicacion(base)

    vinculos = {}
    for ev in Evidencia.objects.filter(fragmento__documento=documento).select_related('valoracion__subfactor__factor'):
        vinculos.setdefault(ev.fragmento_id, []).append(ev.valoracion.subfactor.descripcion)

    subfactores_validos = {v.subfactor_id for v in valoraciones}
    sugerido_id = int(sugerido_raw) if sugerido_raw.isdigit() and int(sugerido_raw) in subfactores_validos else None
    similitud = {}
    orden_sugerido = None
    aviso = ''
    if sugerido_id:
        try:
            resultados = servicio_retrieval.buscar_por_subfactor(
                evaluacion_id=eval_id, subfactor_id=sugerido_id,
                top_k=max(min(total, 500), 1), documento_id=documento.documento_id)
            orden_sugerido = [r['fragmento_id'] for r in resultados]
            similitud = {r['fragmento_id']: r for r in resultados}
            if not orden_sugerido:
                aviso = 'Ningún fragmento de este documento se parece a ese subfactor.'
        except ValidationError as err:
            aviso = err.messages[0] if hasattr(err, 'messages') else str(err)

    consulta = _aplicar_ubicacion(base, ubic)
    if estado == 'sin':
        consulta = consulta.exclude(fragmento_id__in=vinculos.keys())
    elif estado == 'vinculados':
        consulta = consulta.filter(fragmento_id__in=vinculos.keys())

    if orden_sugerido is not None:
        por_id = {f.fragmento_id: f for f in consulta.filter(fragmento_id__in=orden_sugerido)}
        lista = [por_id[i] for i in orden_sugerido if i in por_id]
    else:
        lista = list(consulta)

    if not pagina_raw.isdigit() and destacado_id:
        ids = [f.fragmento_id for f in lista]
        if destacado_id in ids:
            pagina_raw = str(ids.index(destacado_id) // POR_PAGINA + 1)
    paginador = Paginator(lista, POR_PAGINA)
    pagina = paginador.get_page(pagina_raw or 1)

    items = []
    for frag in pagina.object_list:
        sim = similitud.get(frag.fragmento_id)
        items.append({
            'frag': frag,
            'tabla': parsear_tabla(frag.contenido),
            'ubicacion': servicio_retrieval._formatear_ubicacion(frag),
            'vinculos': vinculos.get(frag.fragmento_id, []),
            'similitud': sim['similitud'] if sim else None,
            'porcentaje': sim['relevancia_porcentaje'] if sim else None,
            'destacado': frag.fragmento_id == destacado_id,
        })

    def url(**cambios):
        datos = {'evaluacion_id': eval_id, 'doc_id': documento.documento_id, 'panel': 1,
                 'ubic': ubic, 'estado': estado, 'sugerido': sugerido_id or '', 'pagina': ''}
        datos.update(cambios)
        limpio = {k: v for k, v in datos.items() if v not in ('', None, 'todos')}
        return '?' + urlencode(limpio)

    return {
        'documento': documento,
        'items': items,
        'pagina': pagina,
        'total': total,
        'filtrados': len(lista),
        'vinculados_total': len(vinculos),
        'sin_vincular_total': max(total - len(vinculos), 0),
        'chips': [{'etiqueta': 'Todo', 'url': url(ubic=''), 'activo': not ubic}] + [
            {'etiqueta': etiqueta, 'url': url(ubic=valor), 'activo': ubic == valor} for valor, etiqueta in grupos],
        'estados': [{'etiqueta': etiqueta, 'url': url(estado=valor), 'activo': estado == valor}
                    for valor, etiqueta in ESTADOS],
        'sugerido_id': sugerido_id,
        'aviso': aviso,
        'url_cerrar': f'?evaluacion_id={eval_id}',
        'url_anterior': url(pagina=pagina.number - 1) if pagina.has_previous() else '',
        'url_siguiente': url(pagina=pagina.number + 1) if pagina.has_next() else '',
        'campos_ocultos': {'evaluacion_id': eval_id, 'doc_id': documento.documento_id, 'panel': 1,
                           'ubic': ubic, 'estado': estado if estado != 'todos' else ''},
    }