# Read the manager config file to determine where we should log update messages
$configFilePath = "config.json" # relative path should remain the same
$configContent = Get-Content -Path $configFilePath -Raw
$jsonConfig = $configContent | ConvertFrom-Json
$logPath = $jsonConfig.UpdateLogPath

# Function to write a message to the log file
function Write-Log {
    param (
        [string]$message,
        [string]$logFilePath
    )

    # Get the current timestamp
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    # Format the log message with a timestamp
    $logMessage = "$timestamp - $message"

    # Append the log message to the log file
    $logMessage | Add-Content -Path $logFilePath
}

$PendingReboot = (Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending") -or
                 (Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired") -or
                 (Test-Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\PendingFileRenameOperations")
                 
# Write-Host "Pending reboot: $PendingReboot"
Write-Log -message "Pending reboot status: $PendingReboot" -logFilePath $logPath
if ($PendingReboot) {
    Write-Log -message "Rebooting machine to apply updates" -logFilePath $logPath
    Restart-Computer -Force
}
