Param(
    [Parameter(Mandatory=$true)]
    [string]$PythonPath
)

$cfg = Join-Path $PSScriptRoot '..\backend\config.yaml'
if (-not (Test-Path $cfg)) {
    Write-Error "Could not find backend/config.yaml at $cfg"
    exit 1
}

$content = Get-Content $cfg -Raw
# Replace existing TRIPOSR_PYTHON: null or any existing value with new path
$escaped = $PythonPath -replace '\\','\\\\'
if ($content -match 'TRIPOSR_PYTHON:') {
    # use regex-safe replacement to replace the whole line
    $new = $content -replace 'TRIPOSR_PYTHON:.*', "TRIPOSR_PYTHON: \"$escaped\""
} else {
    # append at end of file
    $append = "`nTRIPOSR_PYTHON: \"$escaped\"`n"
    $new = $content + $append
}

Set-Content -Path $cfg -Value $new -Encoding UTF8
Write-Output "Updated backend/config.yaml with TRIPOSR_PYTHON: $PythonPath"
Write-Output "Restart your server (uvicorn) after this change to apply it."