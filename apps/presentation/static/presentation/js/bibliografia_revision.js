(function () {
    'use strict';
    const selector = document.getElementById('bib-seleccionar-todas');
    const formulario = document.getElementById('bib-form-lote');
    if (!formulario) return;
    const casillas = Array.from(document.querySelectorAll('.bib-check-vinculo'));
    const contador = document.getElementById('bib-lote');
    function actualizar() {
        const seleccionadas = casillas.filter(c => c.checked).length;
        if (contador) contador.textContent = seleccionadas + ' sugerencias seleccionadas';
        if (selector) selector.textContent = seleccionadas === casillas.length ? 'Quitar selección' : 'Seleccionar sugeridas';
    }
    if (selector) selector.addEventListener('click', function () {
        const seleccionar = !casillas.every(c => c.checked);
        casillas.forEach(c => { c.checked = seleccionar; });
        actualizar();
    });
    casillas.forEach(c => c.addEventListener('change', actualizar));
    formulario.addEventListener('submit', function (evento) {
        if (!casillas.some(c => c.checked)) {
            evento.preventDefault();
            if (contador) contador.textContent = 'Seleccione al menos una sugerencia.';
        }
    });
    actualizar();
})();
