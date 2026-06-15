[CmdletBinding()]
param(
    [string]$PythonVersion = "3.11",
    [string]$VenvName = ".venv",
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [string]$OllamaModel = "",
    [switch]$InstallOnly,
    [switch]$SkipFrontendInstall,
    [switch]$SkipModelPull,
    [switch]$SkipDataSeed,
    [switch]$SkipOllama,
    [switch]$NoCleanRestart
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "=== $Message ===" -ForegroundColor Cyan
}

function Resolve-ExternalCommandPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        return $null
    }
    if ($cmd.CommandType -in @("Application", "ExternalScript")) {
        return $cmd.Source
    }
    if ($cmd.Path) {
        return $cmd.Path
    }
    return $cmd.Source
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandPath,
        [string[]]$Arguments = @(),
        [string]$FailureMessage = "Command failed"
    )
    & $CommandPath @Arguments
    $exitCode = $LASTEXITCODE
    if ($null -ne $exitCode -and $exitCode -ne 0) {
        throw "$FailureMessage (exit code: $exitCode)"
    }
}

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string]$Key
    )
    if (-not (Test-Path $FilePath)) {
        return $null
    }
    $pattern = "^\s*{0}\s*=\s*(.*)\s*$" -f [Regex]::Escape($Key)
    foreach ($line in Get-Content -Path $FilePath) {
        if ($line -match "^\s*#") {
            continue
        }
        if ($line -match $pattern) {
            $value = $matches[1].Trim()
            if ($value -match "^(.*?)\s+#") {
                $value = $matches[1].Trim()
            }
            return $value.Trim('"').Trim("'")
        }
    }
    return $null
}

function Set-EnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )
    $lines = @()
    if (Test-Path $FilePath) {
        $lines = @(Get-Content -Path $FilePath)
    }
    $pattern = "^\s*{0}\s*=" -f [Regex]::Escape($Key)
    $updated = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $pattern) {
            $lines[$i] = "$Key=$Value"
            $updated = $true
            break
        }
    }
    if (-not $updated) {
        $lines += "$Key=$Value"
    }
    Set-Content -Path $FilePath -Value $lines -Encoding UTF8
}

function Test-IsAbsoluteSqliteUrl {
    param([string]$DatabaseUrl)
    if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
        return $false
    }
    if ($DatabaseUrl -notmatch "^sqlite:///") {
        return $true
    }
    $pathPart = $DatabaseUrl.Substring("sqlite:///".Length)
    return ($pathPart -match "^[A-Za-z]:/")
}

function Ensure-ProjectEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$EnvFile
    )
    if (-not (Test-Path $EnvFile)) {
        Write-Step "Creating .env from env.example"
        Copy-Item -Path (Join-Path $ProjectRoot "env.example") -Destination $EnvFile
    }

    $currentDbUrl = Get-EnvValue -FilePath $EnvFile -Key "DATABASE_URL"
    if ([string]::IsNullOrWhiteSpace($currentDbUrl)) {
        $currentDbUrl = "sqlite:///./market_analyzer.db"
    }
    if ($currentDbUrl -match "^sqlite:///" -and -not (Test-IsAbsoluteSqliteUrl -DatabaseUrl $currentDbUrl)) {
        $absoluteDbUrl = "sqlite:///$($ProjectRoot.Replace('\','/'))/market_analyzer.db"
        Set-EnvValue -FilePath $EnvFile -Key "DATABASE_URL" -Value $absoluteDbUrl
        Write-Host "Updated DATABASE_URL -> $absoluteDbUrl" -ForegroundColor DarkYellow
    }

    $ollamaBaseUrl = Get-EnvValue -FilePath $EnvFile -Key "OLLAMA_BASE_URL"
    if ([string]::IsNullOrWhiteSpace($ollamaBaseUrl)) {
        Set-EnvValue -FilePath $EnvFile -Key "OLLAMA_BASE_URL" -Value "http://127.0.0.1:11434"
    }
}

