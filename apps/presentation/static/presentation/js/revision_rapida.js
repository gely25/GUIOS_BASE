(() => {
    const raiz = document.getElementById('rv');
    const datos = document.getElementById('rv-datos');
    if (!raiz || !datos) return;
    const filas = JSON.parse(datos.textContent);
    const editable = raiz.dataset.editable === '1';
    const url = raiz.dataset.url, eid = raiz.dataset.eid;
    const csrf = raiz.querySelector('[name=csrfmiddlewaretoken]').value;
    const ESC = {1: 'No cumple', 2: 'No sé', 3: 'Parcial', 4: 'Cumple'};
    const COMPLETO = {1: 'No cumple el requisito', 2: 'Desconozco / No sé si cumple', 3: 'Cumple parcialmente el requisito', 4: 'Cumple el requisito'};
    const COLOR = {'Tecnológica': '#2f5d7c', 'Organizacional': '#a0661f', 'Económica': '#6a4c93'};
    const color = d => COLOR[d] || '#4a525a';
    const TAM = {at: 6, li: 10, ok: 10};
    const pag = {at: 1, li: 1, ok: 1};
    let tab = 'at', fAt = 'todos', dFilt = 'todas', ultimo = null;
    const dims = [...new Set(filas.map(r => r.dim))];
    filas.forEach(r => { r.sel = true; r.v = r.ok ? r.val : null; r.j = ''; });
    const PEND = ['ANALISIS_PENDIENTE', 'PROPUESTA_HABILITADA'];
    let corriendo = false;
    // categoría de un subfactor que necesita atención
    const limpiar = s => (s || '').replace(/\s*Fuentes? citadas?:[^.]*\.?/gi, '').replace(/\b(las |la )?fuentes?\s+(E:\d+\s*(,|y|e)?\s*)+/gi, 'los fragmentos ').replace(/\bE:\d+\b/g, 'el fragmento').replace(/(el fragmento)(,?\s*(y|e)?\s*el fragmento)+/g, 'los fragmentos').trim();
    const cat = r => r.ia === 2 ? 'noSe' : r.ia != null ? '' : !r.nev ? 'sinEv'
        : PEND.includes(r.est) ? 'sinAn' : 'noSe';

    const esc = t => String(t == null ? '' : t).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
    const tipo = r => r.ok ? 'ok' : (r.ia != null && r.ia !== 2 ? 'li' : 'at');
    const porId = id => filas.find(r => r.id === Number(id));
    const q = id => document.getElementById(id);
    function aviso(texto, bueno) {
        const m = q('rv-msg');
        m.textContent = texto || '';
        m.hidden = !texto;
        m.classList.toggle('ok', Boolean(bueno));
        if (texto) m.scrollIntoView({block: 'nearest'});
    }
    async function enviar(datosForm) {
        const f = new FormData();
        f.append('csrfmiddlewaretoken', csrf);
        f.append('etapa', 'validacion');
        f.append('evaluacion', eid);
        datosForm.forEach(([k, v]) => f.append(k, v));
        const resp = await fetch(url, {method: 'POST', body: f, credentials: 'same-origin', headers: {'Accept': 'application/json'}});
        let cuerpo = {};
        try { cuerpo = await resp.json(); } catch (e) { /* respuesta no JSON */ }
        if (!resp.ok) throw new Error(cuerpo.error || 'No se pudo guardar. Recargue la página e intente de nuevo.');
        return cuerpo;
    }
    const dimTag = r => `<small><span class="rv-dtag" style="color:${color(r.dim)}"><i style="background:${color(r.dim)}"></i>${esc(r.dim)}</span> › ${esc(r.fac)}</small>`;
    const estilo = r => `border-left-color:${color(r.dim)}`;
    const chipIA = r => `<span class="rv-chip" title="${r.ia != null ? COMPLETO[r.ia] : ''}">${r.ia != null ? 'Propuesta de la IA: ' + ESC[r.ia] : 'Sin propuesta'}</span>`;

    function abrirEvidencia(id) {
        const r = porId(id);
        ultimo = document.activeElement;
        let h = `<h2 id="rv-dlg-t">${esc(r.text)}</h2><p class="rv-meta"><span class="rv-dtag" style="color:${color(r.dim)}"><i style="background:${color(r.dim)}"></i>${esc(r.dim)}</span> › ${esc(r.fac)}</p>${chipIA(r)}`;
        r.fuentes.forEach(f => {
            h += `<h3>${f.s === 'Declaración del decisor' ? 'Declaración del decisor' : 'Fragmento que respalda la propuesta'}</h3><div class="rv-quote">${esc(f.b)} <mark>${esc(f.m)}</mark> ${esc(f.a)}</div><p class="rv-meta">${esc(f.s)}</p>`;
        });
        if (!r.fuentes.length) h += '<p class="rv-meta">Todavía no hay evidencia evaluada por la IA para este subfactor.</p>';
        if (r.jia) h += `<h3>Justificación de la IA</h3><p>${esc(limpiar(r.jia))}</p>`;
        if (r.ok && r.just) h += `<h3>Su decisión${r.fecha ? ' · ' + esc(r.fecha) : ''}</h3><p>${esc(r.just)}</p>`;
        h += '<div class="rv-acts"><button class="rv-btn rv-btn--primary" type="button" data-a="cerrar">Cerrar</button></div>';
        q('rv-dlg-b').innerHTML = h;
        q('rv-dlg').showModal();
    }
    function abrirReapertura(id) {
        const r = porId(id);
        ultimo = document.activeElement;
        q('rv-dlg-b').innerHTML = `<form method="post" action="${esc(url)}"><input type="hidden" name="csrfmiddlewaretoken" value="${esc(csrf)}"><input type="hidden" name="etapa" value="validacion"><input type="hidden" name="evaluacion" value="${esc(eid)}"><input type="hidden" name="valoracion" value="${r.id}"><input type="hidden" name="version" value="${esc(r.version)}"><input type="hidden" name="accion" value="reabrir_hu11">
        <h2 id="rv-dlg-t">Editar valoración</h2><p class="rv-meta">${esc(r.text)}</p>
        <h3>Decisión registrada: ${ESC[r.val]}${r.fecha ? ' · ' + esc(r.fecha) : ''}</h3><p>${esc(r.just)}</p>
        <p class="rv-meta" style="margin-top:14px">Para cambiarla hay que reabrir la valoración. La decisión anterior queda en el historial y los resultados ya calculados se retiran hasta que vuelva a confirmar.</p>
        <h3>Motivo de la reapertura (obligatorio)</h3><textarea name="motivo" rows="3" maxlength="4000" required></textarea>
        <label style="display:flex;gap:10px;align-items:flex-start;margin-top:12px;font-size:14px"><input type="checkbox" name="confirmar_reapertura" value="1" required> <span>Confirmo que deseo invalidar esta decisión y los resultados derivados.</span></label>
        <div class="rv-acts"><button class="rv-btn" type="button" data-a="cerrar">Cancelar</button><button class="rv-btn rv-btn--primary" type="submit">Reabrir valoración</button></div></form>`;
        q('rv-dlg').showModal();
    }
    q('rv-dlg').addEventListener('click', e => { if (e.target === e.currentTarget) e.currentTarget.close(); });
    q('rv-dlg').addEventListener('close', () => { if (ultimo && ultimo.focus) ultimo.focus(); });

    function filaAtencion(r) {
        let aviso_ia = '';
        const c = cat(r);
        if (c === 'sinAn') aviso_ia = `<span class="rv-chip">${corriendo ? 'La IA lo está analizando…' : 'Pendiente de análisis de la IA'}</span>`;
        let h = `<div class="rv-rw" style="${estilo(r)}"><div class="rv-t">${dimTag(r)}<p>${esc(r.text)}</p>${aviso_ia}</div>`;
        if (editable) {
            h += '<div class="rv-seg" role="group" aria-label="Valoración">';
            for (let n = 1; n <= 4; n++) h += `<button type="button" title="${COMPLETO[n]}" data-a="val" data-id="${r.id}" data-n="${n}" aria-pressed="${r.v === n}">${ESC[n]}${r.ia === n ? '<span class="ia" aria-label="propuesta de IA"></span>' : ''}</button>`;
            h += '</div>';
        }
        if (r.fuentes.length) h += `<button class="rv-lnk" type="button" data-a="ev" data-id="${r.id}">Ver evidencia</button>`;
        return h + '</div>';
    }
    const cambiada = r => r.v != null && r.v !== r.ia;
    function filaLista(r) {
        const sel = r.v != null ? r.v : r.ia;
        return `<div class="rv-rw" style="${estilo(r)}">${editable ? `<input type="checkbox" data-a="sel" data-id="${r.id}"${r.sel && !cambiada(r) ? ' checked' : ''}${cambiada(r) ? ' disabled' : ''} aria-label="Aceptar este subfactor">` : ''}<div class="rv-t">${dimTag(r)}<p>${esc(r.text)}</p></div><div class="rv-seg" role="group" aria-label="Valoración (la IA propuso ${ESC[r.ia]})">${[1, 2, 3, 4].map(n => `<button type="button" title="${COMPLETO[n]}"${editable ? ` data-a="vali" data-id="${r.id}" data-n="${n}"` : ' disabled'} aria-pressed="${sel === n}">${ESC[n]}${r.ia === n ? '<span class="ia" aria-label="propuesta de IA"></span>' : ''}</button>`).join('')}</div><button class="rv-lnk" type="button" data-a="ev" data-id="${r.id}">Ver evidencia</button>${editable ? `<button class="rv-btn rv-btn--primary" type="button" data-a="okia" data-id="${r.id}">${cambiada(r) ? 'Confirmar cambio' : 'Confirmar'}</button>` : ''}</div>`;
    }
    function filaOk(r) {
        return `<div class="rv-rw" style="${estilo(r)}"><div class="rv-t">${dimTag(r)}<p>${esc(r.text)}</p></div><span class="rv-chip rv-chip--n">${ESC[r.val]}</span><button class="rv-lnk" type="button" data-a="ev" data-id="${r.id}">Ver decisión</button>${raiz.dataset.reabrir === '1' ? `<button class="rv-lnk" type="button" data-a="edit" data-id="${r.id}">Editar</button>` : ''}</div>`;
    }
    function pintar() {
        const c = {at: 0, li: 0, ok: 0};
        filas.forEach(r => c[tipo(r)]++);
        q('rv-n-at').textContent = c.at; q('rv-n-li').textContent = c.li; q('rv-n-ok').textContent = c.ok;
        q('rv-resumen').textContent = `${c.ok} de ${filas.length} confirmados`;
        q('rv-bar').style.width = Math.round(c.ok * 100 / filas.length) + '%';
        q('rv-map').innerHTML = dims.map(d => `<div class="rv-map-d"><b style="color:${color(d)}">${esc(d)}</b><div class="rv-sq">${filas.filter(r => r.dim === d).map(r => { const k = tipo(r); return `<i class="${k === 'ok' ? 'ok' : k === 'at' ? 'at' : ''}" title="${esc(r.fac)}"></i>`; }).join('')}</div></div>`).join('');
        document.querySelectorAll('.rv-tab').forEach(t => t.setAttribute('aria-selected', String(t.dataset.tab === tab)));
        let dh = `<span>Dimensión</span><button class="rv-dchip" type="button" data-a="d" data-d="todas" aria-pressed="${dFilt === 'todas'}">Todas<small>${filas.length - c.ok} por revisar</small></button>`;
        dims.forEach(d => { dh += `<button class="rv-dchip" type="button" data-a="d" data-d="${esc(d)}" aria-pressed="${dFilt === d}"><i style="background:${color(d)}"></i>${esc(d)}<small>${filas.filter(r => r.dim === d && !r.ok).length}</small></button>`; });
        q('rv-dimbar').innerHTML = dh;
        let lista = filas.filter(r => tipo(r) === tab && (dFilt === 'todas' || r.dim === dFilt));
        const nTodas = lista.length;
        let h = '', nNoSe = 0, nSinEv = 0, nSinAn = 0;
        if (tab === 'at') {
            lista.forEach(r => { const k = cat(r); if (k === 'noSe') nNoSe++; else if (k === 'sinAn') nSinAn++; else if (k === 'sinEv') nSinEv++; });
            if (fAt !== 'todos') lista = lista.filter(r => cat(r) === fAt);
        }
        const paginas = Math.max(1, Math.ceil(lista.length / TAM[tab]));
        if (pag[tab] > paginas) pag[tab] = paginas;
        if (!lista.length) {
            h = (tab === 'at' && nTodas > 0 ? '<div class="rv-filt"><button class="rv-fchip" type="button" data-a="f" data-f="todos" aria-pressed="false">Quitar filtro</button></div>' : '')
              + `<p class="rv-empty">${tab === 'at' ? (nTodas > 0 ? 'Ningún subfactor coincide con este filtro.' : (dFilt === 'todas' ? 'No queda nada que necesite tu atención.' : 'No queda nada por atender en esta dimensión.')) : tab === 'li' ? 'No hay subfactores listos para aceptar.' : 'Todavía no has confirmado ninguno.'}</p>`;
        } else {
            if (tab === 'at') {
                h += '<p class="rv-hint">Sin evidencia suficiente o con una propuesta dudosa. Elige tu valoración y queda confirmada. El punto naranja marca lo que propuso la IA.</p>';
                h += `<div class="rv-filt" role="group" aria-label="Filtrar"><button class="rv-fchip" type="button" data-a="f" data-f="todos" aria-pressed="${fAt === 'todos'}">Todos<small>${nTodas}</small></button><button class="rv-fchip" type="button" data-a="f" data-f="noSe" aria-pressed="${fAt === 'noSe'}">Sin propuesta<small>${nNoSe}</small></button><button class="rv-fchip" type="button" data-a="f" data-f="sinEv" aria-pressed="${fAt === 'sinEv'}">Sin evidencia<small>${nSinEv}</small></button>${nSinAn ? `<button class="rv-fchip" type="button" data-a="f" data-f="sinAn" aria-pressed="${fAt === 'sinAn'}">Pendientes de la IA<small>${nSinAn}</small></button>` : ''}</div>`;
            }
            if (tab === 'li') {
                const todas = lista.every(r => r.sel);
                h += `<p class="rv-hint">La IA encontró evidencia y propuso una valoración. ${editable ? 'Acepta todas de una vez, o confirma una por una. Si no estás de acuerdo, cambia el valor en la fila y confirma el cambio.' : ''}</p>${editable ? `<label class="rv-selall"><input type="checkbox" data-a="all"${todas ? ' checked' : ''} id="rv-selall"> Seleccionar las ${lista.length} listas</label>` : ''}`;
            }
            const desde = (pag[tab] - 1) * TAM[tab], parte = lista.slice(desde, desde + TAM[tab]);
            parte.forEach(r => { h += tab === 'at' ? filaAtencion(r) : tab === 'li' ? filaLista(r) : filaOk(r); });
            h += `<div class="rv-pager"><span>${desde + 1}–${desde + parte.length} de ${lista.length}</span><div class="g"><button class="rv-btn" type="button" data-a="prev"${pag[tab] <= 1 ? ' disabled' : ''}>‹ Anterior</button><span>Página ${pag[tab]} de ${paginas}</span><button class="rv-btn" type="button" data-a="next"${pag[tab] >= paginas ? ' disabled' : ''}>Siguiente ›</button></div></div>`;
        }
        const enfocado = document.activeElement && document.activeElement.dataset && document.activeElement.dataset.a === 'just' ? document.activeElement.dataset.id : null;
        q('rv-panel').innerHTML = h;
        if (enfocado) { const i = q('rv-panel').querySelector(`input[data-a="just"][data-id="${enfocado}"]`); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }
        const sa = q('rv-selall');
        if (sa) { const n = lista.filter(r => r.sel).length; sa.indeterminate = n > 0 && n < lista.length; }
        const nSel = filas.filter(r => tipo(r) === 'li' && r.sel && !cambiada(r) && (dFilt === 'todas' || r.dim === dFilt)).length;
        const acc = q('rv-acc');
        if (acc) { acc.textContent = `Aceptar propuestas de IA seleccionadas (${nSel})`; acc.disabled = nSel === 0; }
        q('rv-foot').textContent = c.at > 0 ? `${c.at} por revisar con tu criterio · ${c.li} listas para aceptar` : (c.li > 0 ? `${c.li} listas para aceptar` : 'Todo confirmado');
    }

    document.addEventListener('click', async e => {
        const b = e.target.closest('#rv [data-a], #rv-dlg [data-a]');
        if (!b) return;
        const a = b.dataset.a, id = b.dataset.id;
        if (a === 'cerrar') { q('rv-dlg').close(); return; }
        if (a === 'ev') { abrirEvidencia(id); return; }
        if (a === 'edit') { abrirReapertura(id); return; }
        if (a === 'just') return;
        if (a === 'val') {
            const r = porId(id);
            r.v = Number(b.dataset.n);
            const fila = b.closest('.rv-rw');
            document.querySelectorAll(`#rv [data-a="val"][data-id="${r.id}"]`).forEach(x => { x.setAttribute('aria-pressed', String(x === b)); x.disabled = true; });
            if (fila) fila.classList.add('rv-rw--hecho');
            try {
                const res = await enviar([['accion', 'confirmar_rapida_hu11'], ['valoracion', r.id], ['valor', r.v], ['version', r.version]]);
                r.ok = true; r.val = r.v; r.just = res.justificacion || ''; r.version = res.version; r.fecha = '';
                aviso('');
                await new Promise(f => setTimeout(f, 650));
            } catch (err) { aviso(err.message); r.v = null; }
        }
        else if (a === 'okia') {
            const r = porId(id);
            b.disabled = true;
            try {
                if (cambiada(r)) {
                    const res = await enviar([['accion', 'confirmar_rapida_hu11'], ['valoracion', r.id], ['valor', r.v], ['version', r.version]]);
                    r.ok = true; r.val = r.v; r.just = res.justificacion || ''; r.version = res.version; r.fecha = '';
                } else {
                    const res = await enviar([['accion', 'aceptar_propuestas_hu11'], ['seleccion', r.id + ':' + r.version]]);
                    r.ok = true; r.val = r.ia; r.just = 'Propuesta de la IA aceptada tras revisar la evidencia.'; r.version = res.versiones[r.id] || r.version; r.fecha = '';
                }
                aviso('');
            } catch (err) { aviso(err.message); b.disabled = false; return; }
        }
        else if (a === 'vali') { const r = porId(id); r.v = Number(b.dataset.n); if (cambiada(r)) r.sel = false; }
        else if (a === 'sel') porId(id).sel = b.checked;
        else if (a === 'all') filas.forEach(r => { if (tipo(r) === 'li' && (dFilt === 'todas' || r.dim === dFilt)) r.sel = b.checked; });
        else if (a === 'd') { dFilt = b.dataset.d; pag.at = pag.li = pag.ok = 1; }
        else if (a === 'f') { fAt = b.dataset.f; pag.at = 1; }
        else if (a === 'prev') pag[tab]--;
        else if (a === 'next') pag[tab]++;
        pintar();
    });
    document.querySelectorAll('.rv-tab').forEach(t => t.addEventListener('click', () => { tab = t.dataset.tab; pag[tab] = 1; pintar(); }));
    const acc = q('rv-acc');
    if (acc) acc.addEventListener('click', async () => {
        const elegidas = filas.filter(r => tipo(r) === 'li' && r.sel && !cambiada(r) && (dFilt === 'todas' || r.dim === dFilt));
        if (!elegidas.length) return;
        acc.disabled = true;
        try {
            const res = await enviar([['accion', 'aceptar_propuestas_hu11'], ...elegidas.map(r => ['seleccion', r.id + ':' + r.version])]);
            elegidas.forEach(r => { r.ok = true; r.val = r.ia; r.just = 'Propuesta de la IA aceptada tras revisar la evidencia.'; r.version = res.versiones[r.id] || r.version; });
            aviso(`Se aceptaron ${res.aceptadas} propuestas de la IA.`, true);
        } catch (err) { aviso(err.message); }
        pintar();
    });
    pintar();

    // Análisis con IA en segundo plano: la IA recorre los subfactores con evidencia mientras el decisor revisa.
    const caja = q('rv-ia');
    const objetivos = JSON.parse(q('rv-objetivos').textContent || '[]');
    async function analizar(o) {
        const r = porId(o.vid);
        const res = await enviar([['accion', 'analizar_ia_hu11'], ['valoracion', o.vid]]);
        r.est = res.estado;
        r.ia = res.valor_ia && res.jia && res.jia.trim() ? res.valor_ia : null;
        r.jia = res.jia || '';
        r.version = res.version;
        r.fuentes = res.fuentes || [];
        return res;
    }
    // Errores de una sola respuesta de la IA: se reintenta el subfactor y, si persiste, se deja pendiente y se sigue.
    const LOCAL = /datos inválidos|no terminó|formato inválido|contexto supera|supera el límite|preguntas inválidas/i;
    // Subfactores analizados a la vez. Cada uno ya consulta en paralelo a todos los proveedores
    // configurados; si alguno alcanza su límite (429), la cola espera y se reanuda sola.
    const PARALELO = 6;
    const ESPERA_LIMITE = 60;
    let esperasLimite = 0;
    const dormir = ms => new Promise(f => setTimeout(f, ms));
    async function correr() {
        const pendientes = objetivos.filter(o => { const r = porId(o.vid); return r && !r.ok && r.ia == null && PEND.includes(r.est); });
        if (!pendientes.length) { caja.hidden = true; return; }
        corriendo = true;
        q('rv-ia-retry').hidden = true;
        let hechos = 0, fatal = null, i = 0;
        const base = objetivos.length - pendientes.length;
        const progreso = () => { q('rv-ia-t').innerHTML = `La IA está analizando la evidencia: <b>${base + hechos} de ${objetivos.length}</b>. Puedes ir revisando mientras tanto.`; };
        progreso();
        async function trabajador() {
            while (!fatal && i < pendientes.length) {
                const o = pendientes[i++];
                const r = porId(o.vid);
                if (r.ok) { hechos++; continue; }
                for (let intento = 0; intento < 2; intento++) {
                    try { await analizar(o); break; }
                    catch (err) {
                        if (!LOCAL.test(err.message)) { fatal = err.message; break; }
                    }
                }
                if (fatal) return;
                hechos++;
                progreso();
                pintar();
            }
        }
        await Promise.all(Array.from({length: PARALELO}, trabajador));
        const saturada = fatal && /estado HTTP 5\d\d/i.test(fatal);
        if (fatal && (/límite de solicitudes/i.test(fatal) || saturada) && esperasLimite < 8) {
            esperasLimite++;
            for (let s = saturada ? 15 : ESPERA_LIMITE; s > 0; s--) {
                q('rv-ia-t').textContent = `${saturada ? 'La API de IA está saturada' : 'La API de IA alcanzó su límite de uso'}. Se reanuda sola en ${s} s (${base + hechos} de ${objetivos.length} analizados).`;
                await dormir(1000);
            }
            return correr();
        }
        corriendo = false;
        if (fatal) {
            q('rv-ia-t').textContent = `El análisis con IA se detuvo después de ${base + hechos} de ${objetivos.length}: ${fatal}`;
            q('rv-ia-retry').hidden = false;
        } else {
            // Totales de toda la evaluación (no solo de esta tanda), con los mismos criterios que las pestañas.
            const conEvidencia = filas.filter(r => !r.ok && r.nev);
            const listas = filas.filter(r => tipo(r) === 'li').length;
            const sinLeer = conEvidencia.filter(r => r.ia == null && PEND.includes(r.est)).length;
            const criterio = conEvidencia.filter(r => tipo(r) === 'at').length - sinLeer;
            q('rv-ia-t').textContent = `La IA terminó: ${listas} listas para aceptar y ${criterio} con evidencia que necesitan tu criterio` + (sinLeer ? `. ${sinLeer} no se pudieron analizar (puedes reintentar o valorarlos tú).` : '.');
            if (sinLeer) q('rv-ia-retry').hidden = false;
        }
        pintar();
    }
    if (caja.dataset.auto === '1' && objetivos.length) {
        q('rv-ia-retry').addEventListener('click', correr);
        correr();
    }
})();
