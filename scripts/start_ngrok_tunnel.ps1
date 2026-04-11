param(
    [int]$Port = 8010
)

$ngrok = Get-Command ngrok -ErrorAction SilentlyContinue
if (-not $ngrok) {
    Write-Error "ngrok is not installed or not on PATH. Install ngrok first."
    exit 1
}

Write-Host "Starting ngrok tunnel for http://localhost:$Port"
& ngrok http $Port
