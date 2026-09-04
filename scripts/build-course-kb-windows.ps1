[CmdletBinding()]
param(
    [string]$Source,
    [string]$BuildId
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$webuiRoot = Join-Path $projectRoot 'open-webui'
$deployRoot = Join-Path $webuiRoot 'local-deploy'
$dataDir = Join-Path $deployRoot 'data'
$cacheDir = Join-Path $dataDir 'cache'
$tempDir = Join-Path $deployRoot 'tmp'
$venvPython = Join-Path $webuiRoot '.venv\Scripts\python.exe'
$builder = Join-Path $projectRoot 'tools\course_kb\build_course_kb.py'
$output = Join-Path $dataDir 'course_kb'

foreach ($dir in @($dataDir, $cacheDir, $tempDir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Shared virtual environment is unavailable: $venvPython"
}

if ([string]::IsNullOrWhiteSpace($Source)) {
    $Source = Join-Path $projectRoot 'knowledge-base'
}

$env:HF_HOME = Join-Path $cacheDir 'huggingface'
$env:HF_XET_CACHE = Join-Path $cacheDir 'huggingface\xet'
$env:HF_HUB_DISABLE_XET = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:TEMP = $tempDir
$env:TMP = $tempDir
$env:TMPDIR = $tempDir
$env:XDG_CACHE_HOME = $cacheDir
$env:PYTHONPYCACHEPREFIX = Join-Path $cacheDir 'pycache'
$env:TORCH_HOME = Join-Path $cacheDir 'torch'
$env:PYTHONUTF8 = '1'

$pyvenvConfig = Join-Path (Split-Path -Parent (Split-Path -Parent $venvPython)) 'pyvenv.cfg'
if (Test-Path -LiteralPath $pyvenvConfig -PathType Leaf) {
    $homeLine = Get-Content -LiteralPath $pyvenvConfig | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1
    if ($homeLine -match '^home\s*=\s*(.+)$') {
        $pythonHome = $Matches[1].Trim()
        $env:PATH = "$pythonHome;$pythonHome\Library\bin;$pythonHome\DLLs;$pythonHome\Scripts;$($env:PATH)"
    }
}

$arguments = @($builder, '--source', $Source, '--output', $output)
if (-not [string]::IsNullOrWhiteSpace($BuildId)) {
    $arguments += @('--build-id', $BuildId)
}

& $venvPython @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Course knowledge base build failed with exit code $LASTEXITCODE"
}
