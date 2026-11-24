// Paso 4: modales «Completar información faltante» y «Subir otro documento». Solo presentación: las respuestas se guardan con el servicio de preguntas existente.
(() => {
    const h = (tag, props = {}, ...hijos) => {
        const el = document.createElement(tag);
        for (const [k, v] of Object.entries(props)) {
            if (k === 'class') el.className = v;
            else if (k === 'text') el.textContent = v;
            else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
            else if (v !== false && v != null) el.setAttribute(k, v === true ? '' : v);
        }
        hijos.flat().forEach(c => { if (c != null) el.append(c); });
        return el;
    };

    // ---- cierre común y modal de subida ----
    document.querySelectorAll('dialog.hu11-modal').forEach(d => {
        d.addEventListener('click', e => { if (e.target === d) d.close(); });
        d.querySelectorAll('[data-hu11-cerrar]').forEach(b => b.addEventListener('click', () => d.close()));
    });
    const subir = document.querySelector('#hu11-subir');
    if (subir && typeof subir.showModal === 'function') {
        document.querySelectorAll('[data-hu11-subir]').forEach(b => b.addEventListener('click', () => subir.showModal()));
        const archivo = document.querySelector('#hu11-archivo');
        archivo.addEventListener('change', () => {
            const n = archivo.files.length;
            document.querySelector('#hu11-archivos-n').textContent = n ? (n === 1 ? archivo.files[0].name : n + ' archivos elegidos') : '';
        });
    }

    // ---- información faltante ----
    const dlg = document.querySelector('#hu11-info');
    const datos = document.querySelector('#hu11-faltantes');
    if (!dlg || !datos || typeof dlg.showModal !== 'function') return;
    const SUBS = JSON.parse(datos.textContent || '[]');
    const lista = document.querySelector('#hu11-qlist');
    const foco = (dlg.querySelector('[name="valoracion"]') || {}).value;
    const OPC = ['Correo', 'Teléfono', 'Chat en línea', 'Presencial', 'Foro / comunidad'];
    const anio = new Date().getFullYear();
    const SUG = {
        tiempo: [['1 hora hábil', 1, 'horas hábiles'], ['4 horas hábiles', 4, 'horas hábiles'], ['1 día hábil', 1, 'días hábiles'], ['3 días hábiles', 3, 'días hábiles']],
        monto: [['Sin costo', 0, 'pago único'], ['US$ 500 / año', 500, 'por año'], ['US$ 1000 / año', 1000, 'por año']],
        numero: [['10', 10], ['50', 50], ['100', 100], ['300', 300]],
        fecha: [['Este año', anio + '-01-01'], ['Año pasado', (anio - 1) + '-01-01']],
        sino: [], opciones: [['Correo y chat', ['Correo', 'Chat en línea']], ['Todos los canales', OPC.slice()]],
        texto: [['No hay documentación, se estima por experiencia'], ['Consta en un documento que aún no se cargó']],
    };
    const ETQ = { tiempo: 'Tiempo', monto: 'Monto', numero: 'Número', fecha: 'Fecha', sino: 'Sí / No', opciones: 'Opciones', texto: 'Texto' };

    // El tipo se infiere solo del enunciado de la pregunta (sin la descripción del subfactor).
    function tipo(texto) {
        let t = texto.toLowerCase();
        const i = t.indexOf('sobre este subfactor');
        if (i >= 0) t = t.slice(0, i);
        if (/cu[aá]nto (tiempo|demora|tarda|dura)|tiempo de|plazo|duraci[oó]n/.test(t)) return 'tiempo';
        if (/cu[aá]nto (paga|cuesta|cost|invier)|costo|precio|presupuesto|tarifa/.test(t)) return 'monto';
        if (/cu[aá]ntos|cu[aá]ntas|n[uú]mero de|cantidad/.test(t)) return 'numero';
        if (/cu[aá]ndo|fecha|desde qu[eé]|hasta qu[eé]/.test(t)) return 'fecha';
        if (/qu[eé] (canales|medios|formatos|sistemas|idiomas)/.test(t)) return 'opciones';
        if (/^¿(existe|hay|cuenta|tiene|dispone|se |est[aá]|es |son |posee|ofrece|cumple)/.test(t)) return 'sino';
        return 'texto';
    }

    const E = {};
    const preguntas = [];
    SUBS.forEach((s, si) => s.preguntas.forEach(p => {
        p.tipo = tipo(p.texto); p.sub = si;
        E[p.id] = p.respuesta === 'No lo sé' ? { nose: true } : p.respuesta ? { d: p.respuesta } : {};
        preguntas.push(p);
    }));

    function compuesta(p) {
        const e = E[p.id] || {};
        if (e.nose) return 'No lo sé';
        const d = (e.d || '').trim(), t = p.tipo, n = e.n;
        let v = '';
        if (t === 'tiempo' && n !== undefined && n !== '') v = n + ' ' + (e.u || 'horas hábiles');
        else if (t === 'monto' && n !== undefined && n !== '') v = 'US$ ' + n + ' ' + (e.u || 'por año');
        else if (t === 'numero' && n !== undefined && n !== '') v = String(n);
        else if (t === 'fecha' && n) v = new Date(n + 'T00:00').toLocaleDateString('es-EC');
        else if (t === 'sino' && e.sn) v = e.sn;
        else if (t === 'opciones' && e.op && e.op.length) v = e.op.join(', ');
        return v ? (d ? v + ' — ' + d : v) : d;
    }

    function ctrl(p) {
        const e = E[p.id], t = p.tipo;
        const num = (ph, tipoIn = 'number', extra = {}) => h('input', { type: tipoIn, placeholder: ph, 'data-f': 'n', value: e.n ?? '', ...extra });
        const sel = (opts, def) => h('select', { 'data-f': 'u', 'aria-label': 'Unidad' }, opts.map(o => h('option', { text: o, selected: (e.u || def) === o })));
        if (t === 'tiempo') return h('div', { class: 'hu11-inl' }, num('4', 'number', { min: 0, 'aria-label': 'Cantidad' }), sel(['minutos', 'horas hábiles', 'días hábiles', 'semanas'], 'horas hábiles'));
        if (t === 'monto') return h('div', { class: 'hu11-inl' }, h('span', { text: 'US$' }), num('1200', 'number', { min: 0, step: '0.01', 'aria-label': 'Monto' }), sel(['por año', 'por mes', 'pago único'], 'por año'));
        if (t === 'numero') return h('div', { class: 'hu11-inl' }, num('300', 'number', { min: 0, 'aria-label': 'Cantidad' }));
        if (t === 'fecha') return h('div', { class: 'hu11-inl' }, num('', 'date', { 'aria-label': 'Fecha' }));
        if (t === 'sino') return h('div', { class: 'hu11-seg' }, ['Sí', 'No', 'Parcialmente'].map(v => h('button', { type: 'button', 'data-sn': v, class: e.sn === v ? 'on' : '', 'aria-pressed': e.sn === v ? 'true' : 'false', text: v })));
        if (t === 'opciones') return h('div', { class: 'hu11-seg' }, OPC.map(v => h('button', { type: 'button', 'data-op': v, class: (e.op || []).includes(v) ? 'on' : '', 'aria-pressed': (e.op || []).includes(v) ? 'true' : 'false', text: v })));
        return null;
    }

    function bloque(p, idx) {
        const e = E[p.id], sg = SUG[p.tipo] || [];
        const caja = h('div', { class: 'hu11-qc', 'data-q': p.id },
            h('div', { class: 'hu11-qh' }, h('label', { text: idx + '. ' + p.texto, for: 'hu11-d-' + p.id }), h('span', { class: 'hu11-tag', text: ETQ[p.tipo] })),
            ctrl(p),
            sg.length ? h('div', { class: 'hu11-sug' }, h('span', { text: 'Sugerencias:' }), sg.map((x, i) => h('button', { type: 'button', 'data-sg': i, text: x[0] }))) : null,
            h('textarea', { id: 'hu11-d-' + p.id, 'data-f': 'd', rows: p.tipo === 'texto' ? 3 : 2, maxlength: 2000, placeholder: p.tipo === 'texto' ? 'Su respuesta…' : 'Detalle o fuente (opcional)…', text: e.d || '' }),
            h('div', { class: 'hu11-seg' }, h('button', { type: 'button', 'data-nose': '1', class: 'hu11-no' + (e.nose ? ' on' : ''), 'aria-pressed': e.nose ? 'true' : 'false', text: 'No lo sé' })),
            h('p', { class: 'hu11-prev', hidden: true }, 'Se guardará como: ', h('b')));
        caja.querySelector('textarea').value = e.d || '';
        pintar(caja, p);
        return caja;
    }
    function pintar(caja, p) {
        const c = compuesta(p), prev = caja.querySelector('.hu11-prev');
        caja.classList.toggle('hu11-hecha', Boolean(c));
        prev.hidden = !c;
        prev.querySelector('b').textContent = c;
    }

    const acordeones = [];
    function armar() {
        lista.textContent = '';
        let ultimo = '';
        SUBS.forEach((s, si) => {
            if (s.factor !== ultimo) { lista.append(h('p', { class: 'hu11-fac', text: s.factor })); ultimo = s.factor; }
            const cuerpo = h('div', { class: 'hu11-ac-b' }, s.preguntas.map((p, i) => bloque(p, i + 1)));
            const insignia = h('span', { class: 'hu11-okb' });
            const cab = h('button', { type: 'button', class: 'hu11-ac-h', 'aria-expanded': 'false' }, h('span', { class: 'hu11-ch', text: '›', 'aria-hidden': 'true' }), h('span', { class: 'hu11-ac-s', text: s.subfactor }), insignia);
            const ac = h('div', { class: 'hu11-ac' }, cab, cuerpo);
            cab.addEventListener('click', () => alternar(ac));
            ac._insignia = insignia; ac._sub = s;
            acordeones.push(ac); lista.append(ac);
        });
        const primero = acordeones.find(a => a._sub.vid === Number(foco)) || acordeones.find(a => a._sub.preguntas.some(p => !compuesta(p)));
        if (primero) alternar(primero, true);
        refrescar();
    }
    function alternar(ac, abrir) {
        const v = abrir === undefined ? !ac.classList.contains('open') : abrir;
        ac.classList.toggle('open', v);
        ac.querySelector('.hu11-ac-h').setAttribute('aria-expanded', v ? 'true' : 'false');
    }
    let soloPend = false;
    function refrescar() {
        let hechas = 0;
        acordeones.forEach(ac => {
            const n = ac._sub.preguntas.filter(p => compuesta(p)).length, tot = ac._sub.preguntas.length;
            hechas += n;
            ac._insignia.textContent = n + '/' + tot + (n === tot ? ' ✓' : '');
            ac._insignia.classList.toggle('full', n === tot);
        });
        document.querySelector('#hu11-cnt').textContent = hechas + ' de ' + preguntas.length + ' respondidas';
        document.querySelector('#hu11-barra-resp').style.width = (preguntas.length ? hechas * 100 / preguntas.length : 0) + '%';
    }
    function filtrar() {
        acordeones.forEach(ac => { ac.hidden = soloPend && ac._sub.preguntas.every(p => compuesta(p)); });
    }
    function rehacer(caja) {
        const p = preguntas.find(x => String(x.id) === caja.dataset.q);
        const idx = [...caja.parentElement.children].indexOf(caja) + 1;
        caja.replaceWith(bloque(p, idx));
        refrescar();
    }

    lista.addEventListener('input', ev => {
        const t = ev.target, caja = t.closest('[data-q]');
        if (!caja || !t.dataset.f) return;
        const e = E[caja.dataset.q];
        e[t.dataset.f] = t.value; e.nose = false;
        caja.querySelector('.hu11-no').classList.remove('on');
        pintar(caja, preguntas.find(x => String(x.id) === caja.dataset.q));
        refrescar();
    });
    lista.addEventListener('click', ev => {
        const b = ev.target.closest('button');
        const caja = b && b.closest('[data-q]');
        if (!caja) return;
        const p = preguntas.find(x => String(x.id) === caja.dataset.q), e = E[p.id];
        if (b.dataset.sn) { e.sn = b.dataset.sn; e.nose = false; }
        else if (b.dataset.op) { const s = new Set(e.op || []); s.has(b.dataset.op) ? s.delete(b.dataset.op) : s.add(b.dataset.op); e.op = [...s]; e.nose = false; }
        else if (b.dataset.sg !== undefined) {
            const x = SUG[p.tipo][+b.dataset.sg]; e.nose = false;
            if (p.tipo === 'texto') e.d = x[0]; else if (p.tipo === 'opciones') e.op = x[1].slice(); else { e.n = x[1]; if (x[2]) e.u = x[2]; }
        }
        else if (b.dataset.nose) { E[p.id] = e.nose ? {} : { nose: true }; }
        else return;
        rehacer(caja);
    });
    document.querySelector('#hu11-exp').addEventListener('click', ev => {
        const abrir = acordeones.some(a => !a.hidden && !a.classList.contains('open'));
        acordeones.forEach(a => alternar(a, abrir));
        ev.currentTarget.textContent = abrir ? 'Contraer todo' : 'Expandir todo';
    });
    document.querySelector('#hu11-solo').addEventListener('click', ev => {
        soloPend = !soloPend;
        ev.currentTarget.textContent = soloPend ? 'Ver todos' : 'Solo sin responder';
        filtrar();
    });
    document.querySelector('#hu11-nosabe').addEventListener('click', () => {
        preguntas.forEach(p => { if (!compuesta(p)) E[p.id] = { nose: true }; });
        armar(); filtrar();
    });
    document.querySelector('#hu11-info-form').addEventListener('submit', () => {
        const envio = preguntas.map(p => ({ p, c: compuesta(p) })).filter(x => x.c && x.c !== (x.p.respuesta || ''))
            .map(x => ({ id: x.p.id, respuesta: x.c, version: x.p.version }));
        document.querySelector('#hu11-respuestas').value = JSON.stringify(envio);
    });

    armar();
    document.querySelectorAll('[data-hu11-info]').forEach(b => b.addEventListener('click', () => dlg.showModal()));
    if (dlg.dataset.abrir === '1' && SUBS.length) dlg.showModal();
})();
