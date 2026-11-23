document.addEventListener('DOMContentLoaded', function () {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('archivoInput');
    const defaultView = document.getElementById('dropzoneDefault');
    const selectedView = document.getElementById('dropzoneSelected');
    const fileExtBadge = document.getElementById('selectedFileExt');
    const fileNameEl = document.getElementById('selectedFileName');
    const fileSizeEl = document.getElementById('selectedFileSize');
    const clearBtn = document.getElementById('clearFileBtn');
    const submitBtn = document.getElementById('submitUploadBtn');
    const clientError = document.getElementById('dropzoneClientError');
    const uploadForm = document.getElementById('uploadForm');

    if (!dropZone || !fileInput) return;

    const ALLOWED_EXT = ['pdf', 'docx', 'xlsx'];
    const MAX_BYTES = 20 * 1024 * 1024;

    function formatBytes(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    }

    function showError(msg) {
        clientError.textContent = msg;
        clientError.style.display = 'block';
    }

    function clearError() {
        clientError.textContent = '';
        clientError.style.display = 'none';
    }

    function resetSelection() {
        fileInput.value = '';
        dropZone.classList.remove('has-file');
        selectedView.style.display = 'none';
        defaultView.style.display = 'block';
        submitBtn.disabled = true;
        submitBtn.textContent = 'Cargar y fragmentar';
    }

    const listEl = document.getElementById('selectedFileList');

    function validar(file) {
        const parts = file.name.split('.');
        const ext = parts.length > 1 ? parts.pop().toLowerCase() : '';
        if (!ALLOWED_EXT.includes(ext)) return { ext: ext, error: 'formato no permitido (.' + (ext || 'desconocido') + '); use PDF, DOCX o XLSX' };
        if (file.size <= 0) return { ext: ext, error: 'el archivo está vacío' };
        if (file.size > MAX_BYTES) return { ext: ext, error: 'supera el límite de 20 MB' };
        return { ext: ext, error: '' };
    }

    function applyFiles(files) {
        clearError();
        const validos = [];
        const omitidos = [];
        Array.prototype.forEach.call(files || [], function (f) {
            const r = validar(f);
            if (r.error) { omitidos.push('«' + f.name + '»: ' + r.error); } else { validos.push(f); }
        });

        const dt = new DataTransfer();
        validos.forEach(function (f) { dt.items.add(f); });
        fileInput.files = dt.files;

        if (omitidos.length) showError('Se omitió: ' + omitidos.join('; ') + '.');
        if (!validos.length) {
            resetSelection();
            return;
        }

        const total = validos.reduce(function (acc, f) { return acc + f.size; }, 0);
        listEl.textContent = '';
        if (validos.length === 1) {
            fileExtBadge.textContent = validate_ext(validos[0]);
            fileNameEl.textContent = validos[0].name;
            fileSizeEl.textContent = formatBytes(total) + ' · Listo para cargar y fragmentar';
        } else {
            fileExtBadge.textContent = String(validos.length);
            fileNameEl.textContent = validos.length + ' documentos seleccionados';
            fileSizeEl.textContent = formatBytes(total) + ' en total · Listos para cargar y fragmentar';
            validos.forEach(function (f) {
                const li = document.createElement('li');
                li.textContent = f.name + ' · ' + formatBytes(f.size);
                listEl.appendChild(li);
            });
        }
        submitBtn.textContent = validos.length > 1 ? 'Cargar ' + validos.length + ' documentos' : 'Cargar y fragmentar';

        defaultView.style.display = 'none';
        selectedView.style.display = 'flex';
        dropZone.classList.add('has-file');
        submitBtn.disabled = false;
    }

    function validate_ext(file) {
        return validar(file).ext.toUpperCase();
    }

    dropZone.addEventListener('click', function () {
        fileInput.click();
    });

    dropZone.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            fileInput.click();
        }
    });

    clearBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        clearError();
        resetSelection();
    });

    fileInput.addEventListener('change', function () {
        if (fileInput.files && fileInput.files.length > 0) {
            applyFiles(fileInput.files);
        } else {
            resetSelection();
        }
    });

    ['dragenter', 'dragover'].forEach(function (evtName) {
        dropZone.addEventListener(evtName, function (e) {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('drag-over');
        });
    });

    ['dragleave', 'drop'].forEach(function (evtName) {
        dropZone.addEventListener(evtName, function (e) {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('drag-over');
        });
    });

    dropZone.addEventListener('drop', function (e) {
        const files = e.dataTransfer && e.dataTransfer.files;
        if (!files || files.length === 0) return;

        applyFiles(files);
    });

    uploadForm.addEventListener('submit', function () {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Procesando documentos...';
    });

    document.querySelectorAll('.js-confirm-delete').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            if (!window.confirm('¿Eliminar este documento y sus fragmentos?')) {
                e.preventDefault();
            }
        });
    });
});

// Panel lateral de fragmentos: "Ver más", cerrar con Esc y llevar al fragmento destacado.
document.addEventListener('DOMContentLoaded', function () {
    const panel = document.getElementById('panel-fragmentos');
    if (!panel) return;

    document.body.classList.add('cdp-abierto');

    panel.querySelectorAll('.cdp-frag').forEach(function (frag) {
        const texto = frag.querySelector('[data-texto]');
        const boton = frag.querySelector('[data-mas]');
        if (!texto || !boton) return;
        texto.classList.add('recortado');
        if (texto.scrollHeight > texto.clientHeight + 2) {
            boton.hidden = false;
        } else {
            texto.classList.remove('recortado');
        }
        boton.addEventListener('click', function () {
            const abierto = texto.classList.toggle('recortado');
            boton.textContent = abierto ? 'Ver más' : 'Ver menos';
        });
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && panel.dataset.cerrar) {
            window.location.href = panel.dataset.cerrar;
        }
    });

    const destacado = panel.querySelector('.cdp-frag.destacado');
    if (destacado) destacado.scrollIntoView({ block: 'center' });
});
/* Resumen antes de «Siguiente» y apertura de sugerencias */
(function () {
    'use strict';
    var enlace = document.querySelector('.paso-nav a[data-confirmar]');
    var resumen = enlace && document.getElementById(enlace.getAttribute('data-confirmar'));
    if (resumen && typeof resumen.showModal === 'function') {
        enlace.addEventListener('click', function (e) { e.preventDefault(); resumen.showModal(); });
    }
    document.querySelectorAll('[data-cerrar-dialogo]').forEach(function (b) {
        b.addEventListener('click', function () { b.closest('dialog').close(); });
    });
})();

/* Renombrar documento */
(function () {
    'use strict';
    var ren = document.getElementById('cd-renombrar');
    if (ren && typeof ren.showModal === 'function') {
        document.querySelectorAll('.js-renombrar').forEach(function (b) {
            b.addEventListener('click', function () {
                document.getElementById('cd-ren-id').value = b.getAttribute('data-id');
                var campo = document.getElementById('cd-ren-nombre');
                campo.value = b.getAttribute('data-nombre');
                ren.showModal();
                campo.focus();
            });
        });
    }
})();

/* Versión de la carga: etiquetas para elegir o una nueva */
(function () {
    'use strict';
    var nueva = document.getElementById('cd-ver-nueva');
    var texto = document.getElementById('version');
    if (!nueva || !texto) { return; }
    function sync() {
        texto.hidden = !nueva.checked;
        texto.disabled = !nueva.checked;
        if (nueva.checked) { texto.focus(); }
    }
    document.querySelectorAll('.cd-chip input').forEach(function (i) { i.addEventListener('change', sync); });
})();
