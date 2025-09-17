# Activate the virtual environment
& "$PSScriptRoot\venv\Scripts\Activate.ps1"

# Install required packages if not already installed
try {
    python -c "import torchmcubes" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing torchmcubes..."
        pip install torchmcubes
    }
} catch {
    Write-Host "Installing torchmcubes..."
    pip install torchmcubes
}

# Navigate to TripoSR directory
$triposrDir = "E:\GITS\TripoSR-main"
if (-not (Test-Path $triposrDir)) {
    Write-Error "TripoSR directory not found at: $triposrDir"
    exit 1
}

# Check arguments
$inputImage = $args[0]
$outputDir = $args[1]

if (-not $inputImage -or -not $outputDir) {
    Write-Host "Usage: .\run_triposr.ps1 <input_image> <output_directory>"
    exit 1
}

# Verify input image exists
if (-not (Test-Path $inputImage)) {
    Write-Error "Input image not found: $inputImage"
    exit 1
}

# Create output directory if it doesn't exist
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

# Set environment variables for TripoSR
$env:PYTHONPATH = "$triposrDir;$env:PYTHONPATH"

# Change to TripoSR directory and run
Push-Location $triposrDir
try {
    Write-Host "Running TripoSR with input: $inputImage, output: $outputDir"
    python run.py $inputImage --output-dir $outputDir --bake-texture --render
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Error "TripoSR failed with exit code: $exitCode"
        exit $exitCode
    }
    Write-Host "TripoSR completed successfully"
    
    # List generated files for debugging
    Write-Host "Generated files:"
    Get-ChildItem $outputDir -Recurse | ForEach-Object { Write-Host "  $($_.FullName)" }
    
} finally {
    Pop-Location
}
