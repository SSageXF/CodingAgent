param(
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"

$template = Join-Path $PSScriptRoot "video_demo"
if (-not (Test-Path -LiteralPath $template -PathType Container)) {
    throw "Video demo template was not found: $template"
}

if ([string]::IsNullOrWhiteSpace($Destination)) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $Destination = Join-Path $env:TEMP "EvidenceCoderVideoDemo-$stamp"
}

$destinationPath = [System.IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $destinationPath) {
    throw "Destination already exists; choose a new empty path: $destinationPath"
}

$null = New-Item -ItemType Directory -Path $destinationPath
Get-ChildItem -LiteralPath $template -Force | Copy-Item -Destination $destinationPath -Recurse

Push-Location $destinationPath
try {
    $null = & git init --quiet
    if ($LASTEXITCODE -ne 0) { throw "git init failed" }

    $null = & git config user.name "EvidenceCoder Demo"
    if ($LASTEXITCODE -ne 0) { throw "git config user.name failed" }

    $null = & git config user.email "demo@example.invalid"
    if ($LASTEXITCODE -ne 0) { throw "git config user.email failed" }

    $null = & git config core.autocrlf false
    if ($LASTEXITCODE -ne 0) { throw "git config core.autocrlf failed" }

    $null = & git add .
    if ($LASTEXITCODE -ne 0) { throw "git add failed" }

    $null = & git commit --quiet -m "Prepare reproducible EvidenceCoder video demo"
    if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
}
finally {
    Pop-Location
}

Write-Output $destinationPath
