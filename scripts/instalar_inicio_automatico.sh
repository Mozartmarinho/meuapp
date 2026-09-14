#!/usr/bin/env bash
# Instala o MeuApp para iniciar no boot do Linux (systemd + fallback crontab).
# Equivalente ao instalar_inicio_automatico.bat do Windows.
# Produção: HTTP porta 80 via Nginx → Gunicorn. Não liga python app.py na 80.

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_SRC="${APP_DIR}/deploy/meuapp.service"
UNIT_DST="/etc/systemd/system/meuapp.service"
CRON_LINE="@reboot /bin/bash ${APP_DIR}/scripts/start_on_boot.sh"

echo
echo "=== MeuApp — início automático no Linux ==="
echo "Pasta: ${APP_DIR}"
echo

if [[ ! -f "${APP_DIR}/app.py" ]] || [[ ! -f "${APP_DIR}/wsgi.py" ]]; then
  echo "ERRO: execute este script de dentro do clone git do meuapp."
  exit 1
fi

chmod +x "${APP_DIR}/scripts/"*.sh "${APP_DIR}/scripts/run_migrations.py" 2>/dev/null || true

install_systemd() {
  if [[ ! -f "${UNIT_SRC}" ]]; then
    echo "AVISO: ${UNIT_SRC} não encontrado."
    return 1
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    echo "AVISO: sudo não encontrado; pulando systemd."
    return 1
  fi
  echo "Instalando unidade systemd..."
  sudo cp "${UNIT_SRC}" "${UNIT_DST}"
  sudo systemctl daemon-reload
  sudo systemctl enable meuapp
  sudo systemctl restart meuapp || sudo systemctl start meuapp
  sleep 2
  if sudo systemctl is-active --quiet meuapp; then
    echo "OK: meuapp.service ativo e habilitado no boot."
    return 0
  fi
  echo "AVISO: meuapp.service não ficou active."
  sudo systemctl status meuapp --no-pager -l || true
  return 1
}

install_cron_fallback() {
  if ! command -v crontab >/dev/null 2>&1; then
    echo "AVISO: crontab não disponível."
    return 1
  fi
  local current
  current="$(crontab -l 2>/dev/null || true)"
  if echo "${current}" | grep -F "${APP_DIR}/scripts/start_on_boot.sh" >/dev/null 2>&1; then
    echo "OK: crontab @reboot já estava configurado."
    return 0
  fi
  {
    echo "${current}"
    echo "${CRON_LINE}"
  } | grep -v '^$' | crontab -
  echo "OK: crontab @reboot instalado (${APP_DIR}/scripts/start_on_boot.sh)."
}

if install_systemd; then
  install_cron_fallback || true
else
  echo "systemd não ficou pronto; instalando só o fallback de boot."
  install_cron_fallback || true
  /bin/bash "${APP_DIR}/scripts/start_on_boot.sh" || true
fi

echo
echo "Acesso: http://127.0.0.1/  (Nginx porta 80)"
echo "Status: sudo systemctl status meuapp --no-pager"
echo "Desinstalar: sudo systemctl disable --now meuapp"
echo
