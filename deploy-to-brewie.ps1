param(
    [Parameter(Mandatory = $true)]
    [Alias("Host", "BrewieHost")]
    [string]$HostName,

    [string]$User = "root",
    [string]$Password = "",
    [string]$RemoteDir = "/root/rebrewie-machine-tools",
    [switch]$DryRun,
    [switch]$RunProbe,
    [string[]]$SshOption = @()
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found. Install or enable it, then try again."
    }
}

function Quote-Bash {
    param([string]$Value)

    return "'" + ($Value -replace "'", "'\''") + "'"
}

if ($HostName -match "[<>]") {
    throw "Do not include angle brackets in HostName. Use -HostName 192.168.1.XXX, not -HostName <192.168.1.XXX>."
}

Require-Command tar

$UsePutty = -not [string]::IsNullOrEmpty($Password)
if ($UsePutty) {
    Require-Command plink
    Require-Command pscp
}
else {
    Require-Command ssh
    Require-Command scp
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceDir = Join-Path $ProjectRoot "contrib\brewie-machine"
if (-not (Test-Path $SourceDir)) {
    throw "Missing Brewie helper directory: $SourceDir"
}

$ArchivePath = Join-Path ([System.IO.Path]::GetTempPath()) ("rebrewie-machine-tools-{0}.tar.gz" -f ([guid]::NewGuid()))
$RemoteArchive = "/tmp/" + ([System.IO.Path]::GetFileName($ArchivePath))
$Target = if ([string]::IsNullOrWhiteSpace($User)) { $HostName } else { "$User@$HostName" }

try {
    Write-Host "Creating Brewie helper archive from $SourceDir"
    Push-Location $SourceDir
    & tar -czf $ArchivePath "."
    Pop-Location

    if ($LASTEXITCODE -ne 0) {
        throw "tar failed with exit code $LASTEXITCODE."
    }

    if ($DryRun) {
        Write-Host "Dry run: archive created locally at $ArchivePath"
        Write-Host "Dry run: would copy to ${Target}:$RemoteArchive and extract into $RemoteDir"
        return
    }

    Write-Host "Copying archive to ${Target}:$RemoteArchive"
    if ($UsePutty) {
        & pscp -scp -batch -pw $Password @SshOption $ArchivePath "${Target}:${RemoteArchive}"
    }
    else {
        & scp @SshOption $ArchivePath "${Target}:${RemoteArchive}"
    }

    if ($LASTEXITCODE -ne 0) {
        throw "file copy failed with exit code $LASTEXITCODE."
    }

    $probeCommand = if ($RunProbe) {
        "sh $(Quote-Bash "$RemoteDir/brewie_machine_probe.sh") > /tmp/brewie_probe.txt; echo 'Probe written to /tmp/brewie_probe.txt'; sed -n '1,80p' /tmp/brewie_probe.txt"
    }
    else {
        "echo 'Helpers deployed. Run: sh $(Quote-Bash "$RemoteDir/brewie_machine_probe.sh") > /tmp/brewie_probe.txt'"
    }

    $remoteCommand = @(
        "set -e",
        "mkdir -p $(Quote-Bash $RemoteDir)",
        "gzip -dc $(Quote-Bash $RemoteArchive) | (cd $(Quote-Bash $RemoteDir) && tar -xf -)",
        "chmod +x $(Quote-Bash "$RemoteDir/brewie_machine_probe.sh") $(Quote-Bash "$RemoteDir/brewie_bridge_inspect.sh") $(Quote-Bash "$RemoteDir/brewie_tcp_shim.sh") $(Quote-Bash "$RemoteDir/rebrewie_tcp_serial_bridge.py") $(Quote-Bash "$RemoteDir/brewie_capture_bridge.py") 2>/dev/null || true",
        "rm -f $(Quote-Bash $RemoteArchive)",
        "ls -l $(Quote-Bash $RemoteDir)",
        $probeCommand
    ) -join "; "

    Write-Host "Installing Brewie helpers on $Target"
    if ($UsePutty) {
        & plink -batch -ssh -pw $Password @SshOption $Target "sh -lc $(Quote-Bash $remoteCommand)"
    }
    else {
        & ssh @SshOption $Target "sh" "-lc" $remoteCommand
    }

    if ($LASTEXITCODE -ne 0) {
        throw "SSH deployment failed with exit code $LASTEXITCODE."
    }

    Write-Host "Brewie helper deploy complete."
}
finally {
    if (Test-Path $ArchivePath) {
        Remove-Item -LiteralPath $ArchivePath -Force
    }
}
