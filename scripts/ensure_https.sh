#!/usr/bin/env bash
# Corrige HTTPS em sistemas.saogeraldoservice.com (Let's Encrypt + Nginx TLS 1.2/1.3).
# O celular força HTTPS; a porta 443 pública estava com handshake TLS quebrado
# (ERR_SSL_PROTOCOL_ERROR). HTTP:80 (Nginx) já funcionava no desktop.
set -u

DOMAIN="${HTTPS_DOMAIN:-sistemas.saogeraldoservice.com}"
EMAIL="${HTTPS_EMAIL:-informatica@saogeraldoservice.com.br}"
APP_DIR="${APP_DIR:-/home/administrador/meuapp}"
SOCK="${APP_DIR}/meuapp.sock"
SITE_SRC="${APP_DIR}/deploy/nginx-sistemas.conf"
SITE_DST="/etc/nginx/sites-available/meuapp-sistemas"
WEBROOT="/var/www/letsencrypt"
LIVE="/etc/letsencrypt/live/${DOMAIN}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [https] $*"; }
SUDO=""
if sudo -n true 2>/dev/null || sudo -n /usr/sbin/nginx -t >/dev/null 2>&1 || sudo -n /bin/systemctl is-active nginx >/dev/null 2>&1; then
  SUDO="sudo -n"
else
  log "AVISO: sudo sem senha indisponível. No servidor, rode: sudo bash ${APP_DIR}/scripts/ensure_https.sh"
fi

run() {
  if [[ -n "${SUDO}" ]]; then
    # shellcheck disable=SC2086
    ${SUDO} "$@"
  else
    "$@"
  fi
}

log "===== diagnóstico porta 80/443 ====="
(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null || true) | grep -E ':80 |:443 ' || true
log "Processos web:"
ps -eo pid,cmd | grep -Ei 'nginx|caddy|cloudflared|traefik|gunicorn' | grep -v grep || true

if [[ -z "${SUDO}" && "$(id -u)" -ne 0 ]]; then
  log "Não é possível instalar certificado sem root. Abortando (deploy segue)."
  exit 0
fi

# Libera 443 se outro serviço Go/Caddy estiver quebrando o TLS
stop_if_active() {
  local unit="$1"
  if systemctl is-active --quiet "${unit}" 2>/dev/null; then
    log "Parando ${unit} para o Nginx assumir a porta 443"
    run systemctl stop "${unit}" || true
    run systemctl disable "${unit}" || true
  fi
}
stop_if_active caddy
stop_if_active caddy2
# cloudflared às vezes é o túnel; só para se estiver escutando 443
if ss -tlnp 2>/dev/null | grep -q ':443 ' && ss -tlnp 2>/dev/null | grep -qi cloudflared; then
  log "cloudflared está em :443 — parando para o Nginx usar TLS"
  stop_if_active cloudflared
fi

run mkdir -p "${WEBROOT}/.well-known/acme-challenge"
run chown -R www-data:www-data "${WEBROOT}" 2>/dev/null || true

if ! command -v certbot >/dev/null 2>&1; then
  log "Instalando certbot"
  run apt-get update -y
  run DEBIAN_FRONTEND=noninteractive apt-get install -y certbot python3-certbot-nginx
fi

run systemctl start nginx || true

# Caminho rápido: o plugin nginx do certbot edita o vhost que já existe
if run certbot --nginx -d "${DOMAIN}" \
    --non-interactive --agree-tos --email "${EMAIL}" \
    --redirect --keep-until-expiring; then
  log "certbot --nginx concluiu"
  run systemctl reload nginx || true
  curl -skI --max-time 10 "https://127.0.0.1/" -H "Host: ${DOMAIN}" | head -n 8 || true
  log "HTTPS configurado para ${DOMAIN} (TLS 1.2/1.3)."
  exit 0
fi
log "certbot --nginx não aplicou; tentando webroot + site próprio"

# Garante um server_name no HTTP para o ACME (sem redirect ainda, senão o desafio quebra)
ACME_TMP="/etc/nginx/sites-available/meuapp-acme"
cat <<EOF | run tee "${ACME_TMP}" >/dev/null
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    location /.well-known/acme-challenge/ {
        root ${WEBROOT};
        allow all;
    }
    location / {
        proxy_pass http://unix:${SOCK};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        client_max_body_size 40m;
    }
}
EOF
run ln -sfn "${ACME_TMP}" /etc/nginx/sites-enabled/meuapp-acme
# Evita default_server SSL quebrado em sites-enabled
if [[ -L /etc/nginx/sites-enabled/default ]]; then
  log "Removendo site default do Nginx (evita TLS quebrado)"
  run rm -f /etc/nginx/sites-enabled/default
fi
if ! run nginx -t; then
  log "nginx -t falhou com o bloco ACME; não sigo com o certificado"
  exit 0
fi
run systemctl reload nginx || run systemctl restart nginx || true

log "Emitindo/renovando certificado Let's Encrypt para ${DOMAIN}"
if [[ -f "${LIVE}/fullchain.pem" ]]; then
  run certbot renew --quiet --deploy-hook "systemctl reload nginx" || \
    run certbot certonly --webroot -w "${WEBROOT}" -d "${DOMAIN}" \
      --non-interactive --agree-tos --email "${EMAIL}" --keep-until-expiring || true
else
  if ! run certbot certonly --webroot -w "${WEBROOT}" -d "${DOMAIN}" \
      --non-interactive --agree-tos --email "${EMAIL}" --keep-until-expiring; then
    log "Falha no certbot (HTTP-01). Conferir se ${DOMAIN} aponta para este servidor na porta 80."
    exit 0
  fi
fi

if [[ ! -f "${LIVE}/fullchain.pem" ]]; then
  log "Certificado não encontrado em ${LIVE}. HTTPS não ativado."
  exit 0
fi

log "Instalando site HTTPS do Nginx"
run cp "${SITE_SRC}" "${SITE_DST}"
run ln -sfn "${SITE_DST}" /etc/nginx/sites-enabled/meuapp-sistemas
# O bloco ACME duplicaria listen 80; remove depois que o site completo existe
run rm -f /etc/nginx/sites-enabled/meuapp-acme

if ! run nginx -t; then
  log "nginx -t falhou com o site HTTPS. Mantendo HTTP."
  run rm -f /etc/nginx/sites-enabled/meuapp-sistemas
  run ln -sfn "${ACME_TMP}" /etc/nginx/sites-enabled/meuapp-acme
  run nginx -t && run systemctl reload nginx || true
  exit 0
fi

run systemctl reload nginx || run systemctl restart nginx

log "Teste local HTTPS"
curl -skI --max-time 10 "https://127.0.0.1/" -H "Host: ${DOMAIN}" | head -n 8 || true
log "HTTPS configurado para ${DOMAIN} (TLS 1.2/1.3)."
exit 0
