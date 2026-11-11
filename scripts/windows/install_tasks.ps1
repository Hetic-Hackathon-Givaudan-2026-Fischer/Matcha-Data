<#
.SYNOPSIS
  Installe (ou supprime) les 3 tâches planifiées FlavorTrends pour l'utilisateur courant.

.DESCRIPTION
  - Collecte quotidienne   : 03:00, toutes les sources puis nettoyage
  - Presse toutes les 4 h  : 07:00, 11:00, 15:00, 19:00, 23:00 (RSS + Google News + nettoyage)
  - Contrôle de fraîcheur  : 08:30, résultat dans logs\freshness_latest.log

  Si le PC est éteint à l'heure prévue, la tâche se lance dès qu'il redémarre (StartWhenAvailable).
  Les tâches tournent quand l'utilisateur est connecté à sa session Windows.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\install_tasks.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\install_tasks.ps1 -Uninstall
#>
param(
    [switch]$Uninstall,
    [string]$TaskFolder = '\FlavorTrends\',
    [string]$DailyAt = '03:00',
    [string[]]$PressAt = @('07:00', '11:00', '15:00', '19:00', '23:00'),
    [string]$FreshnessAt = '08:30'
)

$ErrorActionPreference = 'Stop'
$Runner = Join-Path $PSScriptRoot 'run_job.ps1'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

$Tasks = @(
    @{ Name = 'Collecte quotidienne'; Job = 'daily'; Times = @($DailyAt); LimitHours = 4 },
    @{ Name = 'Presse toutes les 4 h'; Job = 'press'; Times = $PressAt; LimitHours = 1 },
    @{ Name = 'Contrôle de fraîcheur'; Job = 'freshness'; Times = @($FreshnessAt); LimitHours = 1 }
)

if ($Uninstall) {
    foreach ($t in $Tasks) {
        if (Get-ScheduledTask -TaskPath $TaskFolder -TaskName $t.Name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskPath $TaskFolder -TaskName $t.Name -Confirm:$false
            Write-Host "Supprimée : $TaskFolder$($t.Name)"
        }
    }
    return
}

$Exe = Join-Path $Root '.venv\Scripts\flavortrends.exe'
if (-not (Test-Path $Exe)) {
    throw "Projet non installé : $Exe introuvable. Lancez d'abord : pip install -e ."
}
if (-not (Test-Path (Join-Path $Root '.env'))) {
    Write-Warning "Fichier .env absent : les tâches échoueront tant qu'il n'est pas créé (voir README)."
}

$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

foreach ($t in $Tasks) {
    $Arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Job {1}' -f $Runner, $t.Job
    $Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $Arguments -WorkingDirectory $Root
    $Triggers = @(foreach ($time in $t.Times) { New-ScheduledTaskTrigger -Daily -At $time })
    $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Hours $t.LimitHours) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 15)   # relance si la tâche est interrompue (veille, coupure)
    Register-ScheduledTask -TaskPath $TaskFolder -TaskName $t.Name -Action $Action -Trigger $Triggers `
        -Principal $Principal -Settings $Settings -Description "FlavorTrends : run_job.ps1 -Job $($t.Job)" -Force | Out-Null
    Write-Host ("Installée : {0}{1}  ({2})" -f $TaskFolder, $t.Name, ($t.Times -join ', '))
}

Write-Host ""
Write-Host "Journaux : $Root\logs"
Write-Host "Voir les tâches : touche Windows, tapez « Planificateur de tâches », dossier FlavorTrends."
Write-Host "Tester tout de suite : Start-ScheduledTask -TaskPath '$TaskFolder' -TaskName 'Contrôle de fraîcheur'"
