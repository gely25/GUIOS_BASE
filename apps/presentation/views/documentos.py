"""
Vistas de Carga Documental (HU07), Recuperación Semántica con pgvector (HU08)
y trazabilidad de evidencia para HU10 - Espacio del Decisor.
"""
import os
import re
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
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


def _respaldo_subfactores(request, evaluacion, evaluaciones, retrieval_service,
                         valoraciones, estado_embeddings, cobertura):
    """Pantalla «Respaldo de los subfactores»: elegir qué pasaje respalda cada subfactor (se guarda por POST aparte)."""
    base = reverse('presentation:decisor-carga-documental')
    url_paso3 = f"{base}?evaluacion_id={evaluacion.evaluacion_id}"
    datos = evidencia_carga.datos_respaldo(
        retrieval_service, evaluacion, valoraciones,
        url_base=url_paso3, hay_indexados=cobertura['listos'] > 0)
    pendientes = [d for d in datos if not d['guardados']]
    altas = sum(1 for d in pendientes if d['candidatos'] and d['candidatos'][0]['nivel'] == 'alta')
    return render(request, 'presentation/decisor/respaldo_subfactores.html', {
        'active_tab': 'carga-documental',
        'current_step': 3,
        'evaluacion': evaluacion,
        'evaluaciones': evaluaciones,
        'datos': datos,
        'total': len(datos),
        'n_con': len(datos) - len(pendientes),
        'n_pendientes': len(pendientes),
        'n_altas': altas,
        'url_volver': url_paso3,
    })


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

    ver_id = request.GET.get('ver_id')
    if evaluacion and ver_id:
        doc = get_object_or_404(Documento, documento_id=ver_id, evaluacion=evaluacion)
        if doc.tipo.upper() != 'PDF':
            return redirect(
                f"{reverse('presentation:decisor-carga-documental')}"
                f"?evaluacion_id={evaluacion.evaluacion_id}&doc_id={doc.documento_id}&panel=1")
        ruta = servicio.ruta_absoluta_documento(doc)
        if not ruta.exists():
            raise Http404('El archivo físico no se encuentra en el servidor.')
        respuesta = FileResponse(open(ruta, 'rb'), content_type='application/pdf')
        respuesta['Content-Disposition'] = 'inline'
        respuesta['X-Frame-Options'] = 'SAMEORIGIN'  # solo el propio sitio puede incrustarlo en el visor
        return respuesta

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

        if accion == 'vincular_sugeridas':
            seleccion = request.POST.getlist('sel')
            if not seleccion:
                messages.info(request, 'No marcó ninguna sugerencia, así que no se vinculó nada.')
                return redirect(url_destino)
            creadas, existentes = evidencia_carga.vincular_en_lote(
                retrieval_service, evaluacion, list(PreguntasService._valoraciones(evaluacion)), seleccion)
            texto = f'{creadas} evidencia{"" if creadas == 1 else "s"} vinculada{"" if creadas == 1 else "s"}'
            if existentes:
                texto += f' ({existentes} ya existía{"" if existentes == 1 else "n"})'
            messages.success(request, texto + '. Puede revisarlas en el paso 4.')
            return redirect(url_destino)

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
        if request.GET.get('revisar'):
            return _respaldo_subfactores(request, evaluacion, evaluaciones, retrieval_service,
                                         valoraciones_evaluacion, estado_embeddings, cobertura)

    explorar_abierto = bool(consulta_semantica or subfactor_seleccionado_id)
    anterior_url = siguiente_url = ''
    nota_paso = ''
    if evaluacion:
        anterior_url = f"{reverse('presentation:decisor-importancia-factores')}?evaluacion_id={evaluacion.evaluacion_id}"
        siguiente_url = f"{reverse('presentation:decisor-revision-valoraciones')}?evaluacion={evaluacion.evaluacion_id}"
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