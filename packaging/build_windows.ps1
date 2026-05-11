param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

python -m pip install -e ".[dev,raw]"
python -m pytest -q

if (Test-Path dist) { Remove-Item -LiteralPath dist -Recurse -Force }
if (Test-Path build) { Remove-Item -LiteralPath build -Recurse -Force }

pyinstaller --clean --noconfirm packaging/LumaSift.spec

$PackageDir = Join-Path $Root "dist"
$ZipPath = Join-Path $PackageDir "LumaSift-Windows-Portable.zip"
if (Test-Path $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
Compress-Archive -Path (Join-Path $PackageDir "LumaSift") -DestinationPath $ZipPath

Write-Host "Built portable package:"
Write-Host $ZipPath