function Ensure-VirtualEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$VenvName,
        [Parameter(Mandatory = $true)]
        [string]$PythonVersion
    )
    $venvPath = Join-Path $ProjectRoot $VenvName
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
    $pipExe = Join-Path $venvPath "Scripts\pip.exe"
    $venvIsReady = (Test-Path $pythonExe) -and (Test-Path $pipExe)

    if (-not $venvIsReady -and (Test-Path $venvPath)) {
        Write-Warning "Existing virtual environment is incomplete. Recreating it."
        Remove-Item -Path $venvPath -Recurse -Force
    }

    if (-not $venvIsReady) {
        $pyCmd = Resolve-ExternalCommandPath -Name "py"
        $pythonCmd = Resolve-ExternalCommandPath -Name "python"
        $venvCreated = $false

        if ($pyCmd) {
            try {
                Invoke-CheckedCommand -CommandPath $pyCmd -Arguments @("-$PythonVersion", "-m", "venv", $venvPath) -FailureMessage "Python launcher failed to create venv"
            }
            catch {
                Write-Warning "Python launcher failed for version $PythonVersion. Trying fallback python command."
            }
            $venvCreated = (Test-Path $pythonExe) -and (Test-Path $pipExe)
        }

        if (-not $venvCreated -and $pythonCmd) {
            try {
                Invoke-CheckedCommand -CommandPath $pythonCmd -Arguments @("-m", "venv", $venvPath) -FailureMessage "Fallback python command failed to create venv"
            }
            catch {
                Write-Warning "Fallback python command failed to create virtual environment."
            }
            $venvCreated = (Test-Path $pythonExe) -and (Test-Path $pipExe)
        }

        if (-not $venvCreated) {
            $wingetCmd = Resolve-ExternalCommandPath -Name "winget"
            if ($wingetCmd) {
                Write-Step "Installing Python $PythonVersion via winget"
                Invoke-CheckedCommand -CommandPath $wingetCmd -Arguments @("install", "-e", "--id", "Python.Python.$PythonVersion", "--accept-source-agreements", "--accept-package-agreements") -FailureMessage "winget failed to install Python $PythonVersion"

                $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
                $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
                $env:Path = "$machinePath;$userPath;$env:Path"

                $pyCmd = Resolve-ExternalCommandPath -Name "py"
                $pythonCmd = Resolve-ExternalCommandPath -Name "python"
                if ($pyCmd) {
                    try { Invoke-CheckedCommand -CommandPath $pyCmd -Arguments @("-$PythonVersion", "-m", "venv", $venvPath) -FailureMessage "Python launcher failed after winget install" } catch {}
                    $venvCreated = (Test-Path $pythonExe) -and (Test-Path $pipExe)
                }
                if (-not $venvCreated -and $pythonCmd) {
                    try { Invoke-CheckedCommand -CommandPath $pythonCmd -Arguments @("-m", "venv", $venvPath) -FailureMessage "python command failed after winget install" } catch {}
                    $venvCreated = (Test-Path $pythonExe) -and (Test-Path $pipExe)
                }
            }
        }

        if (-not $venvCreated) {
            throw "Unable to create virtual environment. Ensure Python $PythonVersion is installed and available in PATH."
        }
    }

    if (-not (Test-Path $pythonExe) -or -not (Test-Path $pipExe)) {
        throw "Virtual environment is missing python/pip executables at $venvPath"
    }

    return @{
        VenvPath = $venvPath
        PythonExe = $pythonExe
        PipExe = $pipExe
    }
}

function Install-BackendDependencies {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$PythonExe
    )
    Write-Step "Installing backend dependencies"
    Invoke-CheckedCommand -CommandPath $PythonExe -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel") -FailureMessage "Failed to bootstrap backend build tools"

    $primaryRequirements = Join-Path $ProjectRoot "requirements.txt"
    $fallbackRequirements = Join-Path $ProjectRoot "requirements.deploy.txt"

    if (Test-Path $primaryRequirements) {
        try {
            Invoke-CheckedCommand -CommandPath $PythonExe -Arguments @("-m", "pip", "install", "-r", $primaryRequirements) -FailureMessage "Failed to install requirements.txt"
        }
        catch {
            Write-Warning "Failed to install requirements.txt. Falling back to requirements.deploy.txt."
            if (Test-Path $fallbackRequirements) {
                Invoke-CheckedCommand -CommandPath $PythonExe -Arguments @("-m", "pip", "install", "-r", $fallbackRequirements) -FailureMessage "Failed to install requirements.deploy.txt fallback"
            }
            else {
                throw
            }
        }
    }
    elseif (Test-Path $fallbackRequirements) {
        Invoke-CheckedCommand -CommandPath $PythonExe -Arguments @("-m", "pip", "install", "-r", $fallbackRequirements) -FailureMessage "Failed to install requirements.deploy.txt"
    }
    else {
        throw "Neither requirements.txt nor requirements.deploy.txt was found."
    }
}

