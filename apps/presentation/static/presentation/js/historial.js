/* Historial de evaluaciones: búsqueda, filtro por estado y paginación en el navegador.
   Sin JavaScript la tabla muestra todas las filas. */
(function () {
  var panel = document.getElementById('historial-expedientes');
  if (!panel) return;

  var porPagina = parseInt(panel.getAttribute('data-por-pagina'), 10) || 6;
  var filas = Array.prototype.slice.call(panel.querySelectorAll('tr[data-fila]'));
  var buscar = document.getElementById('historial-buscar');
  var estado = document.getElementById('historial-estado');
  var contador = document.getElementById('historial-contador');
  var paginador = document.getElementById('historial-paginador');
  var etiquetaPagina = document.getElementById('historial-pagina');
  var vacio = document.getElementById('historial-sin-coincidencias');
  var btnAnterior = paginador.querySelector('[data-pag="anterior"]');
  var btnSiguiente = paginador.querySelector('[data-pag="siguiente"]');
  var pagina = 1;

  function normalizar(texto) {
    return (texto || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  }

  function visibles() {
    var q = normalizar(buscar.value.trim());
    var e = estado.value;
    return filas.filter(function (fila) {
      var coincideTexto = !q || normalizar(fila.getAttribute('data-buscar')).indexOf(q) !== -1;
      var coincideEstado = !e || fila.getAttribute('data-estado') === e;
      return coincideTexto && coincideEstado;
    });
  }

  function pintar() {
    var lista = visibles();
    var paginas = Math.max(1, Math.ceil(lista.length / porPagina));
    if (pagina > paginas) pagina = paginas;
    var desde = (pagina - 1) * porPagina;
    var hasta = desde + porPagina;

    filas.forEach(function (fila) { fila.hidden = true; });
    lista.slice(desde, hasta).forEach(function (fila) { fila.hidden = false; });

    vacio.hidden = lista.length > 0;
    if (lista.length === 0) {
      contador.textContent = 'Mostrando 0 evaluaciones';
    } else {
      contador.textContent = 'Mostrando ' + (desde + 1) + '–' + Math.min(hasta, lista.length) +
        ' de ' + lista.length + ' evaluaciones';
    }
    paginador.hidden = lista.length <= porPagina;
    etiquetaPagina.textContent = 'Página ' + pagina + ' de ' + paginas;
    btnAnterior.disabled = pagina <= 1;
    btnSiguiente.disabled = pagina >= paginas;
  }

  buscar.addEventListener('input', function () { pagina = 1; pintar(); });
  estado.addEventListener('change', function () { pagina = 1; pintar(); });
  btnAnterior.addEventListener('click', function () { pagina -= 1; pintar(); });
  btnSiguiente.addEventListener('click', function () { pagina += 1; pintar(); });

  pintar();
})();
