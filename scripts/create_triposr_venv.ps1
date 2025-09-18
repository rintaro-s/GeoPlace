Param(
    [string]$Path = '.\venv-triposr',
    [string]$Python = 'python',
    [switch]$InstallDeps
)

$abs = (Resolve-Path $Path).Path 2>$null
if (-not $abs) {
    python -m venv $Path
    Write-Output "Created venv at $Path"
} else {
    Write-Output "venv path $Path already exists"
}

$py = Join-Path $Path 'Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Output "Could not find python at $py. Ensure the venv created successfully or set -Python to a different Python executable."
    return
}

if ($InstallDeps) {
    Write-Output "Activating venv and installing TripoSR requirements (this may take a while)..."
    & $py -m pip install --upgrade pip
    $req = Join-Path (Join-Path $PSScriptRoot '..\TripoSR-main') 'requirements.txt'
    if (Test-Path $req) {
        & $py -m pip install -r $req
        Write-Output "Installed requirements from $req"
    } else {
        Write-Output "requirements.txt not found at $req; please install dependencies manually inside the venv."
    }
}

Write-Output "TripoSR venv prepared. Python: $py"
Write-Output "Next: run scripts\set_triposr_python.ps1 -PythonPath $py to write backend/config.yaml or pass the python path to the server operator."