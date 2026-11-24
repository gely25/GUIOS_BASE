(() => {
    const raiz = document.querySelector('#hu11-ana');
    const datos = document.querySelector('#hu11-ia-obj');
    if (!raiz || !datos) return;
    const objetivos = JSON.parse(datos.textContent || '[]');
    const csrf = raiz.querySelector('[name=csrfmiddlewaretoken]').value;
    const el = id => document.querySelector(id);
    let detener = false, hechos = 0, errores = 0, con = 0, vacios = 0;
    el('#hu11-ana-manual').addEventListener('click', () => { detener = true; window.location.href = raiz.dataset.destino; });
    function progreso() {
        el('#hu11-ana-barra').style.width = (objetivos.length ? Math.round(100 * hechos / objetivos.length) : 100) + '%';
        el('#hu11-ana-n').textContent = hechos + ' de ' + objetivos.length + ' subfactores analizados';
    }
    async function analizar(o) {
        const f = new FormData();
        f.set('csrfmiddlewaretoken', csrf); f.set('etapa', 'validacion'); f.set('evaluacion', raiz.dataset.eid);
        f.set('valoracion', o.vid); f.set('accion', 'analizar_ia_hu11');
        const r = await fetch(raiz.dataset.url, {method: 'POST', body: f, credentials: 'same-origin', headers: {'Accept': 'application/json'}});
        let j = {};
        try { j = await r.json(); } catch (e) { j = {error: 'Respuesta inesperada del servidor.'}; }
        if (!r.ok) throw new Error(j.error || 'No se pudo analizar.');
        return j;
    }
    (async () => {
        for (const o of objetivos) {
            if (detener) return;
            el('#hu11-ana-s').textContent = 'Localizando fragmentos para «' + o.nombre + '». Aún no hay una sugerencia de valoración.';
            try {
                const j = await analizar(o);
                if (j.valor_ia) con++; else vacios++;
            } catch (e) {
                errores++;
                el('#hu11-ana-e').hidden = false;
                el('#hu11-ana-e').textContent = e.message;
                if (/no está configurado/.test(e.message)) break;
            }
            hechos++;
            progreso();
        }
        if (detener) return;
        el('#hu11-spin').hidden = true;
        el('#hu11-ana-t').textContent = 'Análisis terminado';
        el('#hu11-ana-s').textContent = con + ' con sugerencia de IA · ' + vacios + ' con información por completar' + (errores ? ' · ' + errores + ' con error' : '') + '.';
        el('#hu11-ana-manual').textContent = 'Ir a la revisión';
        if (!errores) setTimeout(() => { if (!detener) window.location.href = raiz.dataset.destino; }, 1500);
    })();
})();