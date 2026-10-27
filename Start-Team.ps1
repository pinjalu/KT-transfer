param(
    [string]$Address = '192.168.0.149',
    [int]$Port = 8443,
    [string]$CertificateDirectory = (Join-Path $PSScriptRoot 'data\team-tls')
)
$ErrorActionPreference = 'Stop'
$ktPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$ktCert = Join-Path $CertificateDirectory 'server.pem'
$ktKey = Join-Path $CertificateDirectory 'server-key.pem'
foreach ($ktRequired in @($ktPython, $ktCert, $ktKey)) {
    if (-not (Test-Path -LiteralPath $ktRequired -PathType Leaf)) {
        throw "Required file is missing: $ktRequired. See docs/TEAM_OFFICE_SETUP.md."
    }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    & $ktPython -m pka --host $Address --port $Port --team-origin "https://${Address}:$Port" --ssl-certfile $ktCert --ssl-keyfile $ktKey
    if ($LASTEXITCODE -ne 0) { throw 'The team server could not start. Check the message above.' }
} finally { Pop-Location }
