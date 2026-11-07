param(
    [int]$Count = 20,
    [int]$DelayMs = 1500
)

$patterns = 'PPSA09009|createApp|appParam|ProcessStarter|download0|LaunchFlow|SplashScreen|0x80a4|107694|LNC_|SceLnc|SIGSEGV|signal|ERROR|error|fail|crash|Crash'
$seen = @{}

for ($i = 0; $i -lt $Count; $i++) {
    $r = & "$PSScriptRoot\mcp.ps1" -Tool shell_run -ArgsJson '{"console":"192.168.1.197","cmd":"klog -n 30000"}'
    try {
        $o = ($r | ConvertFrom-Json).result.structuredContent.stdout
    } catch {
        Start-Sleep -Milliseconds $DelayMs
        continue
    }
    foreach ($line in ($o -split "`n")) {
        if ($line -match $patterns) {
            if (-not $seen.ContainsKey($line)) {
                $seen[$line] = $true
                Write-Output $line
            }
        }
    }
    Start-Sleep -Milliseconds $DelayMs
}
