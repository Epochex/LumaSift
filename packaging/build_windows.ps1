param(
    [string]$Configuration = "Release",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

python -m pip install -e ".[dev,raw]"
python -m pytest -q

if (Test-Path dist) { Remove-Item -LiteralPath dist -Recurse -Force }
if (Test-Path build) { Remove-Item -LiteralPath build -Recurse -Force }

pyinstaller --clean --noconfirm packaging/LumaSift.spec

$AppDistDir = Join-Path $Root "dist\LumaSift"
foreach ($RuntimeDir in @("outputs", "runs", ".lumasift_cache")) {
    $RuntimePath = Join-Path $AppDistDir $RuntimeDir
    if (Test-Path -LiteralPath $RuntimePath) {
        Remove-Item -LiteralPath $RuntimePath -Recurse -Force
    }
}
Get-ChildItem -LiteralPath $AppDistDir -Recurse -Include *.log -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

$PackageDir = Join-Path $Root "dist"
$ZipPath = Join-Path $PackageDir "LumaSift-Windows-Portable.zip"
if (Test-Path $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
Compress-Archive -Path (Join-Path $PackageDir "LumaSift") -DestinationPath $ZipPath

Write-Host "Built portable package:"
Write-Host $ZipPath

if (-not $SkipInstaller) {
    $Iscc = Get-Command iscc -ErrorAction SilentlyContinue
    if (-not $Iscc) {
        $Candidates = @(
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
        )
        foreach ($Candidate in $Candidates) {
            if ($Candidate -and (Test-Path -LiteralPath $Candidate)) {
                $Iscc = Get-Item -LiteralPath $Candidate
                break
            }
        }
    }
    if (-not $Iscc) {
        $Winget = Get-Command winget -ErrorAction SilentlyContinue
        if ($Winget) {
            Write-Host "Inno Setup compiler not found. Trying winget install..."
            winget install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements
            $Iscc = Get-Command iscc -ErrorAction SilentlyContinue
            if (-not $Iscc) {
                $LocalIscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
                if (Test-Path -LiteralPath $LocalIscc) {
                    $Iscc = Get-Item -LiteralPath $LocalIscc
                }
            }
        }
    }

    if ($Iscc) {
        & $Iscc.Source packaging\LumaSiftInstaller.iss
        Write-Host "Built installer:"
        Write-Host (Join-Path $PackageDir "installer\LumaSiftSetup.exe")
    } else {
        Write-Warning "Inno Setup compiler not available. Portable zip was built; installer script is at packaging\LumaSiftInstaller.iss."
    }
}
