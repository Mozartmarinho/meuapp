# Confia no certificado local (Current User \ Trusted Root).
# Uso (na raiz do repo):
#   powershell -ExecutionPolicy Bypass -File .\trust_local_cert.ps1
# Depois: feche e reabra Chrome/Edge e abra https://127.0.0.1/
#
# Só afeta ESTE usuário nesta máquina. Outros PCs / produção precisam de CA pública
# (ex.: Let's Encrypt) ou de repetir este passo.

param(
    [string]$CertPath = (Join-Path $PSScriptRoot 'certs\cert.pem')
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $CertPath)) {
    Write-Error "Certificado não encontrado: $CertPath`nGere com: .\.venv\Scripts\python.exe generate_certs.py"
}

$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertPath)
$store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
    [System.Security.Cryptography.X509Certificates.StoreName]::Root,
    [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
)
$store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
try {
    $existing = $store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
    if ($existing) {
        Write-Host "Já confiável: $($cert.Thumbprint)"
    } else {
        $store.Add($cert)
        Write-Host "Importado em CurrentUser\Root: $($cert.Thumbprint)"
    }
} finally {
    $store.Close()
}

Write-Host "Subject: $($cert.Subject)"
Write-Host "Reinicie o Chrome/Edge e abra https://127.0.0.1/"
Write-Host "Se regenerar o cert (--force), rode este script de novo."
