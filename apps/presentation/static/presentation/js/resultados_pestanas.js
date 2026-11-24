// Pestañas del detalle por factor (Tabla / Matriz FODA / Perfil). Sin JavaScript se muestran las tres vistas seguidas.
(function () {
    var panel = document.getElementById('res-detalle');
    if (!panel) return;
    var pestanas = Array.prototype.slice.call(panel.querySelectorAll('[role="tab"]'));
    var vistas = Array.prototype.slice.call(panel.querySelectorAll('.res-vista'));
    function mostrar(nombre, enfocar) {
        pestanas.forEach(function (p) {
            var activa = p.dataset.vista === nombre;
            p.setAttribute('aria-selected', activa ? 'true' : 'false');
            p.tabIndex = activa ? 0 : -1;
            if (activa && enfocar) p.focus();
        });
        vistas.forEach(function (v) { v.hidden = v.id !== 'vista-' + nombre; });
    }
    pestanas.forEach(function (p, i) {
        p.addEventListener('click', function () { mostrar(p.dataset.vista); });
        p.addEventListener('keydown', function (e) {
            if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
            var sig = pestanas[(i + (e.key === 'ArrowRight' ? 1 : pestanas.length - 1)) % pestanas.length];
            mostrar(sig.dataset.vista, true);
        });
    });
    mostrar('tabla');
})();
