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
    }

    function applyFile(file) {
        clearError();
        if (!file) {
            resetSelection();
            return;
        }

        const parts = file.name.split('.');
        const ext = parts.length > 1 ? parts.pop().toLowerCase() : '';

        if (!ALLOWED_EXT.includes(ext)) {
            resetSelection();
            showError('Formato no permitido (.' + (ext || 'desconocido') + '). Usa PDF, DOCX o XLSX.');
            return;
        }

        if (file.size <= 0) {
            resetSelection();
            showError('El archivo seleccionado está vacío.');
            return;
        }

        if (file.size > MAX_BYTES) {
            resetSelection();
            showError('El archivo supera el límite máximo de 20 MB.');
            return;
        }

        fileExtBadge.textContent = ext.toUpperCase();
        fileNameEl.textContent = file.name;
        fileSizeEl.textContent = formatBytes(file.size) + ' · Listo para cargar y fragmentar';

        defaultView.style.display = 'none';
        selectedView.style.display = 'flex';
        dropZone.classList.add('has-file');
        submitBtn.disabled = false;
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
            applyFile(fileInput.files[0]);
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

        const dt = new DataTransfer();
        dt.items.add(files[0]);
        fileInput.files = dt.files;
        applyFile(files[0]);
    });

    uploadForm.addEventListener('submit', function () {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Procesando documento...';
    });

    document.querySelectorAll('.js-confirm-delete').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            if (!window.confirm('¿Eliminar este documento y sus fragmentos?')) {
                e.preventDefault();
            }
        });
    });
});