function Install-FrontendDependencies {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )
    Write-Step "Installing frontend dependencies"
    $npmCmd = Resolve-ExternalCommandPath -Name "npm"
    if (-not $npmCmd) {
        throw "npm not found. Install Node.js (LTS) and try again."
    }
    Push-Location (Join-Path $ProjectRoot "frontend")
    try {
        if (Test-Path "package-lock.json") {
            Invoke-CheckedCommand -CommandPath $npmCmd -Arguments @("ci") -FailureMessage "npm ci failed"
        }
        else {
            Invoke-CheckedCommand -CommandPath $npmCmd -Arguments @("install") -FailureMessage "npm install failed"
        }
    }
    finally {
        Pop-Location
    }
}

function Test-OllamaReady {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 3 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Wait-OllamaReady {
    param(
        [int]$Attempts = 45,
        [int]$DelaySeconds = 2
    )
    for ($i = 0; $i -lt $Attempts; $i++) {
        if (Test-OllamaReady) {
            return $true
        }
        Start-Sleep -Seconds $DelaySeconds
    }
    return $false
}

function Resolve-OllamaExePath {
    $ollamaPath = Resolve-ExternalCommandPath -Name "ollama"
    if ($ollamaPath) {
        return $ollamaPath
    }
    $possiblePaths = @(
        "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
        "C:\Program Files\Ollama\ollama.exe"
    )
    foreach ($path in $possiblePaths) {
        if (Test-Path $path) {
            return $path
        }
    }
    return $null
}

function Ensure-OllamaInstalledAndReady {
    Write-Step "Ensuring Ollama is installed"
    $ollamaExe = Resolve-OllamaExePath
    if (-not $ollamaExe) {
        $wingetCmd = Resolve-ExternalCommandPath -Name "winget"
        if (-not $wingetCmd) {
            throw "Ollama is not installed and winget is not available. Install Ollama manually: https://ollama.com/download"
        }
        Invoke-CheckedCommand -CommandPath $wingetCmd -Arguments @("install", "-e", "--id", "Ollama.Ollama", "--accept-source-agreements", "--accept-package-agreements") -FailureMessage "winget failed to install Ollama"
        $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $env:Path = "$machinePath;$userPath;$env:Path"
        $ollamaExe = Resolve-OllamaExePath
    }
    if (-not $ollamaExe) {
        throw "Ollama executable not found after installation."
    }
    if (-not (Test-OllamaReady)) {
        Write-Step "Starting Ollama server"
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Minimized | Out-Null
        if (-not (Wait-OllamaReady -Attempts 45 -DelaySeconds 2)) {
            throw "Ollama API did not become ready in time."
        }
    }
    return $ollamaExe
}

function Get-InstalledOllamaModels {
    if (-not (Test-OllamaReady)) {
        return @()
    }
    try {
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 10
        if (-not $tags -or -not $tags.models) {
            return @()
        }
        return @($tags.models | ForEach-Object { $_.name } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    }
    catch {
        return @()
    }
}

function Select-BestInstalledModel {
    param([string[]]$InstalledModels)
    if (-not $InstalledModels -or $InstalledModels.Count -eq 0) {
        return $null
    }
    $preferred = @(
        "qwen2.5:7b-instruct",
        "qwen2.5:7b",
        "mistral:7b-instruct",
        "llama3.1:8b-instruct",
        "phi3:mini"
    )
    foreach ($model in $preferred) {
        if ($InstalledModels -contains $model) {
            return $model
        }
    }
    $instructModel = $InstalledModels | Where-Object { $_ -match "instruct|chat" } | Select-Object -First 1
    if ($instructModel) {
        return $instructModel
    }
    return $InstalledModels[0]
}

function Pull-ModelWithRetry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OllamaExePath,
        [Parameter(Mandatory = $true)]
        [string]$ModelName,
        [int]$MaxAttempts = 3
    )
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            Invoke-CheckedCommand -CommandPath $OllamaExePath -Arguments @("pull", $ModelName) -FailureMessage "Ollama model pull failed"
            return
        }
        catch {
            if ($attempt -ge $MaxAttempts) {
                throw
            }
            Write-Warning "Model pull failed (attempt $attempt/$MaxAttempts). Retrying in 5s..."
            Start-Sleep -Seconds 5
        }
    }
}

