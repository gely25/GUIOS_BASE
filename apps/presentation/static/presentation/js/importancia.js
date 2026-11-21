(function () {
    'use strict';
    // Calcula la IR al instante con la misma regla que el servidor: (ID + IS) // 2.
    // El servidor vuelve a calcularla al guardar, así que esto es solo una ayuda visual.
    var formulario = document.getElementById('importancia-form');
    if (!formulario) return;
    var contador = document.getElementById('imp-relevantes');

    function actualizar(fila) {
        var marcada = fila.querySelector('input:checked');
        var sugerida = parseInt(fila.dataset.is, 10);
        if (!marcada) return;
        var ir = Math.floor((parseInt(marcada.value, 10) + sugerida) / 2);
        fila.querySelector('.imp-ir b').textContent = ir;
        fila.querySelector('.imp-estado').textContent = ir === 1 ? 'Se excluye' : 'Se evalúa';
        fila.classList.toggle('imp-excluida', ir === 1);
    }

    function recontar() {
        formulario.querySelectorAll('.imp-fila').forEach(actualizar);
        contador.textContent = formulario.querySelectorAll('.imp-fila:not(.imp-excluida)').length;
        formulario.querySelectorAll('.imp-dim').forEach(function (dim) {
            dim.querySelector('.imp-dim-n').textContent = dim.querySelectorAll('.imp-fila:not(.imp-excluida)').length;
        });
    }

    formulario.addEventListener('change', recontar);

    document.getElementById('imp-restablecer').addEventListener('click', function () {
        formulario.querySelectorAll('.imp-fila').forEach(function (fila) {
            var objetivo = fila.querySelector('input[value="' + fila.dataset.is + '"]');
            if (objetivo) objetivo.checked = true;
        });
        recontar();
    });
})();
