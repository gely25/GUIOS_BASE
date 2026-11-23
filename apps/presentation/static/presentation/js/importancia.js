(function () {
    'use strict';
    // Calcula la IR al instante con la misma regla que el servidor: (ID + IS) // 2.
    // El servidor vuelve a calcularla al guardar, así que esto es solo una ayuda visual.
    var formulario = document.getElementById('importancia-form');
    if (!formulario) return;

    function etiqueta(valor) { return formulario.getAttribute('data-n' + valor) || valor; }

    function texto(id, valor) {
        var el = document.getElementById(id);
        if (el) el.textContent = valor;
    }

    function plural(n, singular) { return n === 1 ? singular : singular + 's'; }

    function actualizarFila(fila) {
        var marcada = fila.querySelector('input:checked');
        var sugerida = parseInt(fila.dataset.is, 10);
        if (!marcada) return null;
        var id = parseInt(marcada.value, 10);
        var ir = Math.floor((id + sugerida) / 2);
        var excluida = ir === 1;

        var barras = fila.querySelector('.imp-barras');
        barras.className = 'imp-barras imp-l' + id;
        barras.querySelectorAll('.imp-barra').forEach(function (barra, i) {
            barra.classList.toggle('on', i + 1 <= id);
        });
        fila.querySelector('.imp-palabra').textContent = etiqueta(id);
        fila.querySelector('.imp-ir-chip').textContent = excluida ? 'Excluido' : 'IR ' + ir;
        fila.querySelector('.imp-ajustado').hidden = id === sugerida;
        fila.querySelector('.imp-estado-excluido').hidden = !excluida;
        fila.classList.toggle('imp-excluida', excluida);
        return { ir: ir, id: id, sugerida: sugerida, excluida: excluida, nombre: fila.dataset.nombre };
    }

    function recontar(ultima) {
        var activos = 0, suma = 0, grupos = { 1: [], 2: [], 3: [], 4: [] };
        formulario.querySelectorAll('.imp-panel').forEach(function (panel, i) {
            var filas = panel.querySelectorAll('.imp-fila'), evaluadas = 0;
            filas.forEach(function (fila) {
                var r = actualizarFila(fila);
                if (!r) return;
                grupos[r.ir].push(r.nombre);
                if (!r.excluida) { activos += 1; suma += r.ir; evaluadas += 1; }
            });
            var contador = formulario.querySelectorAll('.imp-tab-n')[i];
            if (contador) contador.textContent = evaluadas + '/' + filas.length;
        });
        var excluidos = grupos[1].length;
        texto('imp-relevantes', activos);
        texto('imp-excluidos-n', excluidos);
        texto('imp-excluidos-pal', plural(excluidos, 'excluido'));
        texto('imp-suma-ir', suma);
        formulario.querySelectorAll('.imp-grupo').forEach(function (grupo) {
            var nombres = grupos[grupo.dataset.ir] || [];
            grupo.querySelector('.imp-grupo-n').textContent = nombres.length;
            var lista = grupo.querySelector('.imp-grupo-nombres');
            lista.textContent = '';
            nombres.forEach(function (nombre) {
                var li = document.createElement('li');
                li.textContent = nombre;
                lista.appendChild(li);
            });
            grupo.classList.toggle('vacio', nombres.length === 0);
        });
        if (ultima) {
            var ejemplo = document.getElementById('imp-ejemplo');
            if (ejemplo) {
                var media = (ultima.id + ultima.sugerida) / 2;
                var cuenta = String(media).replace('.', ',');
                var resultado = ultima.excluida ? 'IR 1, se excluye' : 'IR ' + ultima.ir;
                ejemplo.textContent = '';
                var negrita = document.createElement('b');
                negrita.textContent = ultima.nombre + ': ';
                var strong = document.createElement('strong');
                strong.textContent = resultado;
                ejemplo.appendChild(negrita);
                ejemplo.appendChild(document.createTextNode('sugerida ' + etiqueta(ultima.sugerida) + ' (' + ultima.sugerida +
                    ') + su valoración ' + etiqueta(ultima.id) + ' (' + ultima.id + ') = ' + cuenta + ' → '));
                ejemplo.appendChild(strong);
            }
            formulario.querySelectorAll('.imp-matriz td').forEach(function (celda) {
                celda.classList.toggle('activa',
                    celda.dataset.id === String(ultima.id) && celda.dataset.is === String(ultima.sugerida));
            });
        }
    }

    formulario.addEventListener('change', function (evento) {
        var fila = evento.target.closest ? evento.target.closest('.imp-fila') : null;
        recontar(fila ? actualizarFila(fila) : null);
    });

    var restablecer = document.getElementById('imp-restablecer');
    if (restablecer) {
        restablecer.addEventListener('click', function () {
            formulario.querySelectorAll('.imp-fila').forEach(function (fila) {
                var objetivo = fila.querySelector('input[value="' + fila.dataset.is + '"]');
                if (objetivo) objetivo.checked = true;
            });
            recontar(null);
        });
    }

    // Pestañas por dimensión. Sin JavaScript se muestran todas las dimensiones seguidas.
    var pestanas = formulario.querySelectorAll('.imp-tab');
    var paneles = formulario.querySelectorAll('.imp-panel');
    function mostrar(idPanel) {
        pestanas.forEach(function (tab) {
            var activa = tab.dataset.panel === idPanel;
            tab.classList.toggle('imp-tab-activa', activa);
            tab.setAttribute('aria-selected', activa ? 'true' : 'false');
        });
        paneles.forEach(function (panel) { panel.hidden = panel.id !== idPanel; });
    }
    if (pestanas.length) {
        pestanas.forEach(function (tab) {
            tab.addEventListener('click', function () { mostrar(tab.dataset.panel); });
        });
        mostrar(pestanas[0].dataset.panel);
    }

    // Confirmación antes de pasar al siguiente paso. Sin JavaScript el formulario se envía directo.
    var dialogo = document.getElementById('imp-confirmar');
    if (dialogo && typeof dialogo.showModal === 'function') {
        formulario.addEventListener('submit', function (evento) {
            if (formulario.dataset.confirmado === '1') return;
            evento.preventDefault();
            texto('imp-m-activos', document.getElementById('imp-relevantes').textContent);
            texto('imp-m-excluidos', document.getElementById('imp-excluidos-n').textContent);
            texto('imp-m-excluidos-pal', document.getElementById('imp-excluidos-pal').textContent);
            texto('imp-m-suma', document.getElementById('imp-suma-ir').textContent);
            dialogo.showModal();
        });
        document.getElementById('imp-modal-volver').addEventListener('click', function () { dialogo.close(); });
        document.getElementById('imp-modal-confirmar').addEventListener('click', function () {
            formulario.dataset.confirmado = '1';
            dialogo.close();
            formulario.requestSubmit();
        });
    }
})();