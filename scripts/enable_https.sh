#!/usr/bin/env bash
# Liga HTTPS do MeuApp na porta 443 (Caddy) sem tirar o HTTP da porta 80 (Nginx).
# Rode com senha de admin:
#   sudo bash /home/administrador/meuapp/scripts/enable_https.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CADDYFILE_SRC="${APP_DIR}/deploy/Caddyfile"
CADDYFILE_DST="/opt/caddy/Caddyfile"
CERT_FULLCHAIN="${APP_DIR}/certs/fullchain.pem"
CERT_KEY="${APP_DIR}/certs/key.pem"
PYTHON="${APP_DIR}/venv/bin/python"
LAN_IP="${MEUAPP_LAN_IP:-192.168.0.253}"
CADDY_FALLBACK_ID="052004f1aa635f59173ee4dee74d850902614128c4210325455b781770922c37"

log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { echo "ERRO: $*" >&2; exit 1; }

if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3 || true)"
fi
[[ -x "${PYTHON}" ]] || die "Python não encontrado (venv/bin/python)"
[[ -f "${CADDYFILE_SRC}" ]] || die "Falta ${CADDYFILE_SRC}"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Este script precisa de root para gravar o Caddyfile e recarregar o HTTPS na porta 443."
  echo "Rode: sudo bash $0"
  exit 1
fi

log "Gerando CA + certificado de servidor (SAN com IP da LAN)"
"${PYTHON}" "${APP_DIR}/generate_certs.py"
[[ -f "${CERT_FULLCHAIN}" && -f "${CERT_KEY}" ]] || die "Certificados não foram gerados em ${APP_DIR}/certs"

TRUST_USER="${SUDO_USER:-administrador}"
if [[ -n "${TRUST_USER}" && "${TRUST_USER}" != "root" ]]; then
  log "Importando CA no Chrome do usuário ${TRUST_USER}"
  sudo -u "${TRUST_USER}" "${PYTHON}" "${APP_DIR}/generate_certs.py" --trust || true
fi

find_caddy_container() {
  local cid=""
  if command -v docker >/dev/null 2>&1; then
    cid="$(docker ps --format '{{.ID}} {{.Names}} {{.Image}}' 2>/dev/null | awk '/caddy/{print $1; exit}')"
  fi
  if [[ -z "${cid}" ]]; then
    cid="${CADDY_FALLBACK_ID}"
  fi
  echo "${cid}"
}

log "Atualizando Nginx (HTTP :80, preserva X-Forwarded-Proto do Caddy)"
cp /etc/nginx/sites-available/meuapp "/etc/nginx/sites-available/meuapp.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
cp "${APP_DIR}/deploy/nginx-meuapp.conf" /etc/nginx/sites-available/meuapp
if nginx -t; then
  /bin/systemctl reload nginx || log "AVISO: reload nginx falhou"
else
  die "nginx -t falhou; restaure o backup em /etc/nginx/sites-available/"
fi

log "Aplicando Caddyfile (HTTPS :443 do MeuApp + MinIO intacto)"
cp "${CADDYFILE_DST}" "${CADDYFILE_DST}.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
cp "${CADDYFILE_SRC}" "${CADDYFILE_DST}"

CID="$(find_caddy_container)"
log "Container Caddy: ${CID}"
docker cp "${CERT_FULLCHAIN}" "${CID}:/etc/caddy/meuapp-cert.pem"
docker cp "${CERT_KEY}" "${CID}:/etc/caddy/meuapp-key.pem"
docker exec "${CID}" chmod 644 /etc/caddy/meuapp-cert.pem || true
docker exec "${CID}" chmod 600 /etc/caddy/meuapp-key.pem || true
if ! docker exec "${CID}" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
  log "Reload via exec falhou; enviando USR1"
  docker kill -s USR1 "${CID}" || true
fi

log "Verificando HTTP e HTTPS"
sleep 1
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "http://${LAN_IP}/login" || true)"
HTTPS_CODE="$(curl -sk -o /dev/null -w '%{http_code}' --max-time 8 "https://${LAN_IP}/login" || true)"
log "HTTP  http://${LAN_IP}/login  → ${HTTP_CODE:-sem resposta}"
log "HTTPS https://${LAN_IP}/login → ${HTTPS_CODE:-sem resposta}"

if [[ ! "${HTTP_CODE}" =~ ^(200|302|301|303|307|308)$ ]]; then
  die "HTTP deixou de responder. Verifique o Nginx / Gunicorn."
fi
if [[ ! "${HTTPS_CODE}" =~ ^(200|302|301|303|307|308)$ ]]; then
  log "HTTPS ainda não respondeu. Tente: docker restart ${CID}"
  exit 2
fi

echo
echo "OK: HTTP e HTTPS no ar."
echo "  http://${LAN_IP}/"
echo "  https://${LAN_IP}/"
echo
echo "Para o Chrome parar de avisar neste PC:"
echo "  sudo apt-get install -y libnss3-tools"
echo "  sudo -u ${TRUST_USER} bash ${APP_DIR}/scripts/trust_local_cert.sh"
echo "  (feche o Chrome por completo e reabra https://${LAN_IP}/)"
echo "Nos PCs Windows da rede: http://${LAN_IP}/instalar-certificado"
echo
