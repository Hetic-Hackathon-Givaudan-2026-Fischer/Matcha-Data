<#
.SYNOPSIS
  Lance un travail FlavorTrends et écrit son journal dans logs\. Appelé par le Planificateur de tâches.

.PARAMETER Job
  daily     : toutes les sources puis nettoyage (chaque nuit)
  press     : flux RSS + Google News puis nettoyage (toutes les 4 h)
  freshness : contrôle de fraîcheur (chaque matin) ; copie le résultat dans logs\freshness_latest.log

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\run_job.ps1 -Job press
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('daily', 'press', 'freshness')]
    [string]$Job
)

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Exe = Join-Path $Root '.venv\Scripts\flavortrends.exe'
$LogDir = Join-Path $Root 'logs'
$KeepDays = 30

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ('{0}_{1}.log' -f $Job, (Get-Date -Format 'yyyy-MM-dd_HHmm'))

function Write-Log([string]$Text) {
    Add-Content -Path $Log -Encoding UTF8 -Value ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Text)
}

if (-not (Test-Path $Exe)) {
    Write-Log "Programme introuvable : $Exe. Installez le projet dans .venv (pip install -e .)."
    exit 2
}

$Steps = switch ($Job) {
    'daily'     { @('run') }
    'press'     { @('collect rss', 'collect google_news', 'clean') }
    'freshness' { @('freshness') }
}

$env:PYTHONIOENCODING = 'utf-8'
$ExitCode = 0
foreach ($Step in $Steps) {
    Write-Log "flavortrends $Step"
    # Start-Process redirige stdout et stderr dans des fichiers temporaires (sans passer par cmd.exe,
    # qui casse sur les chemins avec espaces comme « Project Data »), puis on les ajoute au journal.
    $Out = Join-Path $LogDir ('.{0}.out.tmp' -f $Job)
    $Err = Join-Path $LogDir ('.{0}.err.tmp' -f $Job)
    $Proc = Start-Process -FilePath $Exe -ArgumentList $Step -WorkingDirectory $Root -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $Out -RedirectStandardError $Err
    $Code = $Proc.ExitCode
    foreach ($F in @($Out, $Err)) {
        if (Test-Path $F) {
            Get-Content -Path $F -Encoding UTF8 | Add-Content -Path $Log -Encoding UTF8
            Remove-Item -Path $F -Force
        }
    }
    Write-Log "fin de l'étape, code de sortie $Code"
    if ($Code -ne 0) { $ExitCode = $Code }
}

if ($Job -eq 'freshness') {
    Copy-Item -Path $Log -Destination (Join-Path $LogDir 'freshness_latest.log') -Force
}

# Rotation : on garde 30 jours de journaux.
Get-ChildItem -Path $LogDir -Filter '*.log' |
    Where-Object { $_.Name -ne 'freshness_latest.log' -and $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } |
    Remove-Item -Force

exit $ExitCode
