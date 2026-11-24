(() => {
    'use strict';
    const buscar = document.querySelector('#hu11-buscar');
    const filtro = document.querySelector('#hu11-filtro');
    const enlaces = [...document.querySelectorAll('[data-hu11-nav]')];
    const normalizar = texto => (texto || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

    function filtrar() {
        if (!buscar || !filtro) return;
        let cantidad = 0;
        enlaces.forEach(enlace => {
            const porTexto = normalizar(enlace.dataset.busqueda).includes(normalizar(buscar.value.trim()));
            const estado = filtro.value;
            const porEstado = !estado || (estado === 'BORRADOR' ? enlace.dataset.borrador === '1' :
                enlace.dataset.estado === estado ||
                (estado === 'CONFIRMADA' && enlace.dataset.estado === 'MANUAL'));
            enlace.hidden = !(porTexto && porEstado);
            if (!enlace.hidden) cantidad++;
        });
        document.querySelectorAll('[data-grupo-hu11]').forEach(grupo => {
            let nodo = grupo.nextElementSibling, visible = false;
            while (nodo && !(nodo.hasAttribute('data-grupo-hu11') &&
                (grupo.matches('.hu11-factor') || nodo.matches('.hu11-dimension')))) {
                if (nodo.hasAttribute('data-hu11-nav') && !nodo.hidden) visible = true;
                nodo = nodo.nextElementSibling;
            }
            grupo.hidden = !visible;
        });
        const vacio = document.querySelector('#hu11-sin-resultados');
        if (vacio) vacio.hidden = cantidad !== 0;
    }
    buscar?.addEventListener('input', filtrar);
    filtro?.addEventListener('change', filtrar);

    const dialogo = document.querySelector('#hu11-editor');
    const formulario = document.querySelector('.hu11-form');
    const lote = document.querySelector('#hu11-lote');
    let sucio = false, enviando = false, definitivo = false, temporizador;
    function mostrarDialogo(modo) {
        if (!dialogo || !formulario) return;
        const opcion = formulario.querySelector(`input[name="modo"][value="${modo}"]`);
        if (opcion) opcion.checked = true;
        const radios = [...formulario.querySelectorAll('[name="valor"]')];
        if (modo === 'CONFIRMAR') {
            const propuesta = dialogo.dataset.valorIa;
            const radio = radios.find(item => item.value === propuesta);
            if (radio) radio.checked = true;
        } else if (modo === 'MODIFICAR') {
            const actual = radios.find(item => item.checked);
            if (actual && actual.value === dialogo.dataset.valorIa) actual.checked = false;
        }
        const titulo = document.querySelector('#hu11-editor-titulo');
        if (titulo) titulo.textContent = modo === 'CONFIRMAR' ? 'Confirmar valoración' :
            modo === 'MODIFICAR' ? 'Modificar valoración' : 'Registrar valoración manual';
        if (typeof dialogo.showModal === 'function') dialogo.showModal();
        else dialogo.setAttribute('open', '');
    }
    document.querySelectorAll('[data-hu11-open]').forEach(boton => boton.addEventListener('click', () => mostrarDialogo(boton.dataset.hu11Open)));
    const cerrar = () => { if (dialogo?.close) dialogo.close(); else dialogo?.removeAttribute('open'); };
    document.querySelector('#hu11-cerrar')?.addEventListener('click', cerrar);
    document.querySelector('#hu11-cancelar')?.addEventListener('click', cerrar);
    dialogo?.addEventListener('click', evento => { if (evento.target === dialogo) cerrar(); });

    if (formulario) {
        const estado = document.querySelector('#hu11-guardado');
        async function guardar() {
            clearTimeout(temporizador);
            if (enviando || definitivo) return;
            enviando = true;
            sucio = false;
            if (estado) estado.textContent = 'Guardando borrador…';
            const datos = new FormData(formulario);
            datos.set('accion', 'guardar_borrador_hu11');
            try {
                const respuesta = await fetch(formulario.action, {
                    method:'POST', body:datos, credentials:'same-origin', headers:{Accept:'application/json'},
                });
                const resultado = await respuesta.json();
                if (!respuesta.ok) throw new Error(resultado.error || 'No se pudo guardar.');
                formulario.elements.version_borrador.value = resultado.version_borrador;
                if (estado) estado.textContent = sucio ? 'Cambios sin guardar…' : 'Borrador guardado automáticamente.';
                const activo = enlaces.find(a => a.getAttribute('aria-current') === 'page');
                if (activo && activo.dataset.borrador !== '1') {
                    activo.dataset.borrador = '1';
                    const etiqueta = activo.querySelector('small');
                    if (etiqueta) etiqueta.textContent = 'Borrador';
                    const contador = document.querySelector('#hu11-contador-borradores');
                    if (contador) contador.textContent = String(Number(contador.textContent) + 1);
                }
                if (sucio) temporizador = setTimeout(guardar, 1200);
            } catch (error) {
                sucio = true;
                if (estado) estado.textContent = (error.message || 'No se pudo guardar.') + ' Conserve esta página e intente nuevamente.';
            } finally { enviando = false; }
        }
        const programar = () => {
            sucio = true;
            if (estado) estado.textContent = 'Cambios sin guardar…';
            clearTimeout(temporizador);
            temporizador = setTimeout(guardar, 1200);
        };
        formulario.addEventListener('input', programar);
        document.querySelector('#hu11-guardar')?.addEventListener('click', guardar);
        formulario.addEventListener('submit', evento => {
            if (enviando) {
                evento.preventDefault();
                if (estado) estado.textContent = 'El guardado está en curso. Vuelva a pulsar cuando termine.';
                return;
            }
            if (dialogo?.dataset.propuesta === '1') {
                const modo = formulario.querySelector('[name="modo"]:checked')?.value;
                const valor = formulario.querySelector('[name="valor"]:checked')?.value;
                if ((modo === 'CONFIRMAR' && valor !== dialogo.dataset.valorIa) ||
                    (modo === 'MODIFICAR' && valor === dialogo.dataset.valorIa)) {
                    evento.preventDefault();
                    if (estado) estado.textContent = 'Para confirmar conserve el valor IA; para modificar seleccione uno distinto.';
                    return;
                }
            }
            clearTimeout(temporizador);
            definitivo = true;
        });
        window.addEventListener('beforeunload', evento => {
            if (!definitivo && (sucio || enviando)) { evento.preventDefault(); evento.returnValue = ''; }
        });
        if (dialogo?.dataset.error === '1') {
            const modo = formulario.querySelector('[name="modo"]:checked')?.value ||
                (dialogo.dataset.propuesta === '1' ? 'MODIFICAR' : 'MANUAL');
            mostrarDialogo(modo);
        }
    }
    if (lote) lote.addEventListener('submit', evento => {
        const estado = document.querySelector('#hu11-lote-estado');
        if (sucio || enviando) {
            evento.preventDefault();
            if (estado) estado.textContent = 'Guarde primero el borrador actual y recargue la página.';
        } else if (!lote.querySelector('[name="seleccion"]:checked')) {
            evento.preventDefault();
            if (estado) estado.textContent = 'Seleccione al menos un borrador.';
        }
    });
})();
