(function () {
    'use strict';
    const dialogo = document.getElementById('formulario-usuario');
    if (!dialogo) return;
    if (typeof dialogo.showModal === 'function') {
        dialogo.close();
        dialogo.showModal();
        dialogo.addEventListener('cancel', function (evento) {
            evento.preventDefault();
            const cancelar = dialogo.querySelector('a.usuarios-enlace');
            if (cancelar) window.location.assign(cancelar.href);
        });
    }
    dialogo.querySelectorAll('.usuarios-toggle').forEach(function (boton) {
        const campo = document.getElementById(boton.getAttribute('aria-controls'));
        if (!campo) return;
        boton.hidden = false;
        boton.addEventListener('click', function () {
            const visible = campo.type === 'text';
            campo.type = visible ? 'password' : 'text';
            boton.textContent = visible ? 'Mostrar' : 'Ocultar';
            boton.setAttribute('aria-pressed', String(!visible));
        });
    });
})();
