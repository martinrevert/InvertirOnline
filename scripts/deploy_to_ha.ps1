<#
.SYNOPSIS
    Despliega la integración custom_components/invertironline hacia Home Assistant por Samba o SSH.

.EXAMPLE
    .\scripts\deploy_to_ha.ps1
    .\scripts\deploy_to_ha.ps1 -Method ssh -SshTarget root@192.168.86.28
#>

param(
    [ValidateSet("samba", "ssh")]
    [string]$Method,
    [string]$SambaHost,
    [string]$SambaShare = "config",
    [string]$SambaUser,
    [string]$SambaPass,
    [string]$SshTarget,
    [string]$SshConfigPath = "/config",
    [string]$HaUrl,
    [string]$HaToken,
    [switch]$RestartHA
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$SourceDir = Join-Path $RepoRoot "custom_components\invertironline"
$EnvFile = Join-Path $RepoRoot ".deploy.env"

if (-not (Test-Path $SourceDir)) {
    throw "No se encontró la carpeta de la integración en: $SourceDir"
}

# Cargar .deploy.env si existe (sin sobreescribir parámetros explícitos)
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $key = $parts[0].Trim()
            $val = $parts[1].Trim()
            switch ($key) {
                "DEPLOY_METHOD" { if (-not $Method) { $Method = $val } }
                "SAMBA_HOST"    { if (-not $SambaHost) { $SambaHost = $val } }
                "SAMBA_SHARE"   { if ($SambaShare -eq "config" -and $val) { $SambaShare = $val } }
                "SAMBA_USER"    { if (-not $SambaUser) { $SambaUser = $val } }
                "SAMBA_PASS"    { if (-not $SambaPass) { $SambaPass = $val } }
                "SSH_TARGET"    { if (-not $SshTarget) { $SshTarget = $val } }
                "SSH_CONFIG_PATH" { if ($SshConfigPath -eq "/config" -and $val) { $SshConfigPath = $val } }
                "HA_URL"        { if (-not $HaUrl) { $HaUrl = $val } }
                "HA_TOKEN"      { if (-not $HaToken) { $HaToken = $val } }
            }
        }
    }
}

if (-not $Method) { $Method = "samba" }

if ($Method -eq "samba") {
    if (-not $SambaHost) {
        throw "Falta SAMBA_HOST. Configúralo en .deploy.env o pásalo con -SambaHost."
    }

    $UncRoot = "\\$SambaHost\$SambaShare"
    $TargetDir = Join-Path $UncRoot "custom_components\invertironline"

    Write-Host "Conectando a Samba: $UncRoot ..." -ForegroundColor Cyan
    if ($SambaUser -and $SambaPass) {
        net use $UncRoot /user:$SambaUser $SambaPass | Out-Null
    } else {
        net use $UncRoot | Out-Null
    }

    if (-not (Test-Path $UncRoot)) {
        throw "No se pudo acceder a $UncRoot. Verifica la IP, credenciales y que el add-on Samba esté activo."
    }

    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

    Write-Host "Sincronizando archivos hacia $TargetDir ..." -ForegroundColor Cyan
    # Robocopy devuelve códigos 0..7 en ejecuciones exitosas
    robocopy $SourceDir $TargetDir /MIR /XD __pycache__ .pytest_cache /XF *.pyc *.pyo /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "Robocopy falló con código de salida $LASTEXITCODE"
    }

    Write-Host "Despliegue Samba completado correctamente." -ForegroundColor Green
}
elseif ($Method -eq "ssh") {
    if (-not $SshTarget) {
        throw "Falta SSH_TARGET. Configúralo en .deploy.env o pásalo con -SshTarget."
    }

    $RemoteParent = "$SshConfigPath/custom_components"
    Write-Host "Creando directorio remoto y copiando por SCP a $SshTarget..." -ForegroundColor Cyan
    ssh $SshTarget "mkdir -p $RemoteParent"
    scp -r $SourceDir "${SshTarget}:$RemoteParent/"
    Write-Host "Despliegue SSH completado correctamente." -ForegroundColor Green
}

if ($HaUrl -and $HaToken) {
    $Headers = @{
        "Authorization" = "Bearer $HaToken"
        "Content-Type"  = "application/json"
    }
    if ($RestartHA) {
        Write-Host "Reiniciando Home Assistant vía API REST..." -ForegroundColor Yellow
        Invoke-RestMethod -Method Post -Uri "$HaUrl/api/services/homeassistant/restart" -Headers $Headers -Body "{}" | Out-Null
        Write-Host "Orden de reinicio enviada." -ForegroundColor Green
    } else {
        Write-Host "Recargando entradas de InvertirOnline vía API REST..." -ForegroundColor Cyan
        $Entries = Invoke-RestMethod -Method Get -Uri "$HaUrl/api/config/config_entries/entry" -Headers $Headers
        $IolEntries = $Entries | Where-Object { $_.domain -eq "invertironline" }
        foreach ($entry in $IolEntries) {
            Invoke-RestMethod -Method Post -Uri "$HaUrl/api/config/config_entries/entry/$($entry.entry_id)/reload" -Headers $Headers | Out-Null
            Write-Host "Entrada $($entry.entry_id) recargada." -ForegroundColor Green
        }
    }
} else {
    Write-Host "Siguiente paso: Si es la primera instalación, reinicia Home Assistant; si es una actualización, recarga la integración InvertirOnline (IOL)." -ForegroundColor Yellow
}
