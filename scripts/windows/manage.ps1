param([ValidateSet('install', 'run', 'build')][string]$Action)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
Set-Location -LiteralPath $Root
$env:PYTHONPATH = Join-Path $Root 'src'
$env:PYTHONUTF8 = '1'
$Python = Join-Path $Root '.venv/Scripts/python.exe'

function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Exe" }
}

try {
    if ($Action -eq 'install') {
        if (-not (Test-Path -LiteralPath $Python)) {
            $Created = $false
            $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
            if ($Launcher) {
                foreach ($Version in @('-3.13', '-3.12', '-3.11', '-3.10')) {
                    & $Launcher.Source $Version -c 'import sys; sys.exit(not (sys.maxsize > 2**32))' 2>$null
                    if ($LASTEXITCODE -eq 0) {
                        Invoke-Checked $Launcher.Source @($Version, '-m', 'venv', '.venv')
                        $Created = $true
                        break
                    }
                }
            }
            if (-not $Created) {
                $Candidate = Get-Command python.exe -ErrorAction SilentlyContinue
                if ($Candidate) {
                    & $Candidate.Source -c 'import sys; sys.exit(not ((3,10) <= sys.version_info[:2] <= (3,13) and sys.maxsize > 2**32))'
                    if ($LASTEXITCODE -eq 0) {
                        Invoke-Checked $Candidate.Source @('-m', 'venv', '.venv')
                        $Created = $true
                    }
                }
            }
            if (-not $Created) { throw 'Install 64-bit Python 3.10-3.13 from https://www.python.org/downloads/windows/ (include the Python launcher), then retry.' }
        }
        Invoke-Checked $Python @('-c', 'import sys; sys.exit(not ((3,10) <= sys.version_info[:2] <= (3,13) and sys.maxsize > 2**32))')
        Invoke-Checked $Python @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', 'requirements.txt')
        Invoke-Checked $Python @('scripts/install_native.py')
        Write-Host 'Installation complete. Run the Windows launch .bat file. Models download on first use.'
    } elseif ($Action -eq 'run') {
        if (-not (Test-Path -LiteralPath $Python)) { throw 'Run the Windows install .bat file first.' }
        Invoke-Checked $Python @('-c', 'import PySide6.QtWidgets')
        # launcher.py starts the GUI independently and redirects errors to launcher.log.
        Invoke-Checked $Python @('-m', 'soundnote')
    } else {
        if (-not (Test-Path -LiteralPath $Python)) { throw 'Run the Windows install .bat file first.' }
        Invoke-Checked $Python @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', 'scripts/requirements-build.txt')
        Invoke-Checked $Python @('scripts/install_native.py')
        Invoke-Checked $Python @('scripts/build.py')
    }
    exit 0
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    exit 1
}
