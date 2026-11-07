param([switch]$SeedDemo)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv312\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create the Python environment using README.md first.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) { throw 'Build the frontend first: cd frontend; npm install; npm run build' }
Push-Location (Join-Path $projectRoot 'backend')
try {
    & $pythonPath -m flask --app run init-db
    if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed.' }
    if ($SeedDemo) {
        & $pythonPath -m flask --app run seed-demo
        if ($LASTEXITCODE -ne 0) { throw 'Demo initialization failed.' }
    }
    Write-Host 'AuditFlow AI: http://127.0.0.1:5000 (Ctrl+C to stop)'
    & $pythonPath run.py
} finally { Pop-Location }
