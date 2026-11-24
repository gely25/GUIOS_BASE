/* Guía metodológica: ventana flotante con pestañas. Funciona en cualquier pantalla con menú lateral. */
(function () {
  var ventana = document.getElementById('guia-metodologica');
  if (!ventana || typeof ventana.showModal !== 'function') return;

  var pestanas = Array.prototype.slice.call(ventana.querySelectorAll('[role="tab"]'));
  var paneles = pestanas.map(function (t) { return document.getElementById(t.getAttribute('aria-controls')); });

  function mostrar(i, enfocar) {
    pestanas.forEach(function (t, k) {
      var activa = k === i;
      t.setAttribute('aria-selected', activa ? 'true' : 'false');
      t.tabIndex = activa ? 0 : -1;
      paneles[k].hidden = !activa;
    });
    if (enfocar) pestanas[i].focus();
  }

  pestanas.forEach(function (t, i) {
    t.addEventListener('click', function () { mostrar(i, false); });
    t.addEventListener('keydown', function (e) {
      var salto = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (!salto) return;
      e.preventDefault();
      mostrar((i + salto + pestanas.length) % pestanas.length, true);
    });
  });

  Array.prototype.forEach.call(document.querySelectorAll('[data-abrir-guia]'), function (b) {
    b.addEventListener('click', function () { mostrar(0, false); ventana.showModal(); });
  });
  Array.prototype.forEach.call(ventana.querySelectorAll('[data-cerrar-guia]'), function (b) {
    b.addEventListener('click', function () { ventana.close(); });
  });
  // Un clic fuera de la ventana (en el fondo oscurecido) la cierra.
  ventana.addEventListener('click', function (e) { if (e.target === ventana) ventana.close(); });
})();
