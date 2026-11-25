// Actualización bibliográfica (HU02): refresca el progreso de la búsqueda sin bloquear la página.
(function () {
    'use strict';
    var panel = document.getElementById('bib-progreso');
    if (!panel || panel.dataset.terminado === '1') { return; }

    var url = panel.dataset.estadoUrl;
    var barra = panel.querySelector('.bib-barra');
    var relleno = panel.querySelector('.bib-barra-relleno');
    function campo(nombre, valor) {
        var el = panel.querySelector('[data-campo="' + nombre + '"]');
        if (el) { el.textContent = valor; }
    }

    function consultar() {
        fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' })
            .then(function (r) { if (!r.ok) { throw new Error(r.status); } return r.json(); })
            .then(function (d) {
                relleno.style.width = d.progreso + '%';
                barra.setAttribute('aria-valuenow', d.progreso);
                campo('progreso', d.progreso);
                campo('completadas', d.por_estado.COMPLETADA);
                campo('fallidas', d.por_estado.FALLIDA);
                campo('pendientes', d.por_estado.PENDIENTE + d.por_estado.EN_CURSO);
                if (d.terminado) { window.location.reload(); } else { setTimeout(consultar, 4000); }
            })
            .catch(function () { setTimeout(consultar, 10000); });
    }
    setTimeout(consultar, 4000);
}());