function Ensure-OllamaModel {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OllamaExe,
        [Parameter(Mandatory = $true)]
        [string]$EnvFile,
        [string]$RequestedModel,
        [switch]$SkipModelPull
    )
    $effectiveModel = $RequestedModel
    if ([string]::IsNullOrWhiteSpace($effectiveModel)) {
        $effectiveModel = Get-EnvValue -FilePath $EnvFile -Key "OLLAMA_MODEL"
    }
    if ([string]::IsNullOrWhiteSpace($effectiveModel)) {
        $effectiveModel = "qwen2.5:7b-instruct"
    }

    $installedModels = Get-InstalledOllamaModels
    if ($installedModels -contains $effectiveModel) {
        Set-EnvValue -FilePath $EnvFile -Key "OLLAMA_MODEL" -Value $effectiveModel
        return $effectiveModel
    }

    # Prefer an already-installed instruct model over a multi-GB download - this is
    # the common reason the assistant ends up on the fallback (the pull never finished).
    $alreadyInstalled = Select-BestInstalledModel -InstalledModels $installedModels
    if ($alreadyInstalled) {
        Write-Warning "Model '$effectiveModel' not installed; using already-installed '$alreadyInstalled' (skipping download)."
        Set-EnvValue -FilePath $EnvFile -Key "OLLAMA_MODEL" -Value $alreadyInstalled
        return $alreadyInstalled
    }

    if ($SkipModelPull) {
        $fallback = Select-BestInstalledModel -InstalledModels $installedModels
        if (-not $fallback) {
            throw "Requested model '$effectiveModel' is not installed and no local Ollama models were found. Run script without -SkipModelPull."
        }
        Write-Warning "Requested model '$effectiveModel' is not installed. Using local model '$fallback'."
        Set-EnvValue -FilePath $EnvFile -Key "OLLAMA_MODEL" -Value $fallback
        return $fallback
    }

    Write-Step "Pulling Ollama model: $effectiveModel"
    Pull-ModelWithRetry -OllamaExePath $OllamaExe -ModelName $effectiveModel -MaxAttempts 3
    $installedAfterPull = Get-InstalledOllamaModels
    if (-not ($installedAfterPull -contains $effectiveModel)) {
        $fallbackAfterPull = Select-BestInstalledModel -InstalledModels $installedAfterPull
        if (-not $fallbackAfterPull) {
            throw "Model '$effectiveModel' is still unavailable after pull."
        }
        Write-Warning "Model '$effectiveModel' is unavailable after pull. Falling back to '$fallbackAfterPull'."
        $effectiveModel = $fallbackAfterPull
    }
    Set-EnvValue -FilePath $EnvFile -Key "OLLAMA_MODEL" -Value $effectiveModel
    return $effectiveModel
}

function Resolve-ShellExecutable {
    $candidates = @(
        (Join-Path $PSHOME "pwsh.exe"),
        (Join-Path $PSHOME "powershell.exe"),
        (Get-Process -Id $PID).Path
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
    if ($candidates -and $candidates.Count -gt 0) {
        return $candidates[0]
    }
    throw "Unable to resolve a PowerShell executable for launching child terminals."
}

function Stop-ProcessesOnPorts {
    param([int[]]$Ports)
    $stopped = @()
    foreach ($port in $Ports) {
        $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($listener in $listeners) {
            $procId = $listener.OwningProcess
            try {
                Stop-Process -Id $procId -Force -ErrorAction Stop
                $stopped += "stopped_pid_${procId}_port_${port}"
            }
            catch {
                $stopped += "failed_pid_${procId}_port_${port}"
            }
        }
    }
    if ($stopped.Count -gt 0) {
        Write-Host ($stopped -join "`n") -ForegroundColor DarkYellow
    }
}

function Wait-HttpReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$Attempts = 60,
        [int]$DelaySeconds = 2
    )
    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -Method Get -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
                return $true
            }
        }
        catch {}
        Start-Sleep -Seconds $DelaySeconds
    }
    return $false
}

