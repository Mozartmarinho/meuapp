"""Gera certificado autoassinado local em certs/cert.pem + certs/key.pem.

Uso:
    .\\.venv\\Scripts\\python.exe generate_certs.py
    .\\.venv\\Scripts\\python.exe generate_certs.py --trust   # Windows: confiar no cert (remove aviso)

Requer: cryptography (pip install cryptography)

Em produção use CA pública (Let's Encrypt) num domínio real. Confiar no cert local
só vale nesta máquina/usuário — outros PCs precisam repetir o trust ou usar CA pública.
"""
from __future__ import annotations

import datetime
import ipaddress
import os
import subprocess
import sys
from pathlib import Path


def generate_self_signed_certs(
    cert_dir: str | os.PathLike = 'certs',
    *,
    days: int = 825,
    force: bool = False,
) -> tuple[str, str]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    cert_dir = Path(cert_dir)
    cert_path = cert_dir / 'cert.pem'
    key_path = cert_dir / 'key.pem'

    if not force and cert_path.is_file() and key_path.is_file():
        return str(cert_path), str(key_path)

    cert_dir.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, 'BR'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Sao Geraldo Local Dev'),
        x509.NameAttribute(NameOID.COMMON_NAME, 'localhost'),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    san = x509.SubjectAlternativeName([
        x509.DNSName('localhost'),
        x509.IPAddress(ipaddress.IPv4Address('127.0.0.1')),
        x509.IPAddress(ipaddress.IPv6Address('::1')),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(san, critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(cert_path), str(key_path)


def public_cert_pem_path(cert_dir: str | os.PathLike = 'certs') -> Path:
    """Caminho do certificado público (nunca a chave privada)."""
    return Path(cert_dir) / 'cert.pem'


def load_public_cert_der(cert_dir: str | os.PathLike = 'certs') -> bytes:
    """Lê cert.pem e devolve DER (.cer) — só a parte pública."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    pem_path = public_cert_pem_path(cert_dir)
    if not pem_path.is_file():
        generate_self_signed_certs(cert_dir)
    pem_bytes = pem_path.read_bytes()
    # Recusar se alguém misturou chave no mesmo arquivo (defesa em profundidade)
    if b'PRIVATE KEY' in pem_bytes:
        raise ValueError('Arquivo de certificado contém chave privada; abortando.')
    cert = x509.load_pem_x509_certificate(pem_bytes)
    return cert.public_bytes(serialization.Encoding.DER)


def trust_cert_windows(cert_path: str | os.PathLike) -> None:
    """Importa cert.pem no Current User Trusted Root (Chrome/Edge)."""
    if sys.platform != 'win32':
        raise RuntimeError('--trust só é suportado no Windows neste projeto')

    cert_path = Path(cert_path).resolve()
    if not cert_path.is_file():
        raise FileNotFoundError(cert_path)

    script = Path(__file__).resolve().parent / 'trust_local_cert.ps1'
    if script.is_file():
        subprocess.run(
            [
                'powershell',
                '-NoProfile',
                '-ExecutionPolicy',
                'Bypass',
                '-File',
                str(script),
                '-CertPath',
                str(cert_path),
            ],
            check=True,
        )
        return

    # Fallback inline se o .ps1 não existir
    ps = f"""
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2('{cert_path}')
$store = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root','CurrentUser')
$store.Open('ReadWrite')
try {{
  if (-not ($store.Certificates | Where-Object {{ $_.Thumbprint -eq $cert.Thumbprint }})) {{
    $store.Add($cert)
  }}
}} finally {{ $store.Close() }}
Write-Host "Trusted: $($cert.Thumbprint)"
"""
    subprocess.run(['powershell', '-NoProfile', '-Command', ps], check=True)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Gera certs TLS locais (self-signed).')
    parser.add_argument('--force', action='store_true', help='Sobrescreve certs existentes')
    parser.add_argument('--dir', default='certs', help='Diretório de saída (padrão: certs)')
    parser.add_argument(
        '--trust',
        action='store_true',
        help='Windows: importa cert no Current User Trusted Root (remove aviso do navegador)',
    )
    args = parser.parse_args()
    cert, key = generate_self_signed_certs(args.dir, force=args.force)
    print(f'Certificado: {cert}')
    print(f'Chave:       {key}')
    if args.trust:
        trust_cert_windows(cert)
        print('Reinicie Chrome/Edge e abra https://127.0.0.1/')
