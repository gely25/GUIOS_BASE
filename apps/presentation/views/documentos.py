"""
Vistas de Carga Documental (HU07) y Recuperación Semántica con pgvector (HU08) - Espacio del Decisor.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.application.services.document import DocumentService
from apps.application.services.retrieval import RetrievalService
from apps.data.models import Documento, Evaluacion, FragmentoDocumento, Subfactor


def _obtener_evaluacion_activa(request):
    evaluaciones = (
        Evaluacion.objects.filter(usuario=request.user)
        .select_related('software', 'organizacion')
        .order_by('-fecha_inicio')
    )
    eval_id = request.GET.get('evaluacion_id') or request.POST.get('evaluacion_id')
    if eval_id:
        evaluacion = evaluaciones.filter(evaluacion_id=eval_id).first()
    else:
        evaluacion = evaluaciones.first()
    return evaluacion, evaluaciones


def _parsear_fragmento_tabular(contenido: str):
    """
    Convierte fragmentos tabulares (Excel o tablas Word con ' | ') en
    encabezados y filas para dibujarlos por columnas en la interfaz.
    """
    lineas = [linea.strip() for linea in contenido.splitlines() if linea.strip()]
    if len(lineas) < 2:
        return None

    lineas_con_pipe = [linea for linea in lineas if ' | ' in linea]
    if len(lineas_con_pipe) < 2:
        return None

    filas_divididas = [[celda.strip() for celda in linea.split(' | ')] for linea in lineas_con_pipe]
    max_cols = max(len(fila) for fila in filas_divididas)
    if max_cols < 2:
        return None

    filas_normalizadas = [fila + [''] * (max_cols - len(fila)) for fila in filas_divididas]
    return {
        'encabezados': filas_normalizadas[0],
        'filas': filas_normalizadas[1:],
    }


def carga_documental_view(request):
    """
    Pantalla «Decisor · Carga documental» (HU07 + HU08).
    Permite subir archivos PDF/DOCX/XLSX, generar sus embeddings de 1536 dimensiones
    en pgvector, inspeccionar fragmentos y probar recuperación semántica por subfactor o consulta.
    """
    servicio = DocumentService()
    retrieval_service = RetrievalService()
    evaluacion, evaluaciones = _obtener_evaluacion_activa(request)

    descargar_id = request.GET.get('descargar_id')
    if evaluacion and descargar_id:
        doc = get_object_or_404(Documento, documento_id=descargar_id, evaluacion=evaluacion)
        ruta = servicio.ruta_absoluta_documento(doc)
        if not ruta.exists():
            raise Http404('El archivo físico no se encuentra en el servidor.')
        return FileResponse(open(ruta, 'rb'), as_attachment=True, filename=doc.nombre)

    if request.method == 'POST':
        if not evaluacion:
            messages.error(request, 'No existe una evaluación activa seleccionada.')
            return redirect('presentation:decisor-carga-documental')

        accion = request.POST.get('accion', 'subir')
        url_destino = f"{reverse('presentation:decisor-carga-documental')}?evaluacion_id={evaluacion.evaluacion_id}"

        if accion == 'sincronizar_embeddings':
            res = retrieval_service.sincronizar_evaluacion(
                evaluacion_id=evaluacion.evaluacion_id,
                forzar=True,
            )
            messages.success(
                request,
                f'Indexación vectorial actualizada en pgvector: {res["indexados"]} fragmento(s) de 1536D.'
            )
            return redirect(url_destino)

        if accion == 'eliminar':
            doc_id = request.POST.get('documento_id')
            doc = get_object_or_404(Documento, documento_id=doc_id, evaluacion=evaluacion)
            nombre_doc = doc.nombre
            servicio.eliminar_documento(doc)
            messages.success(request, f'Documento «{nombre_doc}» y sus fragmentos eliminados.')
            return redirect(url_destino)

        archivo = request.FILES.get('archivo')
        version = request.POST.get('version', '')
        try:
            doc = servicio.procesar_carga(
                evaluacion=evaluacion,
                usuario=request.user,
                archivo=archivo,
                version=version,
            )
            total_frag = doc.fragmentos.count()
            messages.success(
                request,
                f'Documento «{doc.nombre}» ({doc.tipo}) procesado e indexado en pgvector: {total_frag} fragmentos.'
            )
            return redirect(f'{url_destino}&doc_id={doc.documento_id}')
        except ValidationError as err:
            mensaje = err.messages[0] if hasattr(err, 'messages') else str(err)
            messages.error(request, mensaje)
            return redirect(url_destino)

    documentos = []
    documento_inspeccionado = None
    fragmentos_inspeccionados = []
    estado_embeddings = {'total_fragmentos': 0, 'indexados': 0, 'pendientes': 0, 'porcentaje': 0}
    consulta_semantica = (request.GET.get('q') or '').strip()
    resultados_semanticos = []

    subfactores_catalogo = (
        Subfactor.objects.select_related('factor', 'factor__dimension')
        .filter(activo=True)
        .order_by('factor__dimension__dimension_id', 'factor__factor_id', 'subfactor_id')
    )
    subfactor_seleccionado_id = (request.GET.get('subfactor_id') or '').strip()

    if evaluacion:
        estado_embeddings = retrieval_service.estado_indexacion(evaluacion.evaluacion_id)

        if subfactor_seleccionado_id.isdigit():
            try:
                resultados_semanticos = retrieval_service.buscar_por_subfactor(
                    evaluacion_id=evaluacion.evaluacion_id,
                    subfactor_id=int(subfactor_seleccionado_id),
                    top_k=5,
                )
            except ValidationError as err:
                mensaje = err.messages[0] if hasattr(err, 'messages') else str(err)
                messages.error(request, mensaje)
        elif consulta_semantica:
            try:
                resultados_semanticos = retrieval_service.buscar_evidencia(
                    evaluacion_id=evaluacion.evaluacion_id,
                    consulta=consulta_semantica,
                    top_k=5,
                )
            except ValidationError as err:
                mensaje = err.messages[0] if hasattr(err, 'messages') else str(err)
                messages.error(request, mensaje)

        documentos = (
            Documento.objects.filter(evaluacion=evaluacion)
            .annotate(total_fragmentos=Count('fragmentos'))
            .order_by('-fecha_carga')
        )
        doc_id = request.GET.get('doc_id')
        if doc_id:
            documento_inspeccionado = documentos.filter(documento_id=doc_id).first()
        elif documentos:
            documento_inspeccionado = documentos[0]

        if documento_inspeccionado:
            fragmentos_qs = FragmentoDocumento.objects.filter(
                documento=documento_inspeccionado
            ).order_by('fragmento_id')
            for frag in fragmentos_qs:
                frag.tabla = _parsear_fragmento_tabular(frag.contenido)
                fragmentos_inspeccionados.append(frag)

    context = {
        'active_tab': 'carga-documental',
        'current_step': 3,
        'evaluacion': evaluacion,
        'evaluaciones': evaluaciones,
        'documentos': documentos,
        'documento_inspeccionado': documento_inspeccionado,
        'fragmentos_inspeccionados': fragmentos_inspeccionados,
        'estado_embeddings': estado_embeddings,
        'consulta_semantica': consulta_semantica,
        'resultados_semanticos': resultados_semanticos,
        'subfactores_catalogo': subfactores_catalogo,
        'subfactor_seleccionado_id': int(subfactor_seleccionado_id) if subfactor_seleccionado_id.isdigit() else None,
    }
    return render(request, 'presentation/decisor/carga_documental.html', context)