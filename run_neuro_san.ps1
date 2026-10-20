# PowerShell script to launch Neuro-SAN with .env environment variables loaded
Write-Host "Loading .env configuration..."
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
            $parts = $line.Split('=', 2)
            $varName = $parts[0].Trim()
            $varVal = $parts[1].Trim()
            [System.Environment]::SetEnvironmentVariable($varName, $varVal)
            $masked = if ($varName.ToLower().Contains("key") -and $varVal.Length -gt 8) { $varVal.Substring(0, 4) + "..." + $varVal.Substring($varVal.Length - 4) } else { $varVal }
            Write-Host "  $varName = $masked"
        }
    }
}

$env:PYTHONPATH = "src"
$env:AGENT_MANIFEST_FILE = (Resolve-Path .\registries\manifest.hocon).Path
$env:AGENT_TOOL_PATH = (Resolve-Path .\src).Path

Write-Host "`nStarting Neuro-SAN server (host: 127.0.0.1, port: 8080, model: $env:ONRAMP_MODEL, provider: $env:ONRAMP_LLM_CLASS)..."
.\.venv\Scripts\ns.exe run --server-only --server-host 127.0.0.1 --server-http-port 8080
