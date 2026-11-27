param(
    [ValidateSet('Configurar', 'Plan', 'Migrar', 'Django', 'Worker', 'Busquedas', 'Tamanos', 'Cuotas')]
    [string]$Accion = 'Configurar',
    [string]$Perfil
)

$raiz = Split-Path -Parent $PSScriptRoot
$python = Join-Path $raiz 'venv\Scripts\python.exe'
if (-not $Perfil) { $Perfil = Join-Path $raiz 'config\ia-local.json' }
$rutaPerfil = (Resolve-Path -LiteralPath $Perfil -ErrorAction Stop).Path
$config = Get-Content -LiteralPath $rutaPerfil -Raw -Encoding UTF8 | ConvertFrom-Json

if (@($config.proveedores.PSObject.Properties).Count -ne 2 -or
    -not $config.proveedores.gemini -or -not $config.proveedores.cloudflare) {
    throw 'El perfil local debe incluir solo Gemini y Cloudflare.'
}
$gemini = $config.proveedores.gemini.politica
$cloudflare = $config.proveedores.cloudflare.politica
if ($gemini.rpm -gt 15 -or $gemini.tpm -gt 250000 -or
    $cloudflare.rpm -gt 300 -or $cloudflare.unidades_diarias -gt 10000) {
    throw 'El perfil supera los topes confirmados o publicados para el piloto.'
}

$politicas = @{}
$perfiles = @{}
foreach ($nombre in 'gemini', 'cloudflare') {
    $datos = $config.proveedores.$nombre
    $unidad = [string]$datos.unidad
    if (-not $unidad -or $politicas.ContainsKey($unidad)) {
        throw 'Gemini y Cloudflare requieren identificadores distintos de unidad de cuota.'
    }
    $politicas[$unidad] = $datos.politica
    $perfiles["$nombre/$($datos.modelo)"] = $datos.perfil
    $prefijo = "GUIOS_AI_$($nombre.ToUpperInvariant())"
    $operaciones = $datos.perfil.PSObject.Properties |
        Where-Object { $_.Value.validado -eq $true } | ForEach-Object Name
    [Environment]::SetEnvironmentVariable("$($prefijo)_UNIDAD_CUOTA", $unidad, 'Process')
    [Environment]::SetEnvironmentVariable("$($prefijo)_OPERACIONES", ($operaciones -join ','), 'Process')
}
foreach ($nombre in 'COHERE', 'GROQ', 'OPENROUTER') {
    [Environment]::SetEnvironmentVariable("GUIOS_AI_$($nombre)_OPERACIONES", ' ', 'Process')
}

$env:GUIOS_AI_AUTORIZACION_GRATUITA = Join-Path $raiz $config.autorizacion
$env:GUIOS_AI_POLITICAS_CUOTA = ConvertTo-Json -InputObject $politicas -Depth 8 -Compress
$env:GUIOS_AI_MODELOS_ADICIONALES = '{}'
$env:GUIOS_AI_POLITICAS_MODELO = '{}'
$env:GUIOS_AI_PERFILES_OPERACION = ConvertTo-Json -InputObject $perfiles -Depth 8 -Compress
$env:GUIOS_AI_TRABAJADORES_LOTE = [string]$config.trabajadores_lote
$env:GUIOS_AI_TIMEOUT = [string]$config.timeout
$env:GUIOS_AI_COOLDOWN = [string]$config.cooldown
$env:GUIOS_AI_ESPERA_SEGUNDOS = [string]$config.espera_segundos
$env:GUIOS_AI_RESERVA_SEGUNDOS = [string]$config.reserva_segundos
$env:GUIOS_AI_REUSO_SEGUNDOS = [string]$config.reuso_segundos

Push-Location -LiteralPath $raiz
try {
    if ($Accion -in @('Plan', 'Migrar', 'Cuotas')) {
        & $python -m benchmarks.local_ia $Accion.ToLowerInvariant()
    } elseif ($Accion -eq 'Tamanos') {
        & $python -m benchmarks.local_ia tamanos --perfil $rutaPerfil
    } else {
        $verificar = @('-m', 'benchmarks.local_ia', 'verificar', '--perfil', $rutaPerfil)
        if ($Accion -in @('Django', 'Worker', 'Busquedas')) { $verificar += '--base' }
        & $python @verificar
        if ($LASTEXITCODE -eq 0) {
            $huella = (Get-FileHash -LiteralPath $rutaPerfil -Algorithm SHA256).Hash.Substring(0, 12)
            Write-Host "Perfil operativo $huella"
            if ($Accion -eq 'Django') { & $python manage.py runserver 127.0.0.1:8000 }
            if ($Accion -eq 'Worker') { & $python manage.py procesar_hu09 }
            if ($Accion -eq 'Busquedas') { & $python manage.py procesar_busquedas }
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "La accion $Accion fallo con codigo $LASTEXITCODE." }
} finally {
    Pop-Location
}
