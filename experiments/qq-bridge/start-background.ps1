param([ValidateSet('astrbot','napcat','tunnel','all')][string]$Role='all')
$ErrorActionPreference='Stop'
$workspaceRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$pythonwPath=Join-Path (Split-Path (Get-Command python.exe).Source) 'pythonw.exe'
$broker=Join-Path $PSScriptRoot 'run-background.py'
if(-not (Test-Path -LiteralPath $pythonwPath)){throw 'pythonw.exe is required'}
if($Role -in @('all','tunnel')){
    $stopFlag=Join-Path $workspaceRoot 'logs/auto-tunnel.stop'
    if(Test-Path -LiteralPath $stopFlag){Remove-Item -LiteralPath $stopFlag}
}
$roles=if($Role -eq 'all'){@('tunnel','astrbot','napcat')}else{@($Role)}
$startupInfo=New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}
foreach($component in $roles){
    $commandLine='"'+$pythonwPath+'" "'+$broker+'" '+$component
    $result=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$commandLine;CurrentDirectory=$workspaceRoot;ProcessStartupInformation=$startupInfo}
    if($result.ReturnValue -ne 0){throw "Windows background launch failed for $component, code $($result.ReturnValue)"}
    Write-Output "WINDOWS_BACKGROUND_LAUNCH=$component"
}
