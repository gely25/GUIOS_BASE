/* Ficha inicial: al elegir «Otro» en Sector se escribe el sector y queda como etiqueta dentro del campo. */
(function () {
    var sector = document.getElementById('id_sector');
    var campo = document.getElementById('id_sector_otro');
    var chip = document.getElementById('sector-chip');
    var control = document.getElementById('sector-control');
    var bloque = document.getElementById('sector-otro-bloque');
    var ayuda = document.getElementById('sector-ayuda');
    if (!sector || !campo || !chip || !control || !bloque) { return; }
    var texto = chip.querySelector('.chip-texto');
    var quitar = chip.querySelector('.chip-quitar');

    function mostrarChip() {
        var valor = campo.value.trim();
        if (!valor || sector.value !== 'Otro') { return; }
        texto.textContent = valor;
        chip.hidden = false;
        control.classList.add('tiene-chip');
        campo.hidden = true;
        if (ayuda) { ayuda.hidden = true; }
        bloque.hidden = true;
    }
    function mostrarCampo() {
        chip.hidden = true;
        control.classList.remove('tiene-chip');
        bloque.hidden = false;
        campo.hidden = false;
        if (ayuda) { ayuda.hidden = false; }
        campo.focus();
    }
    function actualizar() {
        if (sector.value === 'Otro') {
            if (campo.value.trim()) { mostrarChip(); } else { mostrarCampo(); }
        } else {
            chip.hidden = true;
            control.classList.remove('tiene-chip');
            bloque.hidden = true;
        }
    }
    sector.addEventListener('change', actualizar);
    campo.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); mostrarChip(); }
    });
    campo.addEventListener('blur', mostrarChip);
    quitar.addEventListener('click', function () { campo.value = ''; mostrarCampo(); });
    if (sector.value === 'Otro' && campo.value.trim()) { mostrarChip(); }
    else { bloque.hidden = sector.value !== 'Otro'; }
})();