(function () {
  var el = document.getElementById('rs-datos');
  if (!el) return;
  var datos = JSON.parse(el.textContent);
  var lista = document.getElementById('rs-lista');
  var detalle = document.getElementById('rs-detalle');
  var soloPend = document.getElementById('rs-solo-pend');
  var sel = document.getElementById('rs-sel');
  var btnGuardar = document.getElementById('rs-guardar');
  var txt = document.getElementById('rs-barra-txt');
  var elegido = {};   // id subfactor -> valor "val:frag:sim"
  var ninguna = {};   // id subfactor -> true
  var actual = null, tab = 0;

  function h(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function esc(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function estado(d) {
    if (d.guardados.length) return 'con';
    if (elegido[d.id]) return 'sug';
    return 'sin';
  }
  var ROT = { con: 'Con respaldo', sug: 'Elegido', sin: 'Pendiente' };

  function marcar(texto, comunes) {
    var frag = document.createDocumentFragment();
    if (!comunes.length) { frag.appendChild(document.createTextNode(texto)); return frag; }
    var re = new RegExp('(' + comunes.map(esc).join('|') + ')[a-záéíóúñü]*', 'gi');
    var ult = 0, m;
    while ((m = re.exec(texto))) {
      if (m.index > ult) frag.appendChild(document.createTextNode(texto.slice(ult, m.index)));
      frag.appendChild(h('mark', '', m[0]));
      ult = m.index + m[0].length;
      if (m[0].length === 0) re.lastIndex++;
    }
    if (ult < texto.length) frag.appendChild(document.createTextNode(texto.slice(ult)));
    return frag;
  }

  function pintarLista() {
    lista.textContent = '';
    var ultimoFactor = null, visibles = 0;
    datos.forEach(function (d) {
      var e = estado(d);
      if (soloPend.checked && e === 'con') return;
      visibles++;
      if (d.factor !== ultimoFactor) { lista.appendChild(h('li', 'rs-grupo', d.factor)); ultimoFactor = d.factor; }
      var li = h('li');
      var b = h('button', 'rs-item'); b.type = 'button';
      if (actual === d.id) b.setAttribute('aria-current', 'true');
      b.appendChild(h('span', 't', d.texto.length > 110 ? d.texto.slice(0, 110) + '…' : d.texto));
      b.appendChild(h('span', 'rs-est rs-est--' + e, ROT[e]));
      b.addEventListener('click', function () { actual = d.id; tab = 0; pintarTodo(); });
      li.appendChild(b); lista.appendChild(li);
    });
    if (!visibles) lista.appendChild(h('li', 'rs-vacio', 'No hay subfactores para mostrar.')).style.padding = '14px';
  }

  function pintarDetalle() {
    detalle.textContent = '';
    var d = datos.filter(function (x) { return x.id === actual; })[0];
    if (!d) { detalle.appendChild(h('p', 'rs-vacio', 'Elija un subfactor de la lista para ver sus fuentes.')); return; }
    detalle.appendChild(h('div', 'rs-factor', d.factor));
    detalle.appendChild(h('h2', '', d.texto));
    if (d.guardados.length) {
      d.guardados.forEach(function (g) {
        detalle.appendChild(h('div', 'rs-guardado', 'Ya tiene respaldo: ' + g.documento + ' · ' + g.ubicacion));
      });
      detalle.appendChild(h('p', 'rs-vacio', 'Este respaldo se revisa en el paso 4. Para cambiarlo use «Ver fragmentos» en la carga documental.'));
      return;
    }
    if (!d.candidatos.length) {
      detalle.appendChild(h('p', 'rs-vacio', 'No se encontraron pasajes parecidos en sus documentos. Puede vincular uno a mano desde «Ver fragmentos» en la carga documental.'));
      return;
    }
    var tabs = h('div', 'rs-tabs'); tabs.setAttribute('role', 'tablist');
    d.candidatos.forEach(function (c, i) {
      var t = h('button', 'rs-tab', 'Fuente ' + (i + 1)); t.type = 'button';
      t.setAttribute('role', 'tab'); t.setAttribute('aria-selected', String(i === tab));
      t.addEventListener('click', function () { tab = i; pintarDetalle(); });
      tabs.appendChild(t);
    });
    detalle.appendChild(tabs);
    var c = d.candidatos[tab];
    var cab = h('div', 'rs-fuente-cab');
    cab.appendChild(h('strong', '', c.documento));
    cab.appendChild(h('span', '', '· ' + c.ubicacion));
    cab.appendChild(h('span', 'rs-rel rs-rel--' + c.nivel, 'Relevancia ' + c.nivel));
    detalle.appendChild(cab);
    var ex = h('div', 'rs-extracto');
    ex.appendChild(marcar(c.extracto, c.comunes));
    detalle.appendChild(ex);
    var completo = false;
    if (c.comunes.length) detalle.appendChild(h('div', 'rs-comunes', 'Coincide con: ' + c.comunes.map(function (x) { return x + '…'; }).join(', ')));
    var ac = h('div', 'rs-acciones');
    var usar = h('button', 'rs-btn rs-btn-prim'); usar.type = 'button';
    var elegidaEsta = elegido[d.id] === c.valor;
    usar.textContent = elegidaEsta ? '✓ Usada como respaldo' : 'Usar como respaldo';
    if (elegidaEsta) usar.className = 'rs-btn rs-btn-on';
    usar.addEventListener('click', function () {
      if (elegido[d.id] === c.valor) delete elegido[d.id]; else { elegido[d.id] = c.valor; delete ninguna[d.id]; }
      pintarTodo();
    });
    ac.appendChild(usar);
    var ning = h('button', 'rs-btn rs-btn-sec', 'Ninguna sirve'); ning.type = 'button';
    ning.addEventListener('click', function () { delete elegido[d.id]; ninguna[d.id] = true; pintarTodo(); });
    ac.appendChild(ning);
    var ver = h('button', 'rs-btn rs-btn-sec', 'Ver texto completo'); ver.type = 'button';
    ver.addEventListener('click', function () {
      completo = !completo;
      ex.textContent = '';
      ex.appendChild(marcar(completo ? c.texto : c.extracto, c.comunes));
      ex.classList.toggle('rs-largo', completo);
      ver.textContent = completo ? 'Ver menos' : 'Ver texto completo';
    });
    ac.appendChild(ver);
    var otro = h('a', 'rs-btn rs-btn-sec', 'Ver en el documento'); otro.href = c.url;
    ac.appendChild(otro);
    detalle.appendChild(ac);
    if (ninguna[d.id]) detalle.appendChild(h('p', 'rs-vacio', 'Marcado como «ninguna sirve»: este subfactor quedará sin respaldo.'));
    detalle.appendChild(h('div', 'rs-flujo', 'Así se mostrará en el paso 4 y en el informe: «Fuente: ' + c.documento + ' · ' + c.ubicacion + '», con relevancia ' + c.nivel + '.'));
  }

  function actualizarForm() {
    sel.textContent = '';
    var n = 0;
    Object.keys(elegido).forEach(function (k) {
      var i = document.createElement('input');
      i.type = 'hidden'; i.name = 'sel'; i.value = elegido[k]; sel.appendChild(i); n++;
    });
    txt.textContent = n + (n === 1 ? ' respaldo elegido' : ' respaldos elegidos');
    btnGuardar.disabled = n === 0;
  }

  function pintarTodo() { pintarLista(); pintarDetalle(); actualizarForm(); }

  soloPend.addEventListener('change', pintarTodo);
  var altas = document.getElementById('rs-aceptar-altas');
  if (altas) altas.addEventListener('click', function () {
    datos.forEach(function (d) {
      if (!d.guardados.length && d.candidatos.length && d.candidatos[0].nivel === 'alta') {
        elegido[d.id] = d.candidatos[0].valor; delete ninguna[d.id];
      }
    });
    pintarTodo();
  });

  var primero = datos.filter(function (d) { return !d.guardados.length; })[0] || datos[0];
  if (primero) actual = primero.id;
  pintarTodo();
})();