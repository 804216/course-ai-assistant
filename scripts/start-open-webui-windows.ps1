[CmdletBinding()]
param(
    [string]$ListenHost = '0.0.0.0',
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,
    [switch]$BuildFrontend
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$webuiRoot = Join-Path $projectRoot 'open-webui'
$deployRoot = Join-Path $webuiRoot 'local-deploy'
$dataDir = Join-Path $deployRoot 'data'
$cacheDir = Join-Path $dataDir 'cache'
$logsDir = Join-Path $deployRoot 'logs'
$tempDir = Join-Path $deployRoot 'tmp'
$staticDir = Join-Path $deployRoot 'static'
$buildDir = Join-Path $webuiRoot 'build'
$backendDir = Join-Path $webuiRoot 'backend'
$venvDir = Join-Path $webuiRoot '.venv'
$openWebuiExe = Join-Path $venvDir 'Scripts\open-webui.exe'
$secretFile = Join-Path $deployRoot 'webui_secret_key.txt'
$localEnvExample = Join-Path $webuiRoot '.env.example'

foreach ($dir in @($dataDir, $cacheDir, $logsDir, $tempDir, $staticDir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

if (-not (Test-Path -LiteralPath $openWebuiExe -PathType Leaf)) {
    throw "Shared virtual environment is unavailable: $openWebuiExe"
}

# Keep configurable runtime files under local-deploy on drive D.
$env:DATA_DIR = $dataDir
$env:FRONTEND_BUILD_DIR = $buildDir
$env:STATIC_DIR = $staticDir
$env:TEMP = $tempDir
$env:TMP = $tempDir
$env:TMPDIR = $tempDir
$env:HF_HOME = Join-Path $cacheDir 'huggingface'
$env:HF_XET_CACHE = Join-Path $cacheDir 'huggingface\xet'
$env:HF_HUB_DISABLE_XET = '1'
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'
$env:RAG_EMBEDDING_MODEL_AUTO_UPDATE = 'False'
$env:XDG_CACHE_HOME = $cacheDir
$env:PIP_CACHE_DIR = Join-Path $cacheDir 'pip'
$env:UV_CACHE_DIR = Join-Path $cacheDir 'uv'
$env:NPM_CONFIG_CACHE = Join-Path $cacheDir 'npm'
$env:PYTHONPYCACHEPREFIX = Join-Path $cacheDir 'pycache'
$env:TORCH_HOME = Join-Path $cacheDir 'torch'
$env:MPLCONFIGDIR = Join-Path $cacheDir 'matplotlib'
$env:NLTK_DATA = Join-Path $cacheDir 'nltk_data'
$env:PYTHONUTF8 = '1'

# Course-agent reranking uses the SiliconFlow-compatible endpoint.  The local
# key currently lives in .env.example as requested; copy it into this process
# only, never print it or persist it in Open WebUI's database.
if ([string]::IsNullOrWhiteSpace($env:COURSE_RERANK_API_KEY) -and (Test-Path -LiteralPath $localEnvExample)) {
    $rerankLine = Get-Content -LiteralPath $localEnvExample |
        Where-Object { $_ -match '^\s*rerank-key\s*=' } |
        Select-Object -Last 1
    if ($rerankLine -match '^\s*rerank-key\s*=\s*(.*)\s*$') {
        $rerankKey = $Matches[1].Trim()
        if (
            $rerankKey.Length -ge 2 -and
            (($rerankKey.StartsWith("'") -and $rerankKey.EndsWith("'")) -or
             ($rerankKey.StartsWith('"') -and $rerankKey.EndsWith('"')))
        ) {
            $rerankKey = $rerankKey.Substring(1, $rerankKey.Length - 2)
        }
        if (-not [string]::IsNullOrWhiteSpace($rerankKey)) {
            $env:COURSE_RERANK_API_KEY = $rerankKey
        }
    }
}
$env:COURSE_RERANK_API_URL = if ([string]::IsNullOrWhiteSpace($env:COURSE_RERANK_API_URL)) {
    'https://api.siliconflow.cn/v1/rerank'
} else {
    $env:COURSE_RERANK_API_URL
}
$env:COURSE_RERANK_MODEL = if ([string]::IsNullOrWhiteSpace($env:COURSE_RERANK_MODEL)) {
    'BAAI/bge-reranker-v2-m3'
} else {
    $env:COURSE_RERANK_MODEL
}
$env:COURSE_RERANK_TIMEOUT = if ([string]::IsNullOrWhiteSpace($env:COURSE_RERANK_TIMEOUT)) {
    '30'
} else {
    $env:COURSE_RERANK_TIMEOUT
}

# The shared .venv is an editable install; prefer the current checkout's source.
if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $backendDir
} else {
    $env:PYTHONPATH = "$backendDir;$($env:PYTHONPATH)"
}

# Add the base Conda Python DLL directories required by this shared venv.
$pyvenvConfig = Join-Path $venvDir 'pyvenv.cfg'
if (Test-Path -LiteralPath $pyvenvConfig -PathType Leaf) {
    $homeLine = Get-Content -LiteralPath $pyvenvConfig | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1
    if ($homeLine -match '^home\s*=\s*(.+)$') {
        $pythonHome = $Matches[1].Trim()
        $env:PATH = "$pythonHome;$pythonHome\Library\bin;$pythonHome\DLLs;$pythonHome\Scripts;$($env:PATH)"
    }
}

if (-not (Test-Path -LiteralPath $secretFile -PathType Leaf)) {
    $secretBytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($secretBytes)
    } finally {
        $rng.Dispose()
    }
    [System.IO.File]::WriteAllText(
        $secretFile,
        [Convert]::ToBase64String($secretBytes),
        [System.Text.Encoding]::ASCII
    )
}

$env:WEBUI_SECRET_KEY_FILE = $secretFile
$env:WEBUI_SECRET_KEY = (Get-Content -LiteralPath $secretFile -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($env:WEBUI_SECRET_KEY)) {
    throw "The secret key file is empty: $secretFile"
}

if ($BuildFrontend) {
    $npm = Get-Command npm.cmd -ErrorAction Stop
    Push-Location $webuiRoot
    try {
        & $npm.Source run build
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend build failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $buildDir 'index.html') -PathType Leaf)) {
    throw "Frontend build not found. Run: .\scripts\start-open-webui-windows.ps1 -BuildFrontend"
}

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    $owners = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ', '
    throw "Port $Port is already in use by process(es): $owners"
}

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdoutLog = Join-Path $logsDir "open-webui-$timestamp.stdout.log"
$stderrLog = Join-Path $logsDir "open-webui-$timestamp.stderr.log"
$serverProcess = Start-Process `
    -FilePath $openWebuiExe `
    -ArgumentList @('serve', '--host', $ListenHost, '--port', $Port) `
    -WorkingDirectory $webuiRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

$pidFile = Join-Path $deployRoot 'open-webui.pid'
Start-Sleep -Seconds 3
$serverProcess.Refresh()
if ($serverProcess.HasExited) {
    if (Test-Path -LiteralPath $pidFile) {
        Remove-Item -LiteralPath $pidFile -Force
    }
    $errorTail = if (Test-Path -LiteralPath $stderrLog) {
        (Get-Content -LiteralPath $stderrLog -Tail 20) -join [Environment]::NewLine
    } else {
        'No stderr log was created.'
    }
    throw "Open WebUI exited during startup (code $($serverProcess.ExitCode)).`n$errorTail"
}

[System.IO.File]::WriteAllText(
    $pidFile,
    [string]$serverProcess.Id,
    [System.Text.Encoding]::ASCII
)

Write-Host "Open WebUI started. PID=$($serverProcess.Id)"
Write-Host "URL: http://localhost:$Port"
Write-Host "Data: $dataDir"
Write-Host "Logs: $logsDir"
