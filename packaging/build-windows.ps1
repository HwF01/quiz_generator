#requires -Version 5.1
<#
.SYNOPSIS
  Build a Windows portable payload and (if Inno Setup is installed) QuizGen-Setup.exe.

.DESCRIPTION
  Caches runtimes under packaging/vendor/. Does not copy .env or API keys.
#>
param(
    [string]$PythonVersion = "3.12.10",
    [string]$NodeVersion = "20.18.1",
    [switch]$SkipDownloads,
    [switch]$SkipFrontend,
    [switch]$IncludeOcr
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$PackagingRoot = $PSScriptRoot
$RepoRoot = Split-Path -Parent $PackagingRoot
$Vendor = Join-Path $PackagingRoot "vendor"
$Dist = Join-Path $PackagingRoot "dist"
$Payload = Join-Path $Dist "payload"
$OcrPayload = Join-Path $Dist "ocr-payload"

New-Item -ItemType Directory -Force -Path $Vendor, $Dist | Out-Null

function Assert-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing command: $Name"
    }
}

function Invoke-Download($Url, $Dest) {
    if (Test-Path $Dest) {
        Write-Host "Using cache $Dest"
        return
    }
    Write-Host "Downloading $Url"
    $tmp = "$Dest.partial"
    Invoke-WebRequest -Uri $Url -OutFile $tmp -UseBasicParsing
    Move-Item -Force $tmp $Dest
}

function Expand-ZipTo($Zip, $Dest) {
    if (Test-Path $Dest) {
        Remove-Item -Recurse -Force $Dest
    }
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Expand-Archive -Path $Zip -DestinationPath $Dest -Force
}

function Copy-Robo($Src, $Dst, $ExtraArgs = @()) {
    New-Item -ItemType Directory -Force -Path $Dst | Out-Null
    & robocopy $Src $Dst /E /NFL /NDL /NJH /NJS /nc /ns /np @ExtraArgs | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed with code $LASTEXITCODE from $Src"
    }
}

Write-Host "==> Cleaning payload"
if (Test-Path $Payload) {
    Remove-Item -Recurse -Force $Payload
}
New-Item -ItemType Directory -Force -Path $Payload | Out-Null

$PyNupkg = Join-Path $Vendor "python-$PythonVersion.nupkg"
$NodeZip = Join-Path $Vendor "node-v$NodeVersion-win-x64.zip"
$PyUrl = "https://www.nuget.org/api/v2/package/python/$PythonVersion"
$NodeUrl = "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-x64.zip"

if (-not $SkipDownloads) {
    Invoke-Download $PyUrl $PyNupkg
    Invoke-Download $NodeUrl $NodeZip
}

Write-Host "==> Python runtime"
$PyExtract = Join-Path $Vendor "python-$PythonVersion"
if (-not (Test-Path (Join-Path $PyExtract "tools\python.exe"))) {
    if (-not (Test-Path $PyNupkg)) { throw "Python nupkg missing: $PyNupkg" }
    Expand-ZipTo $PyNupkg $PyExtract
}
$PyTools = Join-Path $PyExtract "tools"
if (-not (Test-Path (Join-Path $PyTools "python.exe"))) {
    throw "Unexpected nuget python layout under $PyExtract"
}
Copy-Robo $PyTools (Join-Path $Payload "runtime\python")
$PayloadPy = Join-Path $Payload "runtime\python\python.exe"

Write-Host "==> Installing Python packages"
$ReqFile = Join-Path $env:TEMP "quizgen-pack-req.txt"
Get-Content (Join-Path $RepoRoot "backend\requirements.txt") |
    Where-Object { $_ -notmatch 'pytest' } |
    Set-Content -Encoding utf8 $ReqFile
Add-Content $ReqFile "pystray"
& $PayloadPy -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) {
    Write-Host "ensurepip failed, trying get-pip.py"
    $GetPip = Join-Path $Vendor "get-pip.py"
    if (-not $SkipDownloads) {
        Invoke-Download "https://bootstrap.pypa.io/get-pip.py" $GetPip
    }
    if (-not (Test-Path $GetPip)) { throw "get-pip.py missing at $GetPip" }
    & $PayloadPy $GetPip
    if ($LASTEXITCODE -ne 0) { throw "get-pip failed" }
}
& $PayloadPy -m pip install --upgrade pip
& $PayloadPy -m pip install -r $ReqFile
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "==> Node runtime"
$NodeExtract = Join-Path $Vendor "node-v$NodeVersion-win-x64"
if (-not (Test-Path (Join-Path $NodeExtract "node.exe"))) {
    if (-not (Test-Path $NodeZip)) { throw "Node zip missing: $NodeZip" }
    $NodeUnpack = Join-Path $Vendor "node-unpack"
    Expand-ZipTo $NodeZip $NodeUnpack
    $Inner = Get-ChildItem $NodeUnpack -Directory | Select-Object -First 1
    if (Test-Path (Join-Path $NodeUnpack "node.exe")) {
        $NodeExtract = $NodeUnpack
    } elseif ($Inner) {
        $NodeExtract = $Inner.FullName
    } else {
        throw "Could not find node.exe in $NodeZip"
    }
}
Copy-Robo $NodeExtract (Join-Path $Payload "runtime\node")

