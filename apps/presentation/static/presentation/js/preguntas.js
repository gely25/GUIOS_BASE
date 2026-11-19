document.querySelectorAll('.hu09-ai').forEach(form => {
    form.addEventListener('submit', event => {
        if (form.dataset.busy) {
            event.preventDefault();
            return;
        }
        form.dataset.busy = 'true';
        form.setAttribute('aria-busy', 'true');
        form.querySelector('.hu09-wait').hidden = false;
    });
});
window.addEventListener('pageshow', () => {
    document.querySelectorAll('.hu09-ai').forEach(form => {
        delete form.dataset.busy;
        form.removeAttribute('aria-busy');
        form.querySelector('.hu09-wait').hidden = true;
    });
});

// Solo consulta el estado; nunca recarga ni sustituye respuestas en edición.
const panelLote = document.querySelector('#hu09-lote');
if (panelLote) {
    const estado = panelLote.querySelector('#hu09-lote-estado');
    const progreso = panelLote.querySelector('#hu09-lote-progreso');
    const resumen = panelLote.querySelector('#hu09-lote-resumen');
    const boton = panelLote.querySelector('#hu09-iniciar-lote');
    async function consultarLote() {
        try {
            const respuesta = await fetch(panelLote.dataset.url, {credentials: 'same-origin', cache: 'no-store'});
            if (!respuesta.ok || respuesta.redirected) throw new Error('No disponible');
            const {lote} = await respuesta.json();
            if (!lote) return;
            const activo = ['EN_COLA', 'EN_PROCESO'].includes(lote.estado);
            estado.textContent = `Lote #${lote.id} · ${lote.estado} · ${lote.procesados}/${lote.total}`;
            progreso.max = Math.max(1, lote.total);
            progreso.value = lote.procesados;
            resumen.textContent = `Preguntas nuevas: ${lote.preguntas_nuevas} · Omitidos: ${lote.omitidos} · Errores: ${lote.errores}`;
            if (boton) boton.disabled = activo;
            if (activo) window.setTimeout(consultarLote, 3000);
        } catch (error) {
            estado.textContent = 'No se pudo consultar el lote. Reintentando…';
            window.setTimeout(consultarLote, 5000);
        }
    }
    consultarLote();
}

// Filtros locales: conservan los formularios y borradores en el DOM.
const buscador = document.querySelector('#hu09-buscar');
const filtro = document.querySelector('#hu09-filtro');
const normalizar = texto => texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
function filtrarHU09() {
    if (!buscador || !filtro) return;
    let visibles = 0;
    document.querySelectorAll('.hu09-subfactor').forEach(card => {
        const texto = normalizar(card.dataset.indice);
        const preguntas = [...card.querySelectorAll('.hu09-question')];
        const coincide = filtro.value === 'TODAS' || preguntas.some(p => p.dataset.estado === filtro.value);
        card.hidden = !texto.includes(normalizar(buscador.value.trim())) || !coincide;
        if (!card.hidden) visibles++;
        preguntas.forEach(p => { p.hidden = filtro.value !== 'TODAS' && p.dataset.estado !== filtro.value && !p.querySelector('form[data-dirty="true"]'); });
        const enlace = document.querySelector(`.hu09-nav a[data-destino="${card.id}"]`);
        if (enlace) enlace.hidden = card.hidden;
    });
    document.querySelectorAll('.hu09-factor-group,.hu09-dimension').forEach(grupo => {
        grupo.hidden = !grupo.querySelector('.hu09-subfactor:not([hidden])');
    });
    document.querySelector('#hu09-sin-resultados').hidden = visibles !== 0;
}
if (buscador && filtro) {
    buscador.addEventListener('input', filtrarHU09);
    filtro.addEventListener('change', filtrarHU09);
}
document.querySelectorAll('[data-fuente]').forEach(enlace => {
    enlace.addEventListener('click', () => {
        if (buscador && filtro) { buscador.value = ''; filtro.value = 'TODAS'; filtrarHU09(); }
        const fuente = document.getElementById(enlace.hash.slice(1));
        if (fuente) { const detalle = fuente.closest('details'); if (detalle) detalle.open = true; }
    });
});

