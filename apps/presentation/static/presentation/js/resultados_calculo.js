// Pagina la tabla de cálculo de PM/FODA. Todas las filas siguen en el formulario, solo se ocultan las de otras páginas.
(function () {
    document.querySelectorAll('table[data-paginar]').forEach(function (tabla) {
        var tam = Number(tabla.dataset.paginar) || 6;
        var filas = Array.prototype.slice.call(tabla.querySelectorAll('tbody tr'));
        if (filas.length <= tam) return;
        var total = Math.ceil(filas.length / tam), pag = 1;
        var barra = document.createElement('div');
        barra.className = 'res-pager';
        tabla.closest('.admin-table-container').insertAdjacentElement('afterend', barra);
        function pintar() {
            filas.forEach(function (f, i) { f.hidden = Math.floor(i / tam) + 1 !== pag; });
            var pend = filas.filter(function (f) { var s = f.querySelector('select'); return s && !s.value; }).length;
            barra.innerHTML = '<span>' + ((pag - 1) * tam + 1) + '–' + Math.min(pag * tam, filas.length) + ' de ' + filas.length + ' factores'
                + (pend ? ' · <b>' + pend + ' sin alcance elegido</b>' : '') + '</span>'
                + '<span><button type="button" data-p="-1"' + (pag === 1 ? ' disabled' : '') + '>‹ Anterior</button> Página ' + pag + ' de ' + total
                + ' <button type="button" data-p="1"' + (pag === total ? ' disabled' : '') + '>Siguiente ›</button></span>';
        }
        barra.addEventListener('click', function (e) {
            var b = e.target.closest('button[data-p]');
            if (!b || b.disabled) return;
            pag += Number(b.dataset.p);
            pintar();
        });
        tabla.addEventListener('change', pintar);
        pintar();
    });
})();
