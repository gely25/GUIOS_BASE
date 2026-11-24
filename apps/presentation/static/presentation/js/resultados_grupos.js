// Pagina la lista de factores de cada tarjeta FODA (Fortalezas, Debilidades, Oportunidades, Amenazas).
// Sin JavaScript se muestran todos los factores.
(function () {
    document.querySelectorAll('[data-grupo]').forEach(function (tarjeta) {
        var por = Number(tarjeta.dataset.porPagina) || 5;
        var items = Array.prototype.slice.call(tarjeta.querySelectorAll('.res-item'));
        var pie = tarjeta.querySelector('.res-grupo-pie');
        var total = Math.ceil(items.length / por);
        if (total <= 1 || !pie) return;
        var lista = tarjeta.querySelector('.res-items');
        var pag = 1;
        // Reserva el alto de una página completa para que la tarjeta no salte al cambiar de página.
        function reservar() {
            lista.style.minHeight = '';
            var alto = 0;
            items.forEach(function (i) { i.hidden = false; });
            items.slice(0, por).forEach(function (i) { alto += i.offsetHeight; });
            lista.style.minHeight = alto + 'px';
        }
        function pintar() {
            items.forEach(function (it, i) { it.hidden = Math.floor(i / por) + 1 !== pag; });
            var desde = (pag - 1) * por + 1, hasta = Math.min(pag * por, items.length);
            var nums = '';
            for (var n = 1; n <= total; n++) {
                nums += '<button type="button" class="res-pg-num' + (n === pag ? ' on' : '') + '" data-ir="' + n + '"'
                    + (n === pag ? ' aria-current="page"' : '') + ' aria-label="Página ' + n + '">' + n + '</button>';
            }
            pie.innerHTML = '<span class="res-grupo-cuenta">' + desde + '–' + hasta + ' de ' + items.length + '</span>'
                + '<nav class="res-pg" aria-label="Páginas de ' + tarjeta.querySelector('h3').firstChild.textContent.trim() + '">'
                + '<button type="button" class="res-pg-flecha" data-d="-1" aria-label="Página anterior"' + (pag === 1 ? ' disabled' : '') + '>&lsaquo;</button>'
                + nums
                + '<button type="button" class="res-pg-flecha" data-d="1" aria-label="Página siguiente"' + (pag === total ? ' disabled' : '') + '>&rsaquo;</button></nav>';
        }
        pie.addEventListener('click', function (e) {
            var b = e.target.closest('button');
            if (!b) return;
            if (b.dataset.d) pag += Number(b.dataset.d);
            else if (b.dataset.ir) pag = Number(b.dataset.ir);
            pintar();
            var activo = pie.querySelector('.res-pg-num.on');
            if (activo) activo.focus();
        });
        reservar();
        pintar();
    });
})();
