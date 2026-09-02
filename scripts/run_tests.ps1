# Task #16: run backend pytest suite (backend/.venv preferred, system python fallback)
$ErrorActionPreference = "Stop"
$backend = Resolve-Path (Join-Path $PSScriptRoot "..\backend")
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
} else {
    $python = "python"
}
Write-Host "[run_tests] backend = $backend"
Write-Host "[run_tests] python  = $python"
Push-Location $backend
try {
    & $python -m pytest tests
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
Write-Host "[run_tests] pytest exit code = $exitCode"
exit $exitCode