Write-Host "==> Backend + prompts"
New-Item -ItemType Directory -Force -Path (Join-Path $Payload "app\backend") | Out-Null
Copy-Robo (Join-Path $RepoRoot "backend\app") (Join-Path $Payload "app\backend\app") @("/XD", "__pycache__")
Copy-Item (Join-Path $RepoRoot "backend\requirements.txt") (Join-Path $Payload "app\backend\requirements.txt")
Copy-Robo (Join-Path $RepoRoot "prompts") (Join-Path $Payload "app\prompts")
Copy-Item (Join-Path $PackagingRoot "launcher.py") (Join-Path $Payload "launcher.py")
Copy-Item (Join-Path $PackagingRoot "config.env.template") (Join-Path $Payload "config.env.template")
@"
@echo off
cd /d "%~dp0"
runtime\python\python.exe launcher.py
"@ | Set-Content -Encoding ascii (Join-Path $Payload "QuizGen.cmd")

if (-not $SkipFrontend) {
    Write-Host "==> Frontend standalone"
    Assert-Command npm
    $Frontend = Join-Path $RepoRoot "frontend"
    Push-Location $Frontend
    try {
        if (-not (Test-Path "node_modules")) {
            npm ci
            if ($LASTEXITCODE -ne 0) { npm install }
        }
        $env:INTERNAL_API_URL = "http://127.0.0.1:8000"
        $env:NEXT_TELEMETRY_DISABLED = "1"
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "next build failed" }
    } finally {
        Pop-Location
    }
    $FeDest = Join-Path $Payload "app\frontend"
    $Standalone = Join-Path $Frontend ".next\standalone"
    if (Test-Path (Join-Path $Standalone "server.js")) {
        Copy-Robo $Standalone $FeDest
    } elseif (Test-Path (Join-Path $Standalone "frontend\server.js")) {
        Copy-Robo (Join-Path $Standalone "frontend") $FeDest
    } else {
        throw "Next standalone output not found (server.js). Check next.config output: 'standalone'."
    }
    $StaticSrc = Join-Path $Frontend ".next\static"
    $StaticDst = Join-Path $FeDest ".next\static"
    if (Test-Path $StaticSrc) {
        Copy-Robo $StaticSrc $StaticDst
    }
    $PublicSrc = Join-Path $Frontend "public"
    if (Test-Path $PublicSrc) {
        Copy-Robo $PublicSrc (Join-Path $FeDest "public")
    }
}

Write-Host "==> Icon"
$IconPy = @"
from pathlib import Path
from PIL import Image, ImageDraw
p = Path(r'$Payload') / 'quizgen.ico'
img = Image.new('RGBA', (256, 256), (15, 118, 110, 255))
d = ImageDraw.Draw(img)
d.rounded_rectangle((32, 32, 224, 224), radius=28, outline=(255, 255, 255, 255), width=14)
d.rectangle((88, 88, 168, 168), fill=(255, 255, 255, 235))
img.save(p, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(p)
"@
$IconScript = Join-Path $env:TEMP "quizgen-icon.py"
Set-Content -Path $IconScript -Value $IconPy -Encoding utf8
& $PayloadPy $IconScript
Copy-Item (Join-Path $Payload "quizgen.ico") (Join-Path $PackagingRoot "quizgen.ico") -Force

if ($IncludeOcr) {
    $TessSrc = Join-Path $Vendor "tesseract"
    $TessExe = Join-Path $TessSrc "tesseract.exe"
    if (-not (Test-Path $TessExe)) {
        Write-Warning "OCR requested but $TessExe not found. Skip OCR payload."
    } else {
        Write-Host "==> OCR payload"
        if (Test-Path $OcrPayload) { Remove-Item -Recurse -Force $OcrPayload }
        Copy-Robo $TessSrc $OcrPayload
    }
} elseif (Test-Path $OcrPayload) {
    Remove-Item -Recurse -Force $OcrPayload
}

Write-Host "==> Portable zip"
$ZipPath = Join-Path $Dist "QuizGen-portable.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath }
Compress-Archive -Path (Join-Path $Payload "*") -DestinationPath $ZipPath

$Iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "ISCC.exe"
) | Where-Object { $_ -eq "ISCC.exe" -or (Test-Path $_) } | Select-Object -First 1

$IsccCmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($IsccCmd) {
    $Iscc = $IsccCmd.Source
} elseif (Test-Path "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") {
    $Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
} elseif (Test-Path "$env:ProgramFiles\Inno Setup 6\ISCC.exe") {
    $Iscc = "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
} else {
    $Iscc = $null
}

if ($Iscc) {
    Write-Host "==> Inno Setup ($Iscc)"
    Push-Location $PackagingRoot
    try {
        & $Iscc "quizgen.iss"
        if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }
    } finally {
        Pop-Location
    }
} else {
    Write-Warning "Inno Setup 6 not found. Portable zip is ready: $ZipPath"
    Write-Warning "Install Inno Setup to produce QuizGen-Setup.exe"
}

Write-Host "Done."
Write-Host "  Portable: $ZipPath"
$Setup = Join-Path $Dist "QuizGen-Setup.exe"
if (Test-Path $Setup) {
    Write-Host "  Installer: $Setup"
}
