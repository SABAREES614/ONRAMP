# Start the Neuro-SAN server with the ONRAMP agent network.
# Run from the project root in its own PowerShell terminal.
# Prerequisite: uv on PATH (installer puts it at $HOME\.local\bin).

$env:AGENT_MANIFEST_FILE = (Resolve-Path .\registries\manifest.hocon).Path
$env:AGENT_TOOL_PATH = (Resolve-Path .\src).Path

Write-Host "Starting Neuro-SAN server (127.0.0.1:8080) with ONRAMP network..."
Write-Host "  manifest : $env:AGENT_MANIFEST_FILE"
Write-Host "  tool path: $env:AGENT_TOOL_PATH"

uv run ns run --server-only --server-host 127.0.0.1 --server-http-port 8080