function Get-DbVacancyCount {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe
    )
    $code = @'
from sqlalchemy import select, func
from app.db.session import SessionLocal, init_db
from app.db.models import Vacancy

init_db()
with SessionLocal() as session:
    count = session.execute(select(func.count(Vacancy.id))).scalar_one()
print(f"COUNT:{int(count)}")
'@
    $output = @($code | & $PythonExe - 2>&1)
    $exitCode = $LASTEXITCODE
    if ($null -ne $exitCode -and $exitCode -ne 0) {
        throw "Unable to read vacancy count.`n$($output -join "`n")"
    }
    $text = $output -join "`n"
    $match = [Regex]::Match($text, "COUNT:(\d+)")
    if (-not $match.Success) {
        throw "Unable to parse vacancy count from output.`n$text"
    }
    return [int]$match.Groups[1].Value
}

function Seed-DataIfNeeded {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe,
        [switch]$SkipDataSeed
    )
    if ($SkipDataSeed) {
        return
    }

    $countBefore = Get-DbVacancyCount -PythonExe $PythonExe
    if ($countBefore -gt 0) {
        Write-Host "Data already present in DB: $countBefore rows." -ForegroundColor Green
        return
    }

    Write-Step "Database is empty. Seeding data from live sources (HN / LinkedIn / job APIs)"
    Write-Host "This downloads real data and may take a few minutes. CSV fallback is used only if all sources fail." -ForegroundColor DarkYellow
    $seedCode = @'
import json
from sqlalchemy import select, func
from app.db.session import SessionLocal, init_db
from app.db.models import Vacancy
from app.services.ingestion import run_ingestion_pipeline

init_db()
with SessionLocal() as session:
    result = run_ingestion_pipeline(session, force_csv=False)

with SessionLocal() as session:
    count = session.execute(select(func.count(Vacancy.id))).scalar_one()

print("SEED_RESULT:" + json.dumps({"vacancies": int(count), "summary": result}, ensure_ascii=False))
'@
    $seedOutput = @($seedCode | & $PythonExe - 2>&1)
    $seedExitCode = $LASTEXITCODE
    if ($null -ne $seedExitCode -and $seedExitCode -ne 0) {
        throw "Data seed failed.`n$($seedOutput -join "`n")"
    }
    $seedText = $seedOutput -join "`n"
    Write-Host $seedText

    $countAfter = Get-DbVacancyCount -PythonExe $PythonExe
    if ($countAfter -le 0) {
        throw "Data seed completed without errors but DB is still empty."
    }
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Get-Location).Path
}
Set-Location $ProjectRoot

Write-Step "Checking project structure"
$requiredPaths = @(
    "app\main.py",
    "frontend\package.json",
    "env.example"
)
foreach ($required in $requiredPaths) {
    $fullPath = Join-Path $ProjectRoot $required
    if (-not (Test-Path $fullPath)) {
        throw "Required path not found: $required"
    }
}

$envFile = Join-Path $ProjectRoot ".env"
Ensure-ProjectEnv -ProjectRoot $ProjectRoot -EnvFile $envFile

Write-Step "Setting up Python virtual environment"
$venvInfo = Ensure-VirtualEnvironment -ProjectRoot $ProjectRoot -VenvName $VenvName -PythonVersion $PythonVersion
$pythonExe = $venvInfo.PythonExe

Install-BackendDependencies -ProjectRoot $ProjectRoot -PythonExe $pythonExe

if (-not $SkipFrontendInstall) {
    Install-FrontendDependencies -ProjectRoot $ProjectRoot
}

