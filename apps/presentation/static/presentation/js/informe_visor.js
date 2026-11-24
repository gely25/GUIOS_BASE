/* Visor del informe: una hoja a la vez, escalada al ancho disponible, con miniaturas.
   Sin JavaScript se ven las cuatro hojas una debajo de otra. */
(function () {
  var visor = document.getElementById('iv-visor');
  var contenedor = document.getElementById('iv-hojas');
  if (!visor || !contenedor) return;
  var hojas = Array.prototype.slice.call(contenedor.querySelectorAll('[data-hoja]'));
  if (!hojas.length) return;

  var ANCHO = 794;
  var nav = visor.querySelector('.iv-nav');
  var posicion = document.getElementById('iv-posicion');
  var minis = document.getElementById('iv-minis');
  var titulos = ['1 · Resumen', '2 · Resultados', '3 · Detalle', '4 · Respaldo'];
  var actual = 0;

  visor.classList.add('iv-js');
  nav.hidden = false;
  minis.hidden = false;

  var cuerpo = document.createElement('div');
  cuerpo.className = 'iv-cuerpo';
  contenedor.parentNode.insertBefore(cuerpo, contenedor);
  cuerpo.appendChild(minis);
  cuerpo.appendChild(contenedor);

  var marco = document.createElement('div');
  marco.className = 'iv-marco';
  contenedor.insertBefore(marco, hojas[0]);
  hojas.forEach(function (h) { marco.appendChild(h); });

  var botones = hojas.map(function (hoja, i) {
    var b = document.createElement('button');
    b.type = 'button';
    b.setAttribute('role', 'tab');
    var vista = document.createElement('span');
    vista.className = 'iv-mini-marco';
    var copia = hoja.cloneNode(true);
    copia.removeAttribute('data-hoja');
    copia.setAttribute('aria-hidden', 'true');
    vista.appendChild(copia);
    var texto = document.createElement('span');
    texto.textContent = titulos[i] || ('Hoja ' + (i + 1));
    b.appendChild(vista);
    b.appendChild(texto);
    b.addEventListener('click', function () { ir(i); });
    minis.appendChild(b);
    return { boton: b, vista: vista, copia: copia };
  });

  var fijo = window.matchMedia('(min-width: 1101px)');

  function escalar() {
    var hoja = hojas[actual];
    var alto = hoja.offsetHeight;
    var factor = contenedor.clientWidth / ANCHO;
    if (fijo.matches) {
      contenedor.style.height = '';
      factor = Math.min(factor, contenedor.clientHeight / alto);
    }
    factor = Math.max(0.3, Math.min(1, factor));
    hoja.style.transform = 'scale(' + factor + ')';
    marco.style.width = Math.round(ANCHO * factor) + 'px';
    marco.style.height = Math.round(alto * factor) + 'px';
    if (!fijo.matches) contenedor.style.height = marco.style.height;
    botones.forEach(function (b) {
      var w = b.vista.clientWidth;
      if (!w) return;
      var f = w / ANCHO;
      b.copia.style.transform = 'scale(' + f + ')';
      b.vista.style.height = Math.round(w * 1123 / ANCHO) + 'px';
    });
  }

  function ir(i) {
    actual = Math.max(0, Math.min(hojas.length - 1, i));
    hojas.forEach(function (h, k) { h.classList.toggle('is-activa', k === actual); });
    posicion.textContent = 'Hoja ' + (actual + 1) + ' de ' + hojas.length;
    botones.forEach(function (b, k) {
      b.boton.classList.toggle('on', k === actual);
      b.boton.setAttribute('aria-selected', k === actual ? 'true' : 'false');
    });
    nav.querySelector('[data-ir="-1"]').disabled = actual === 0;
    nav.querySelector('[data-ir="1"]').disabled = actual === hojas.length - 1;
    escalar();
  }

  Array.prototype.forEach.call(nav.querySelectorAll('[data-ir]'), function (b) {
    b.addEventListener('click', function () { ir(actual + parseInt(b.getAttribute('data-ir'), 10)); });
  });
  window.addEventListener('resize', escalar);
  ir(0);
})();
