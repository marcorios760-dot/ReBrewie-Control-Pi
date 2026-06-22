param(
    [Parameter(Mandatory = $true)]
    [Alias("Host", "PiHost")]
    [string]$HostName,

    [string]$User = "pi",
    [string]$AppDir = "/opt/rebrewie-control-pi",
    [string]$ServiceName = "rebrewie-control-pi",
    [string]$Password = "",
    [switch]$DeployRecipes,
    [switch]$DryRun,
    [string[]]$SshOption = @()
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found. Install or enable OpenSSH/tar, then try again."
    }
}

function Quote-Bash {
    param([string]$Value)

    return "'" + ($Value -replace "'", "'\''") + "'"
}

if ($HostName -match "[<>]") {
    throw "Do not include angle brackets in HostName. Use -HostName 192.168.1.113, not -HostName <192.168.1.113>."
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
$ArchivePath = Join-Path ([System.IO.Path]::GetTempPath()) ("rebrewie-control-pi-{0}.tar.gz" -f ([guid]::NewGuid()))
$RemoteArchive = "/tmp/" + ([System.IO.Path]::GetFileName($ArchivePath))
$RemoteTmp = "/tmp/rebrewie-deploy-" + ([guid]::NewGuid().ToString("N"))
$Target = if ([string]::IsNullOrWhiteSpace($User)) { $HostName } else { "$User@$HostName" }

$tarArgs = @(
    "--exclude=.git",
    "--exclude=.venv",
    "--exclude=__pycache__",
    "--exclude=*.pyc",
    "--exclude=.env",
    "--exclude=.blink-auth.json",
    "--exclude=owner-registration.json",
    "--exclude=machine-registration.json",
    "--exclude=logs"
)

if (-not $DeployRecipes) {
    $tarArgs += "--exclude=recipes"
}

$tarArgs += @("-czf", $ArchivePath, ".")

try {
    Write-Host "Creating deploy archive from $ProjectRoot"
    Push-Location $ProjectRoot
    & tar @tarArgs
    Pop-Location

    if ($LASTEXITCODE -ne 0) {
        throw "tar failed with exit code $LASTEXITCODE."
    }

    Write-Host "Copying archive to ${Target}:$RemoteArchive"
    if ($UsePutty) {
        & pscp -batch -pw $Password @SshOption $ArchivePath "${Target}:${RemoteArchive}"
    }
    else {
        & scp @SshOption $ArchivePath "${Target}:${RemoteArchive}"
    }

    if ($LASTEXITCODE -ne 0) {
        throw "file copy failed with exit code $LASTEXITCODE."
    }

    $remoteExcludes = @(
        "--exclude=.env",
        "--exclude=.blink-auth.json",
        "--exclude=owner-registration.json",
        "--exclude=machine-registration.json",
        "--exclude=.venv/",
        "--exclude=logs/"
    )

    if (-not $DeployRecipes) {
        $remoteExcludes += "--exclude=recipes/"
    }

    $dryRunFlag = if ($DryRun) { "--dry-run --itemize-changes" } else { "" }
    $restartCommand = if ($DryRun) {
        "echo 'Dry run complete; service was not restarted.'"
    } else {
        "cd $(Quote-Bash $AppDir) && if [ ! -x .venv/bin/python ]; then sudo python3 -m venv .venv; fi && sudo .venv/bin/python -m pip install -r requirements.txt && if systemctl list-unit-files $(Quote-Bash "$ServiceName.service") >/dev/null 2>&1; then sudo systemctl restart $(Quote-Bash $ServiceName); sudo systemctl --no-pager --lines=20 status $(Quote-Bash $ServiceName); else echo 'Service not found; run install.sh on the Pi once, then deploy again.'; fi"
    }

    $remoteCommand = @(
        "set -e",
        "rm -rf $(Quote-Bash $RemoteTmp)",
        "mkdir -p $(Quote-Bash $RemoteTmp)",
        "tar -xzf $(Quote-Bash $RemoteArchive) -C $(Quote-Bash $RemoteTmp)",
        "sudo mkdir -p $(Quote-Bash $AppDir)",
        "sudo rsync -a --delete $dryRunFlag $($remoteExcludes -join ' ') $(Quote-Bash "$RemoteTmp/") $(Quote-Bash "$AppDir/")",
        $restartCommand,
        "rm -rf $(Quote-Bash $RemoteTmp) $(Quote-Bash $RemoteArchive)"
    ) -join "; "

    Write-Host "Installing update on $Target"
    if ($UsePutty) {
        & plink -batch -ssh -pw $Password @SshOption $Target "bash -lc $(Quote-Bash $remoteCommand)"
    }
    else {
        & ssh @SshOption -t $Target "bash" "-lc" $remoteCommand
    }

    if ($LASTEXITCODE -ne 0) {
        throw "ssh deployment failed with exit code $LASTEXITCODE."
    }

    Write-Host "Deploy complete."
}
finally {
    if (Test-Path $ArchivePath) {
        Remove-Item -LiteralPath $ArchivePath -Force
    }
}
