(() => {
    const buscar = document.querySelector('#hu11-buscar');
    const filtro = document.querySelector('#hu11-filtro');
    const links = [...document.querySelectorAll('[data-hu11-nav]')];
    const normalizar = s => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    function filtrar() {
        let visibles = 0;
        links.forEach(a => {
            const estado = filtro.value;
            const coincide = normalizar(a.dataset.busqueda).includes(normalizar(buscar.value.trim())) &&
                (!estado || (estado === 'BORRADOR' ? a.dataset.borrador === '1' : a.dataset.estado === estado));
            a.hidden = !coincide;
            if (coincide) visibles++;
        });
        const grupos = [...document.querySelectorAll('[data-grupo-hu11]')];
        grupos.forEach(g => {
            let n = g.nextElementSibling, visible = false;
            while (n && !(n.hasAttribute('data-grupo-hu11') && (g.tagName === 'P' || n.tagName === 'H3'))) {
                if (n.hasAttribute('data-hu11-nav') && !n.hidden) visible = true;
                n = n.nextElementSibling;
            }
            g.hidden = !visible;
        });
        document.querySelector('#hu11-sin-resultados').hidden = Boolean(visibles);
    }
    if (buscar && filtro) {
        buscar.addEventListener('input', filtrar);
        filtro.addEventListener('change', filtrar);
    }
    // El tipo de decisión se deduce de la valoración elegida: igual a la propuesta de IA = confirmar; distinta = modificar.
    const modo = document.querySelector('#hu11-modo');
    const nota = document.querySelector('#hu11-modo-nota');
    const radios = [...document.querySelectorAll('.hu11-form [name="valor"]')];
    function sincronizarModo() {
        if (!modo || !nota) return;
        const elegido = radios.find(r => r.checked);
        if (modo.dataset.manual === '1') { nota.textContent = elegido ? 'Valoración manual: se registra sin propuesta de IA.' : ''; return; }
        if (!elegido) { modo.value = ''; nota.textContent = 'Elija una valoración. Si coincide con la propuesta de IA, la confirma; si no, la modifica.'; return; }
        const igual = elegido.value === modo.dataset.ia;
        modo.value = igual ? 'CONFIRMAR' : 'MODIFICAR';
        nota.textContent = igual ? 'Confirma la propuesta de IA.' : 'Modifica la propuesta de IA (propuesta ' + modo.dataset.ia + ' → decisión ' + elegido.value + '). La propuesta original se conserva.';
    }
    radios.forEach(r => r.addEventListener('change', sincronizarModo));
    sincronizarModo();
    const form = document.querySelector('.hu11-form');
    const lote = document.querySelector('#hu11-lote');
    let sucio = false, enviando = false, definitivo = false, timer;
    if (form) {
        const estado = document.querySelector('#hu11-guardado');
        function programar() {
            sucio = true;
            estado.textContent = 'Cambios sin guardar…';
            clearTimeout(timer);
            timer = setTimeout(guardar, 1200);
        }
        async function guardar() {
            clearTimeout(timer);
            if (enviando || definitivo) return;
            enviando = true;
            sucio = false;
            estado.textContent = 'Guardando borrador…';
            const data = new FormData(form);
            data.set('accion', 'guardar_borrador_hu11');
            try {
                const respuesta = await fetch(form.action, {method:'POST', body:data, credentials:'same-origin', headers:{'Accept':'application/json'}});
                const resultado = await respuesta.json();
                if (!respuesta.ok) throw new Error(resultado.error || 'No se pudo guardar.');
                form.elements.version_borrador.value = resultado.version_borrador;
                estado.textContent = sucio ? 'Cambios sin guardar…' : 'Borrador guardado automáticamente.';
                const activo = links.find(a => a.getAttribute('aria-current') === 'page');
                if (activo && activo.dataset.borrador !== '1') {
                    activo.dataset.borrador = '1';
                    activo.querySelector('small').textContent += ' · Borrador';
                    document.querySelector('#hu11-contador-borradores').textContent = String(Number(document.querySelector('#hu11-contador-borradores').textContent) + 1);
                }
                if (sucio) timer = setTimeout(guardar, 1200);
            } catch (error) {
                sucio = true;
                estado.textContent = `${error.message || 'No se pudo guardar.'} Conserve esta página y vuelva a intentar o consulte de nuevo.`;
            } finally { enviando = false; }
        }
        form.addEventListener('input', programar);
        document.querySelector('#hu11-guardar').addEventListener('click', guardar);
        form.addEventListener('submit', event => {
            if (enviando) {
                event.preventDefault();
                estado.textContent = 'El guardado está en curso. Pulse de nuevo cuando termine.';
                return;
            }
            clearTimeout(timer);
            definitivo = true;
        });
        window.addEventListener('beforeunload', event => {
            if (!definitivo && (sucio || enviando)) { event.preventDefault(); event.returnValue = ''; }
        });
    }
    if (lote) lote.addEventListener('submit', event => {
        const estado = document.querySelector('#hu11-lote-estado');
        if (sucio || enviando) { event.preventDefault(); estado.textContent = 'Guarde primero el borrador actual y recargue la página.'; }
        else if (!lote.querySelector('[name="seleccion"]:checked')) {event.preventDefault(); estado.textContent = 'Seleccione al menos un borrador.';}
    });
})();
