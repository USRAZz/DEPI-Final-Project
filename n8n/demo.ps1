# Start a throwaway n8n with the four SecureFin workflows ready to try. No .env, no credentials, no accounts.
#   powershell -ExecutionPolicy Bypass -File n8n\demo.ps1          start (or restart) the demo
#   powershell -ExecutionPolicy Bypass -File n8n\demo.ps1 -Stop    remove it
# It does not touch any other n8n on this machine: its own container (securefin-n8n-demo) on its own port.
param([switch]$Stop, [int]$Port = 5680)

$name = "securefin-n8n-demo"
$workflows = Join-Path $PSScriptRoot "workflows"
$base = "http://localhost:$Port"

docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Host "Docker is not running. Start Docker Desktop, wait until it is ready, then run this again." -ForegroundColor Red; exit 1 }

docker rm -f $name *> $null
if ($Stop) { Write-Host "Demo removed."; exit 0 }

# Import the workflow files, publish them, then start n8n. Everything inside the container is deleted on -Stop.
$boot = 'n8n import:workflow --separate --input=/workflows && for w in sfErrorAlerts0001 sfInvoiceIntake001 sfDecisionNotify01 sfIntegrityRun001; do n8n publish:workflow --id=$w; done; exec n8n start'
docker run -d --name $name -p "127.0.0.1:${Port}:5678" -e "WEBHOOK_URL=$base/" -e "GENERIC_TIMEZONE=Africa/Cairo" `
    -v "${workflows}:/workflows:ro" --entrypoint sh n8nio/n8n:2.46.7 -c $boot | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "Could not start the container (is port $Port already in use? try -Port 5681)." -ForegroundColor Red; exit 1 }

Write-Host "Starting n8n (about one minute the first time)..."
$ready = $false
foreach ($i in 1..60) {
    Start-Sleep -Seconds 3
    try { if ((Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "$base/form/securefin-test-notify").StatusCode -eq 200) { $ready = $true; break } } catch { }
}
if (-not $ready) { Write-Host "n8n did not become ready. See: docker logs $name" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "Ready. Open each link in your browser, press Run, and read the result on the screen:" -ForegroundColor Green
Write-Host "  0 Error alert            $base/form/securefin-test-alert"
Write-Host "  1 Invoice intake         $base/form/securefin-test-intake      (upload any PDF from tests\fixtures\synthetic\clear_invoices_20)"
Write-Host "  2 Decision notification  $base/form/securefin-test-notify"
Write-Host "  3 Integrity run          $base/form/securefin-test-integrity"
Write-Host ""
Write-Host "To see the workflow diagrams: $base  (it asks you to create a local owner account first)"
Write-Host "To remove the demo:          powershell -ExecutionPolicy Bypass -File n8n\demo.ps1 -Stop"
