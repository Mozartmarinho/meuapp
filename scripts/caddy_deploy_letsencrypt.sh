#!/bin/bash
# Copia o certificado Let's Encrypt renovado para o Caddy (Docker :443)
# e recarrega. Chamado pelo certbot em:
#   /etc/letsencrypt/renewal-hooks/deploy/
set -euo pipefail

DOMAIN="sistemas.saogeraldoservice.com"
CID="${CADDY_CONTAINER:-caddy}"
LIVE="${RENEWED_LINEAGE:-/etc/letsencrypt/live/${DOMAIN}}"

lineage_name="$(basename "${LIVE}")"
renewed_domains="${RENEWED_DOMAINS:-${lineage_name}}"
case " ${renewed_domains} " in
  *" ${DOMAIN} "*) ;;
  *)
    echo "[caddy-le] ignorando lineage ${lineage_name} (${renewed_domains})"
    exit 0
    ;;
esac

full="$(readlink -f "${LIVE}/fullchain.pem")"
key="$(readlink -f "${LIVE}/privkey.pem")"
[[ -f "${full}" && -f "${key}" ]] || {
  echo "[caddy-le] certificado não encontrado em ${LIVE}" >&2
  exit 1
}

echo "[caddy-le] copiando ${full} -> ${CID}:/data/sistemas-fullchain.pem"
docker cp "${full}" "${CID}:/data/sistemas-fullchain.pem"
docker cp "${key}" "${CID}:/data/sistemas-privkey.pem"
docker exec "${CID}" chmod 644 /data/sistemas-fullchain.pem
docker exec "${CID}" chmod 600 /data/sistemas-privkey.pem
docker exec "${CID}" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
echo "[caddy-le] Caddy recarregado com o certificado novo de ${DOMAIN}"
