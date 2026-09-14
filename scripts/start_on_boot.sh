#!/usr/bin/env bash
# Fallback de boot: garante MeuApp + runner se o systemd não subir sozinho.
# Crontab: @reboot /bin/bash /home/administrador/meuapp/scripts/start_on_boot.sh

set -euo pipefail
APP_DIR="/home/administrador/meuapp"
RUNNER_DIR="/home/administrador/actions-runner"
LOG_DIR="${APP_DIR}/logs"
SYSTEMCTL="/bin/systemctl"
mkdir -p "${LOG_DIR}"

exec >> "${LOG_DIR}/boot.log" 2>&1
echo "===== boot $(date -Is) ====="

# Esperar rede/MySQL
sleep 20

# Preferir systemd (serviço enabled no boot)
if sudo -n "${SYSTEMCTL}" start meuapp 2>/dev/null; then
  sleep 2
  if sudo -n "${SYSTEMCTL}" is-active --quiet meuapp 2>/dev/null; then
    echo "meuapp.service ativo via systemctl"
  else
    echo "AVISO: systemctl start não deixou active"
  fi
fi

# Fallback: Gunicorn manual se não houver processo
if ! pgrep -f "gunicorn.*${APP_DIR}/meuapp.sock" >/dev/null 2>&1; then
  echo "Fallback: iniciando Gunicorn manual"
  rm -f "${APP_DIR}/meuapp.sock"
  cd "${APP_DIR}"
  nohup "${APP_DIR}/venv/bin/python" -m gunicorn \
    --workers 3 \
    --bind "unix:${APP_DIR}/meuapp.sock" \
    -m 007 \
    --chdir "${APP_DIR}" \
    wsgi:application \
    >> "${LOG_DIR}/gunicorn.manual.log" 2>&1 &
  echo "gunicorn pid $!"
else
  echo "gunicorn já rodando"
fi

# Nginx (se sudoers permitir)
sudo -n "${SYSTEMCTL}" start nginx 2>/dev/null || true

# GitHub Actions runner (CI/CD)
if [[ -x "${RUNNER_DIR}/run.sh" ]]; then
  if ! pgrep -f 'Runner.Listener' >/dev/null 2>&1; then
    cd "${RUNNER_DIR}"
    nohup ./run.sh >> "${RUNNER_DIR}/runner.log" 2>&1 &
    echo "runner pid $!"
  else
    echo "runner já rodando"
  fi
fi

sleep 3
if [[ -S "${APP_DIR}/meuapp.sock" ]]; then
  echo "socket OK"
else
  echo "AVISO: socket ausente"
fi
curl -s -o /dev/null -w "health:%{http_code}\n" --max-time 10 http://127.0.0.1/login || true
echo "===== boot fim $(date -Is) ====="
