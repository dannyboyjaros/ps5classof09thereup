param(
    [Parameter(Mandatory = $true)][string]$Tool,
    [string]$ArgsJson = '{}'
)

$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:19113/mcp'

function Invoke-Rpc {
    param([string]$Body, [string]$Session)
    $headers = @{ Accept = 'application/json, text/event-stream'; 'Content-Type' = 'application/json' }
    if ($Session) { $headers['Mcp-Session-Id'] = $Session }
    $response = Invoke-WebRequest -Uri $base -Method Post -Headers $headers -Body $Body -TimeoutSec 300 -UseBasicParsing
    [pscustomobject]@{ Session = $response.Headers['Mcp-Session-Id']; Json = $response.Content }
}

$init = Invoke-Rpc -Body '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"opencode","version":"1.0"}}}'

$payload = @{
    jsonrpc = '2.0'
    id      = 2
    method  = 'tools/call'
    params  = @{ name = $Tool; arguments = (ConvertFrom-Json $ArgsJson) }
} | ConvertTo-Json -Depth 30 -Compress

(Invoke-Rpc -Body $payload -Session $init.Session).Json
