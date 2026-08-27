# Abre /nutricao so quando o Flask novo responder com o commit esperado.
# Evita o navegador cair no processo antigo ainda preso na porta 80.
param(
    [string]$ExpectedRev = '',
    [int]$TimeoutSec = 45
)

$ErrorActionPreference = 'SilentlyContinue'
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$ok = $false

do {
    try {
        $stamp = [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
        $r = Invoke-WebRequest -Uri ("http://127.0.0.1/nutricao/versao?t={0}" -f $stamp) -UseBasicParsing -TimeoutSec 2
        $txt = [string]$r.Content
        if ($ExpectedRev) {
            if ($txt -match [regex]::Escape($ExpectedRev)) { $ok = $true; break }
        } elseif ($txt -match 'meuapp') {
            $ok = $true
            break
        }
    } catch {}
    Start-Sleep -Milliseconds 400
} while ((Get-Date) -lt $deadline)

if (-not $ok) {
    Write-Host 'AVISO: /nutricao/versao nao confirmou o commit novo a tempo. Nao abri o navegador na pagina antiga.'
    exit 1
}

$open = 'http://127.0.0.1/nutricao?v=' + [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
Start-Process $open
exit 0