// Guardado sin recarga. Una cola cliente evita solicitudes simultáneas de la misma página.
let colaGuardado = Promise.resolve();
const formulariosRespuesta = [...document.querySelectorAll('.hu09-respuesta')];
formulariosRespuesta.forEach(form => {
    const campo = form.querySelector('textarea');
    const estado = form.querySelector('.hu09-save-status');
    const version = form.elements.version;
    const pregunta = form.closest('.hu09-question');
    let guardado = campo.value;
    let timer;
    let enCola = false;
    function marcar() {
        form.dataset.dirty = String(campo.value !== guardado);
    }
    function programar() {
        clearTimeout(timer);
        marcar();
        if (campo.value === guardado) { estado.textContent = ''; return; }
        estado.textContent = campo.value.trim() ? 'Cambios pendientes de guardar…' : 'Una respuesta vacía no se guarda.';
        if (campo.value.trim()) timer = setTimeout(guardar, 1500);
    }
    function guardar() {
        clearTimeout(timer);
        if (enCola || campo.value === guardado || !campo.value.trim()) return;
        enCola = true;
        form.dataset.saving = 'true';
        colaGuardado = colaGuardado.then(async () => {
            const enviado = campo.value;
            if (enviado === guardado || !enviado.trim()) return;
            estado.dataset.error = 'false';
            estado.textContent = 'Guardando…';
            const datos = new FormData(form);
            datos.set('accion', 'autoguardar');
            datos.set('respuesta', enviado);
            try {
                const res = await fetch(form.action || location.href, {method:'POST', body: datos, credentials:'same-origin', cache:'no-store'});
                if (res.redirected) throw new Error('Sesión expirada. Conserve su borrador.');
                const resultado = await res.json();
                if (!res.ok) throw new Error(resultado.error || 'No se pudo guardar.');
                guardado = resultado.respuesta;
                version.value = resultado.version;
                if (campo.value === enviado) campo.value = guardado;
                estado.textContent = 'Guardado automáticamente.';
                pregunta.dataset.estado = resultado.estado;
                const etiqueta = pregunta.querySelector('.hu09-respuesta-estado');
                etiqueta.classList.toggle('hu09-done', resultado.estado === 'APORTADA');
                etiqueta.classList.toggle('hu09-unknown', ['DESCONOCE','NO_INFORMATIVA'].includes(resultado.estado));
                etiqueta.textContent = resultado.estado === 'DESCONOCE' ? 'Desconocida' : resultado.estado === 'NO_INFORMATIVA' ? 'Sin aporte' : 'Respondida';
                pregunta.querySelector('.hu09-fecha').textContent = `R:${form.elements.pregunta.value} · Último guardado: ${resultado.fecha}`;
                const descarte = pregunta.querySelector('.hu09-discard-active');
                if (descarte) descarte.elements.version.value = resultado.version;
                const card = pregunta.closest('.hu09-subfactor');
                card.querySelector('.hu09-info').textContent = resultado.estado_informacion === 'DESCONOCE' ? 'Información desconocida · sin evidencia suficiente' : resultado.estado_informacion === 'SIN_APORTE' ? 'Respuestas sin aporte · sin evidencia suficiente' : 'Información disponible · pendiente de análisis';
                const panel = card.querySelector('.hu09-suficiencia');
                if (!resultado.vigente && panel) {
                    let aviso = panel.querySelector('.hu09-cambio');
                    if (!aviso) { aviso = document.createElement('p'); aviso.className = 'hu09-cambio hu09-muted'; panel.prepend(aviso); }
                    aviso.textContent = 'Información actualizada. Recargue para revisar la suficiencia y las acciones disponibles.';
                    panel.querySelectorAll('.hu09-conclusion,.hu09-justificacion,.hu09-fuentes').forEach(el => { el.hidden = true; });
                    const entrega = panel.querySelector('.hu09-entrega span');
                    if (entrega) entrega.textContent = 'Información actualizada; recargue para comprobar el estado.';
                }
                document.querySelector('#hu09-total').textContent = resultado.total;
                document.querySelector('#hu09-respondidas').textContent = resultado.respondidas;
                document.querySelector('#hu09-pendientes').textContent = resultado.total - resultado.respondidas;
                document.querySelector('#hu09-desconocidas').textContent = resultado.desconocidas;
                document.querySelector('#hu09-no-informativas').textContent = resultado.no_informativas;
                const progreso = document.querySelector('#hu09-progreso');
                if (progreso) { progreso.max = Math.max(1, resultado.total); progreso.value = resultado.respondidas; }
                marcar();
                // No ocultar el campo recién guardado hasta que el usuario cambie el filtro.
                if (campo.value !== guardado) programar();
            } catch (error) {
                estado.dataset.error = 'true';
                estado.textContent = `${error.message} El borrador sigue en pantalla; pulse Guardar respuesta para reintentar.`;
            }
        }).finally(() => { enCola = false; delete form.dataset.saving; marcar(); });
    }
    campo.addEventListener('input', programar);
    form.addEventListener('submit', evento => {
        evento.preventDefault();
        if (evento.submitter?.value === 'desconozco') campo.value = 'No lo sé';
        marcar(); guardar();
    });
});
window.addEventListener('beforeunload', evento => {
    if (formulariosRespuesta.some(form => form.dataset.dirty === 'true' || form.dataset.saving === 'true')) {
        evento.preventDefault(); evento.returnValue = '';
    }
});

