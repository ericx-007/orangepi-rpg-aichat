$ErrorActionPreference='Stop'
$workspaceRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$pythonwPath=Join-Path (Split-Path (Get-Command python.exe).Source) 'pythonw.exe'
if(-not(Test-Path -LiteralPath $pythonwPath)){throw 'pythonw.exe is required'}
$scriptPath=Join-Path $PSScriptRoot 'supervise-runtime.py'
$startupDirectory=[Environment]::GetFolderPath('Startup')
$shortcutPath=Join-Path $startupDirectory 'OrangePi QQ Runtime.lnk'
$shellObject=New-Object -ComObject WScript.Shell
$shortcut=$shellObject.CreateShortcut($shortcutPath)
$description='OrangePi QQ runtime supervisor for current user'
if((Test-Path -LiteralPath $shortcutPath) -and $shortcut.Description -ne $description){throw 'An unrelated startup shortcut uses this name'}
$shortcut.TargetPath=$pythonwPath
$shortcut.Arguments='"'+$scriptPath+'"'
$shortcut.WorkingDirectory=$workspaceRoot
$shortcut.WindowStyle=7
$shortcut.Description=$description
$shortcut.Save()
$stopFlag=Join-Path $workspaceRoot 'qq-runtime/state/supervisor.stop'
if(Test-Path -LiteralPath $stopFlag){Remove-Item -LiteralPath $stopFlag}
$startupInfo=New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}
$commandLine='"'+$pythonwPath+'" "'+$scriptPath+'"'
$result=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$commandLine;CurrentDirectory=$workspaceRoot;ProcessStartupInformation=$startupInfo}
if($result.ReturnValue -ne 0){throw "Supervisor launch failed: $($result.ReturnValue)"}
$check=$shellObject.CreateShortcut($shortcutPath)
if($check.TargetPath -ne $pythonwPath -or $check.Arguments -ne ('"'+$scriptPath+'"')){throw 'Startup shortcut did not persist correctly'}
@{installed_at=[DateTimeOffset]::Now.ToUnixTimeSeconds();shortcut=$shortcutPath;target=$check.TargetPath;arguments=$check.Arguments;working_directory=$check.WorkingDirectory;window_style=$check.WindowStyle;launch_pid=$result.ProcessId;trigger='current-user Windows logon';full_pc_reboot_tested=$false} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $workspaceRoot 'qq-runtime/state/startup-installation.json') -Encoding UTF8
Write-Output 'CURRENT_USER_QQ_STARTUP_INSTALLED_AND_LAUNCHED'
