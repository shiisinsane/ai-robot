[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$checks = [System.Collections.Generic.List[object]]::new()

function Add-Check {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Detail
    )

    $checks.Add([pscustomobject]@{
        Check  = $Name
        Status = $Status
        Detail = $Detail
    })
}

function Test-Command {
    param(
        [string]$Name,
        [string[]]$Arguments = @('--version')
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        Add-Check $Name 'MISSING' 'Command not found'
        return
    }

    try {
        $allOutput = & $Name @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        $output = $allOutput | Select-Object -First 1
        $detail = (($output | Out-String).Trim())
        if ($exitCode -eq 0) {
            Add-Check $Name 'OK' $detail
        }
        else {
            Add-Check $Name 'WARN' "Exit $exitCode`: $detail"
        }
    }
    catch {
        Add-Check $Name 'WARN' $_.Exception.Message
    }
}

$osDescription = [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
Add-Check 'Windows host' 'INFO' $osDescription

Test-Command 'git'
Test-Command 'code'
Test-Command 'wsl.exe' @('--status')

$workspaceRoot = [System.IO.Path]::GetPathRoot((Get-Location).Path)
$disk = [System.IO.DriveInfo]::new($workspaceRoot)
if ($disk.IsReady) {
    $freeGb = [math]::Round($disk.AvailableFreeSpace / 1GB, 2)
    $status = if ($freeGb -ge 20) { 'OK' } else { 'WARN' }
    Add-Check 'Workspace disk free' $status "$freeGb GB"
}

$checks | Format-Table -AutoSize

if ($checks.Status -contains 'MISSING') {
    exit 1
}
