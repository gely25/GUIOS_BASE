"""
Vistas de Carga Documental (HU07), Recuperación Semántica con pgvector (HU08)
y trazabilidad de evidencia para HU10 - Espacio del Decisor.
"""
import os
import re
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.application.services.document import DocumentService
from apps.application.services.preguntas import PreguntasService
from apps.application.services.retrieval import RetrievalService
from apps.presentation.views import evidencia_carga
from apps.presentation.views.fragmentos_panel import contexto_panel
from apps.data.models import Documento, Evaluacion, Evidencia, FragmentoDocumento, Subfactor


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


DOCS_POR_PAGINA = 5
VERSIONES_BASE = ['v1.0', 'v2.0', 'v3.0']


def _versiones_sugeridas(documentos):
    """Etiquetas de versión para elegir: las habituales y las que ya se usaron en la evaluación."""
    usadas = sorted({d.version for d in documentos if d.version})
    return VERSIONES_BASE + [v for v in usadas if v not in VERSIONES_BASE]


def carga_documental_view(request):
    """
    Pantalla «Decisor · Carga documental» (HU07 + HU08).
    Permite subir archivos PDF/DOCX/XLSX, generar sus embeddings de 1536 dimensiones
    en pgvector, inspeccionar fragmentos, comprobar su ubicación y vincularlos a subfactores.
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
                f'Búsqueda actualizada: {res["indexados"]} fragmento(s) listos para buscar.'
            )
            return redirect(url_destino)

        if accion == 'preparar_evidencia':
            # RF11: el sistema recupera por sí solo los pasajes relacionados con cada subfactor.
            url_paso4 = (f"{reverse('presentation:decisor-revision-valoraciones')}"
                         f"?evaluacion={evaluacion.evaluacion_id}&etapa=validacion")
            if evaluacion.documentos.exists():
                creadas, cubiertos = evidencia_carga.preparar_evidencia(
                    retrieval_service, evaluacion, list(PreguntasService._valoraciones(evaluacion)))
                if creadas:
                    messages.success(
                        request,
                        f'Se asociaron {creadas} pasaje{"" if creadas == 1 else "s"} de sus documentos a '
                        f'{cubiertos} subfactor{"" if cubiertos == 1 else "es"}. Revíselos en este paso.')
                else:
                    messages.info(
                        request,
                        'No se encontraron pasajes suficientemente relacionados con los subfactores pendientes.')
            return redirect(url_paso4)

        if accion == 'vincular_evidencia':
            frag_id = (request.POST.get('fragmento_id') or '').strip()
            val_id = (request.POST.get('valoracion_id') or '').strip()
            relevancia_raw = (request.POST.get('relevancia') or '').strip().replace(',', '.')
            if not frag_id.isdigit() or not val_id.isdigit():
                messages.error(request, 'Seleccione un fragmento y un subfactor válidos para vincular.')
                return redirect(url_destino)

            fragmento = get_object_or_404(
                FragmentoDocumento,
                fragmento_id=int(frag_id),
                documento__evaluacion=evaluacion,
            )
            valoracion = PreguntasService._valoraciones(evaluacion).filter(pk=int(val_id)).first()
            if not valoracion:
                messages.error(request, 'El subfactor seleccionado no pertenece a esta evaluación.')
                return redirect(url_destino)

            ubicacion = retrieval_service._formatear_ubicacion(fragmento)
            try:
                relevancia = Decimal(relevancia_raw) if relevancia_raw else None
            except InvalidOperation:
                relevancia = None

            evidencia, creada = Evidencia.objects.get_or_create(
                valoracion=valoracion,
                fragmento=fragmento,
                defaults={'referencia': ubicacion, 'relevancia': relevancia},
            )
            if not creada and not evidencia.referencia:
                evidencia.referencia = ubicacion
                evidencia.save(update_fields=['referencia'])

            messages.success(
                request,
                f'Evidencia E:{evidencia.pk} ({fragmento.documento.nombre} · {ubicacion}) vinculada al subfactor «{valoracion.subfactor.descripcion}».'
            )
            return redirect(
                f'{url_destino}&doc_id={fragmento.documento_id}&fragmento_id={fragmento.fragmento_id}#fragmento-{fragmento.fragmento_id}'
            )

        if accion == 'renombrar':
            doc = get_object_or_404(Documento, documento_id=request.POST.get('documento_id'), evaluacion=evaluacion)
            nuevo = ' '.join(re.split(r'[\\/]', request.POST.get('nombre') or '')[-1].split())  # sin rutas
            extension = os.path.splitext(doc.nombre)[1]
            if extension and not nuevo.lower().endswith(extension.lower()):
                nuevo += extension
            if not nuevo or nuevo.lower() == extension.lower():
                messages.error(request, 'Escriba un nombre para el documento.')
            elif len(nuevo) > 255:
                messages.error(request, 'El nombre es demasiado largo (máximo 255 caracteres).')
            else:
                anterior = doc.nombre
                doc.nombre = nuevo
                doc.save(update_fields=['nombre'])
                messages.success(request, f'Documento renombrado: «{anterior}» → «{nuevo}».')
            return redirect(url_destino)

        if accion == 'eliminar':
            doc_id = request.POST.get('documento_id')
            doc = get_object_or_404(Documento, documento_id=doc_id, evaluacion=evaluacion)
            nombre_doc = doc.nombre
            try:
                servicio.eliminar_documento(doc)
                messages.success(request, f'Documento «{nombre_doc}» y sus fragmentos eliminados.')
            except ProtectedError:
                messages.error(
                    request,
                    f'No se puede eliminar «{nombre_doc}» porque tiene fragmentos vinculados como evidencia en uno o más subfactores.'
                )
            return redirect(url_destino)

        archivos = request.FILES.getlist('archivo') or [None]
        version = request.POST.get('version', '')
        cargados, fragmentos_total = [], 0
        for archivo in archivos:
            try:
                doc = servicio.procesar_carga(
                    evaluacion=evaluacion,
                    usuario=request.user,
                    archivo=archivo,
                    version=version,
                )
            except ValidationError as err:
                mensaje = err.messages[0] if hasattr(err, 'messages') else str(err)
                nombre = f'«{archivo.name}»: ' if archivo is not None and len(archivos) > 1 else ''
                messages.error(request, nombre + mensaje)
                continue
            cargados.append(doc)
            fragmentos_total += doc.fragmentos.count()
        if len(cargados) == 1:
            doc = cargados[0]
            messages.success(
                request,
                f'Documento «{doc.nombre}» ({doc.tipo}) procesado e indexado en pgvector: {fragmentos_total} fragmentos.'
            )
            if len(archivos) == 1 and request.POST.get('volver') != 'validacion':
                return redirect(f'{url_destino}&doc_id={doc.documento_id}')
        elif cargados:
            messages.success(
                request,
                f'{len(cargados)} documentos procesados e indexados: {fragmentos_total} fragmentos en total.'
            )
        if request.POST.get('volver') == 'validacion':
            # Se subió desde el paso 4: se asocian los pasajes y se vuelve a la revisión.
            if cargados:
                try:
                    evidencia_carga.preparar_evidencia(
                        retrieval_service, evaluacion, list(PreguntasService._valoraciones(evaluacion)))
                except ValidationError as err:
                    messages.error(request, err.messages[0] if hasattr(err, 'messages') else str(err))
            return redirect(f"{reverse('presentation:decisor-revision-valoraciones')}?etapa=validacion&evaluacion={evaluacion.evaluacion_id}")
        return redirect(url_destino)

    documentos = []
    documento_inspeccionado = None
    panel = None
    valoraciones_evaluacion = []
    estado_embeddings = {'total_fragmentos': 0, 'indexados': 0, 'pendientes': 0, 'porcentaje': 0}
    consulta_semantica = (request.GET.get('q') or '').strip()
    resultados_semanticos = []

    subfactores_catalogo = (
        Subfactor.objects.select_related('factor', 'factor__dimension')
        .filter(activo=True)
        .order_by('factor__dimension__dimension_id', 'factor__factor_id', 'subfactor_id')
    )
    subfactor_seleccionado_id = (request.GET.get('subfactor_id') or '').strip()
    fragmento_destacado_raw = (request.GET.get('fragmento_id') or '').strip()
    fragmento_destacado_id = int(fragmento_destacado_raw) if fragmento_destacado_raw.isdigit() else None

    if evaluacion:
        estado_embeddings = retrieval_service.estado_indexacion(evaluacion.evaluacion_id)
        valoraciones_evaluacion = list(PreguntasService._valoraciones(evaluacion))

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
            .annotate(
                total_fragmentos=Count('fragmentos'),
                indexados=Count('fragmentos', filter=Q(fragmentos__embedding__isnull=False)),
            )
            .order_by('-fecha_carga')
        )
        doc_id = request.GET.get('doc_id')
        if not doc_id and fragmento_destacado_id:
            frag_obj = FragmentoDocumento.objects.filter(
                fragmento_id=fragmento_destacado_id,
                documento__evaluacion=evaluacion,
            ).first()
            if frag_obj:
                doc_id = str(frag_obj.documento_id)

        if doc_id:
            documento_inspeccionado = documentos.filter(documento_id=doc_id).first()

        if documento_inspeccionado and (request.GET.get('panel') or fragmento_destacado_id):
            panel = contexto_panel(
                request, evaluacion, documento_inspeccionado, retrieval_service,
                valoraciones_evaluacion, _parsear_fragmento_tabular, fragmento_destacado_id)

    cobertura = opciones = None
    if evaluacion:
        cobertura = evidencia_carga.cobertura(evaluacion, valoraciones_evaluacion, estado_embeddings)
        opciones = evidencia_carga.opciones_subfactores(valoraciones_evaluacion)

    explorar_abierto = bool(consulta_semantica or subfactor_seleccionado_id)
    anterior_url = siguiente_url = ''
    nota_paso = ''
    if evaluacion:
        anterior_url = f"{reverse('presentation:decisor-importancia-factores')}?evaluacion_id={evaluacion.evaluacion_id}"
        siguiente_url = f"{reverse('presentation:decisor-revision-valoraciones')}?evaluacion={evaluacion.evaluacion_id}&etapa=validacion"
        total_docs = len(documentos)
        nota_paso = (
            f'{total_docs} documento{"" if total_docs == 1 else "s"} cargado{"" if total_docs == 1 else "s"}'
            if total_docs else 'Sin documentos: no habrá evidencia que vincular en el paso 4.'
        )

    context = {
        'active_tab': 'carga-documental',
        'explorar_abierto': explorar_abierto,
        'anterior_url': anterior_url,
        'siguiente_url': siguiente_url,
        'nota_paso': nota_paso,
        'current_step': 3,
        'evaluacion': evaluacion,
        'evaluaciones': evaluaciones,
        'documentos': documentos,
        'docs_pagina': Paginator(documentos, DOCS_POR_PAGINA).get_page(request.GET.get('pag')),
        'versiones_sugeridas': _versiones_sugeridas(documentos),
        'documento_inspeccionado': documento_inspeccionado,
        'panel': panel,
        'cobertura': cobertura,
        'opciones': opciones,
        'fragmento_destacado_id': fragmento_destacado_id,
        'valoraciones_evaluacion': valoraciones_evaluacion,
        'estado_embeddings': estado_embeddings,
        'consulta_semantica': consulta_semantica,
        'resultados_semanticos': resultados_semanticos,
        'subfactores_catalogo': subfactores_catalogo,
        'subfactor_seleccionado_id': int(subfactor_seleccionado_id) if subfactor_seleccionado_id.isdigit() else None,
    }
    return render(request, 'presentation/decisor/carga_documental.html', context)