// Confirmar el descarte de una respuesta sin salir del diseño de la aplicación.
const dialogoDescarte = document.querySelector('#hu09-confirmar-descarte');
let descartePendiente = null;
let descarteConfirmado = null;
if (dialogoDescarte) {
    dialogoDescarte.querySelector('#hu09-cancelar-descarte').addEventListener('click', () => dialogoDescarte.close());
    dialogoDescarte.querySelector('#hu09-aceptar-descarte').addEventListener('click', () => {
        const form = descartePendiente;
        if (!form) return;
        descarteConfirmado = form;
        dialogoDescarte.close();
        form.requestSubmit(form.querySelector('button[type="submit"]'));
        descarteConfirmado = null;
    });
    dialogoDescarte.addEventListener('close', () => { descartePendiente = null; });
}
document.querySelectorAll('.hu09-discard-active').forEach(form => {
    form.addEventListener('submit', event => {
        const pregunta = form.closest('.hu09-question');
        const respuesta = pregunta.querySelector('.hu09-respuesta');
        form.elements.confirmar.value = '0';
        if (respuesta && (respuesta.dataset.dirty === 'true' || respuesta.dataset.saving === 'true')) {
            event.preventDefault();
            respuesta.querySelector('.hu09-save-status').textContent = 'Guarde la respuesta antes de descartar la pregunta.';
            return;
        }
        if (pregunta.dataset.estado !== 'PENDIENTE' && descarteConfirmado !== form) {
            if (!dialogoDescarte || typeof dialogoDescarte.showModal !== 'function') {
                if (!window.confirm('¿Descartar esta pregunta respondida? La respuesta se conservará en el historial.')) {
                    event.preventDefault();
                    return;
                }
            } else {
                event.preventDefault();
                descartePendiente = form;
                dialogoDescarte.querySelector('#hu09-dialog-pregunta').textContent = pregunta.querySelector('label').textContent;
                dialogoDescarte.showModal();
                return;
            }
        }
        form.elements.confirmar.value = '1';
    });
});
