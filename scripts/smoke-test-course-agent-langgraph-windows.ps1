[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:8080'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$webuiRoot = Join-Path $projectRoot 'open-webui'
$deployRoot = Join-Path $webuiRoot 'local-deploy'
$dataDir = Join-Path $deployRoot 'data'
$cacheDir = Join-Path $dataDir 'cache'
$tempDir = Join-Path $deployRoot 'tmp'
$venvPython = Join-Path $webuiRoot '.venv\Scripts\python.exe'
$smokeTest = Join-Path $projectRoot 'tools\course_agent\smoke_test_langgraph.py'

$env:DATA_DIR = $dataDir
$env:TEMP = $tempDir
$env:TMP = $tempDir
$env:TMPDIR = $tempDir
$env:XDG_CACHE_HOME = $cacheDir
$env:PYTHONPYCACHEPREFIX = Join-Path $cacheDir 'pycache'
$env:PYTHONUTF8 = '1'

$pyvenvConfig = Join-Path (Split-Path -Parent (Split-Path -Parent $venvPython)) 'pyvenv.cfg'
if (Test-Path -LiteralPath $pyvenvConfig -PathType Leaf) {
    $homeLine = Get-Content -LiteralPath $pyvenvConfig | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1
    if ($homeLine -match '^home\s*=\s*(.+)$') {
        $pythonHome = $Matches[1].Trim()
        $env:PATH = "$pythonHome;$pythonHome\Library\bin;$pythonHome\DLLs;$pythonHome\Scripts;$($env:PATH)"
    }
}

& $venvPython $smokeTest --base-url $BaseUrl
if ($LASTEXITCODE -ne 0) {
    throw "LangGraph course assistant smoke test failed with exit code $LASTEXITCODE"
}
