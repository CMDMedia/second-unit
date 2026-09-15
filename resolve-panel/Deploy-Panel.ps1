[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$PanelClosedConfirmed,
    [string]$Python,
    [string]$ComfyUrl
)
$ErrorActionPreference = 'Stop'
$Package = Split-Path -Parent $PSScriptRoot
$TargetRoot = Join-Path $env:PROGRAMDATA 'Blackmagic Design\DaVinci Resolve\Support\Workflow Integration Plugins'
if (-not (Test-Path -LiteralPath $TargetRoot)) { throw 'DaVinci Resolve Studio Workflow Integration Plugins folder was not found.' }
if (-not $Python) { $Python = $env:SECOND_UNIT_PYTHON }
if (-not $Python) { $Python = 'python' }
$Python = (Get-Command $Python -ErrorAction Stop).Source
if ($Python -match '\\WindowsApps\\') { throw 'Use a Python installation from python.org, not the Microsoft Store alias.' }
& $Python -c 'import sys;sys.exit(0 if sys.version_info >= (3,9) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.9 or newer is required for the external worker.' }
$PriorLog = $env:SECOND_UNIT_LOG
$PriorBytecode = $env:PYTHONDONTWRITEBYTECODE
$CheckLog = Join-Path ([IO.Path]::GetTempPath()) ('second-unit-check-' + [guid]::NewGuid().ToString('N') + '.log')
try {
    $env:SECOND_UNIT_LOG = $CheckLog
    $env:PYTHONDONTWRITEBYTECODE = '1'
    & $Python (Join-Path $Package 'tools\check_preview.py')
    if ($LASTEXITCODE -ne 0) { throw 'Package checks failed. Nothing was installed.' }
} finally {
    $env:SECOND_UNIT_LOG = $PriorLog
    $env:PYTHONDONTWRITEBYTECODE = $PriorBytecode
}
if ($CheckOnly) { Write-Output 'CHECK ONLY: passed. Nothing was installed.'; exit 0 }
if ((Get-Process Resolve -ErrorAction SilentlyContinue) -and -not $PanelClosedConfirmed) {
    throw 'Close the Second Unit panel, then rerun with -PanelClosedConfirmed. Resolve may stay open.'
}
$Cache = Join-Path $env:LOCALAPPDATA 'SecondUnit\preview-cache'
$Backup = Join-Path $env:LOCALAPPDATA ('SecondUnit\install-backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $Cache,$Backup -Force | Out-Null
$Names = @('Second Unit.py','h3_prompt_translator.py','camera_reference.py','second-unit-home.json','second-unit.json')
$Existed = @{}
foreach ($Name in $Names) {
    $Dest = Join-Path $TargetRoot $Name
    $Existed[$Name] = Test-Path -LiteralPath $Dest
    if ($Existed[$Name]) { Copy-Item -LiteralPath $Dest -Destination (Join-Path $Backup $Name) }
}
$Config = @{}
$ConfigFile = Join-Path $TargetRoot 'second-unit.json'
if (Test-Path -LiteralPath $ConfigFile) {
    $OldConfig = Get-Content -LiteralPath $ConfigFile -Raw | ConvertFrom-Json
    foreach ($Property in $OldConfig.PSObject.Properties) { $Config[$Property.Name] = $Property.Value }
}
if ($ComfyUrl) { $Config['comfy_url'] = $ComfyUrl }
elseif (-not $Config['comfy_url']) { $Config['comfy_url'] = 'http://127.0.0.1:8188' }
$Config['workflows_dir'] = Join-Path $Package 'workflows'
$Config['cache_dir'] = $Cache
$Config['own_loop'] = '1'
$Config['show_unproven'] = '0'
$HomeData = @{ repo=$Package; workflows=(Join-Path $Package 'workflows'); python=$Python; cache=$Cache }
$Utf8 = New-Object System.Text.UTF8Encoding($false)
try {
    [IO.File]::WriteAllText((Join-Path $TargetRoot 'second-unit-home.json'), ($HomeData | ConvertTo-Json), $Utf8)
    [IO.File]::WriteAllText($ConfigFile, ($Config | ConvertTo-Json -Depth 8), $Utf8)
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'h3_prompt_translator.py') -Destination (Join-Path $TargetRoot 'h3_prompt_translator.py') -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'camera_reference.py') -Destination (Join-Path $TargetRoot 'camera_reference.py') -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'SecondUnit.py') -Destination (Join-Path $TargetRoot 'Second Unit.py') -Force
    foreach ($Pair in @(@('SecondUnit.py','Second Unit.py'),@('h3_prompt_translator.py','h3_prompt_translator.py'),@('camera_reference.py','camera_reference.py'))) {
        if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $Pair[0])).Hash -ne (Get-FileHash -LiteralPath (Join-Path $TargetRoot $Pair[1])).Hash) { throw 'Installed file does not match package.' }
    }
} catch {
    foreach ($Name in $Names) {
        $Dest = Join-Path $TargetRoot $Name
        if ($Existed[$Name]) { Copy-Item -LiteralPath (Join-Path $Backup $Name) -Destination $Dest -Force }
        elseif (Test-Path -LiteralPath $Dest) { Remove-Item -LiteralPath $Dest -Force }
    }
    throw
}
@{ package=$Package; backup=$Backup; installed=(Get-Date).ToString('o'); files=$Names } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Backup 'receipt.json') -Encoding UTF8
Write-Output "INSTALLED: Second Unit Custom Workflow Preview. Backup: $Backup"
Write-Output 'Open Workspace > Workflow Integrations > Second Unit. Restart Resolve after a first installation if the menu entry is missing.'
