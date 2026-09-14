#!/usr/bin/env bash
# Sobe o MeuApp em segundo plano no Linux (sem git pull, sem abrir navegador).
# Equivalente ao scripts/iniciar_autostart.ps1 do Windows.
# Produção: Nginx na porta 80 → Gunicorn (não usa python app.py).

set -euo pipefail

APP_DIR="${APP_DIR:-}"
if [[ -z "${APP_DIR}" ]]; then
  APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
fi
LOG_DIR="${APP_DIR}/logs"
SYSTEMCTL="/bin/systemctl"
mkdir -p "${LOG_DIR}"

exec >> "${LOG_DIR}/autostart.log" 2>&1
echo "===== autostart $(date -Is) ====="
echo "Pasta: ${APP_DIR}"

if [[ ! -f "${APP_DIR}/app.py" ]] || [[ ! -f "${APP_DIR}/wsgi.py" ]]; then
  echo "ERRO: pasta do meuapp inválida (${APP_DIR})"
  exit 1
fi

cd "${APP_DIR}"

if sudo -n "${SYSTEMCTL}" start meuapp 2>/dev/null; then
  sleep 2
  if sudo -n "${SYSTEMCTL}" is-active --quiet meuapp 2>/dev/null; then
    echo "meuapp.service ativo via systemd"
    curl -s -o /dev/null -w "health:%{http_code}\n" --max-time 10 http://127.0.0.1/login || true
    echo "===== autostart fim $(date -Is) ====="
    exit 0
  fi
fi

echo "systemd indisponível; usando scripts/start_on_boot.sh"
exec /bin/bash "${APP_DIR}/scripts/start_on_boot.sh"
