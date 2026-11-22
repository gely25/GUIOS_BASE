/* Ficha inicial: al elegir «Otro» en Sector se escribe el sector y queda como una etiqueta (chip). */
(function () {
    var sector = document.getElementById('id_sector');
    var campo = document.getElementById('id_sector_otro');
    var chip = document.getElementById('sector-chip');
    if (!sector || !campo || !chip) { return; }
    var cuadro = document.getElementById('sector-otro-bloque');
    var texto = chip.querySelector('.chip-texto');
    var quitar = chip.querySelector('.chip-quitar');

    function mostrarChip() {
        var valor = campo.value.trim();
        if (!valor) { return; }
        texto.textContent = valor;
        chip.hidden = false;
        campo.hidden = true;
    }
    function mostrarCampo() {
        chip.hidden = true;
        campo.hidden = false;
        campo.focus();
    }
    function actualizar() {
        var esOtro = sector.value === 'Otro';
        cuadro.hidden = !esOtro;
        if (esOtro && campo.value.trim() && !campo.hidden) { mostrarChip(); }
        if (esOtro && !campo.value.trim()) { mostrarCampo(); }
    }
    sector.addEventListener('change', actualizar);
    campo.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); mostrarChip(); }
    });
    campo.addEventListener('blur', mostrarChip);
    quitar.addEventListener('click', mostrarCampo);
    cuadro.hidden = sector.value !== 'Otro';
    if (sector.value === 'Otro' && campo.value.trim()) { mostrarChip(); }
})();