# Ollama powers the AI assistant. It is OPTIONAL: the assistant falls back to
# deterministic, data-driven answers if Ollama is unavailable. Never let an
# Ollama hiccup abort the whole setup.
$selectedModel = ""
if ($SkipOllama) {
    Write-Step "Skipping Ollama setup (-SkipOllama). Assistant will use deterministic fallback."
}
else {
    try {
        $ollamaExe = Ensure-OllamaInstalledAndReady
        $selectedModel = Ensure-OllamaModel -OllamaExe $ollamaExe -EnvFile $envFile -RequestedModel $OllamaModel -SkipModelPull:$SkipModelPull
        Write-Host "Using Ollama model: $selectedModel" -ForegroundColor Green
    }
    catch {
        Write-Warning "Ollama setup failed: $($_.Exception.Message)"
        Write-Warning "Continuing without a local LLM - the assistant will use its deterministic fallback."
    }
}

Seed-DataIfNeeded -PythonExe $pythonExe -SkipDataSeed:$SkipDataSeed

if ($InstallOnly) {
    Write-Step "Install complete"
    Write-Host "Environment is ready. To start services later, run this script again without -InstallOnly."
    exit 0
}

if (-not $NoCleanRestart) {
    Write-Step "Cleaning existing listeners on target ports"
    Stop-ProcessesOnPorts -Ports @($BackendPort, $FrontendPort)
}

Write-Step "Starting backend and frontend in separate terminal windows"
$shellExe = Resolve-ShellExecutable
$frontendDir = Join-Path $ProjectRoot "frontend"
$npmExe = Resolve-ExternalCommandPath -Name "npm"
if (-not $npmExe) {
    throw "npm not found. Install Node.js (LTS) and ensure npm is in PATH."
}

$databaseUrl = Get-EnvValue -FilePath $envFile -Key "DATABASE_URL"
if (-not $databaseUrl) {
    $databaseUrl = "sqlite:///$($ProjectRoot.Replace('\','/'))/market_analyzer.db"
}

$ollamaModelForRun = $selectedModel
if (-not $ollamaModelForRun) { $ollamaModelForRun = Get-EnvValue -FilePath $envFile -Key "OLLAMA_MODEL" }
if (-not $ollamaModelForRun) { $ollamaModelForRun = "qwen2.5:7b-instruct" }
# Set env vars in the CHILD shell. Single-quoted template keeps $env: literal; -f fills values.
$backendTemplate = '$env:DATABASE_URL=''{0}''; $env:OLLAMA_MODEL=''{1}''; $env:ASSISTANT_LLM_ENABLED=''true''; $env:LLM_PROVIDER=''ollama''; & ''{2}'' -m uvicorn app.main:app --host 0.0.0.0 --port {3}'
$backendCommand = $backendTemplate -f $databaseUrl, $ollamaModelForRun, $pythonExe, $BackendPort
$frontendCommand = "& '$npmExe' run dev -- --host 0.0.0.0 --port $FrontendPort"

Start-Process -FilePath $shellExe -WorkingDirectory $ProjectRoot -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand | Out-Null
Start-Process -FilePath $shellExe -WorkingDirectory $frontendDir -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand | Out-Null

Write-Step "Waiting for services"
$backendReady = Wait-HttpReady -Url "http://127.0.0.1:$BackendPort/api/system/data-status" -Attempts 60 -DelaySeconds 2
if (-not $backendReady) {
    throw "Backend did not become ready on http://127.0.0.1:$BackendPort"
}
$frontendReady = Wait-HttpReady -Url "http://127.0.0.1:$FrontendPort/" -Attempts 60 -DelaySeconds 1
if (-not $frontendReady) {
    Write-Warning "Frontend is still starting. It should be available shortly at http://127.0.0.1:$FrontendPort"
}

try {
    $status = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/system/data-status" -Method Get -TimeoutSec 10
    $rows = $status.rows
}
catch {
    $rows = "unknown"
}

Write-Step "Done"
Write-Host "Backend:  http://127.0.0.1:$BackendPort"
Write-Host "Frontend: http://127.0.0.1:$FrontendPort"
Write-Host "Rows in memory: $rows"
if ($selectedModel -and (Test-OllamaReady)) {
    Write-Host "AI assistant (Vyz): ON via Ollama model '$selectedModel'" -ForegroundColor Green
}
else {
    Write-Host "AI assistant (Vyz): deterministic fallback (Ollama/model unavailable)." -ForegroundColor DarkYellow
    Write-Host "  To enable LLM replies: install Ollama (https://ollama.com), run 'ollama pull qwen2.5:7b-instruct', then re-run this script." -ForegroundColor DarkYellow
}
