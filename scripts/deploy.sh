#!/usr/bin/env bash
# Deploy de produção do MeuApp (GitHub Actions self-hosted).
# Porta de produção: HTTP 80 via Nginx → unix socket Gunicorn.

set -euo pipefail

APP_DIR="${APP_DIR:-/home/administrador/meuapp}"
BRANCH="${DEPLOY_BRANCH:-main}"
REMOTE="${DEPLOY_REMOTE:-origin}"
VENV_DIR="${APP_DIR}/venv"
LOG_DIR="${APP_DIR}/logs/deploy"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/deploy_${TIMESTAMP}.log"
LOCK_FILE="${APP_DIR}/logs/deploy/.deploy.lock"
SYSTEMCTL="/bin/systemctl"
NGINX="/usr/sbin/nginx"

mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
fail() { log "ERRO: $*"; log "Deploy FALHOU. Log: ${LOG_FILE}"; exit 1; }
cleanup() { rm -f "${LOCK_FILE}" 2>/dev/null || true; }
trap cleanup EXIT

if command -v flock >/dev/null 2>&1; then
  exec 9>"${LOCK_FILE}"
  flock -n 9 || fail "Outro deploy já está em andamento"
else
  [[ -f "${LOCK_FILE}" ]] && fail "Outro deploy já está em andamento (${LOCK_FILE})"
  echo $$ > "${LOCK_FILE}"
fi

cd "${APP_DIR}" || fail "Diretório ${APP_DIR} não encontrado"

log "========== INÍCIO DO DEPLOY =========="
log "Diretório: ${APP_DIR}"
log "Branch: ${BRANCH}"
log "Commit atual: $(git rev-parse --short HEAD 2>/dev/null || echo 'n/a')"
log "Log: ${LOG_FILE}"

if [[ ! -f "${APP_DIR}/.ci_deploy_enabled" ]]; then
  fail "Deploy bloqueado: crie ${APP_DIR}/.ci_deploy_enabled para habilitar (veja CICD.md)"
fi

log ">>> 1/5 Atualizando código (${REMOTE}/${BRANCH})"
git fetch --prune "${REMOTE}" "${BRANCH}" || fail "git fetch falhou"
BEFORE="$(git rev-parse HEAD)"
git update-ref "refs/heads/${BRANCH}" "${REMOTE}/${BRANCH}" 2>/dev/null || true
git checkout -f "${BRANCH}" 2>/dev/null || git checkout -B "${BRANCH}" "${REMOTE}/${BRANCH}" || fail "git checkout ${BRANCH} falhou"
git reset --hard "${REMOTE}/${BRANCH}" || fail "git reset --hard falhou"
AFTER="$(git rev-parse HEAD)"
log "Antes:  ${BEFORE}"
log "Depois: ${AFTER}"
if [[ "${BEFORE}" == "${AFTER}" ]]; then
  log "Nenhuma alteração de código (mesmo commit)."
else
  log "Commits aplicados:"
  git log --oneline "${BEFORE}..${AFTER}" || true
fi

log ">>> 2/5 Instalando/atualizando dependências Python"
[[ -x "${VENV_DIR}/bin/python" ]] || fail "venv não encontrado em ${VENV_DIR}"
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
log "Dependências OK"

log ">>> 3/5 Executando migrações de banco"
python scripts/run_migrations.py || fail "Migrações falharam"

log ">>> 4/5 Reiniciando serviços"
restart_gunicorn_manual() {
  log "Reiniciando Gunicorn manualmente"
  pkill -f 'gunicorn.*meuapp.sock' 2>/dev/null || true
  sleep 1
  rm -f "${APP_DIR}/meuapp.sock"
  nohup "${VENV_DIR}/bin/python" -m gunicorn \
    --workers 3 \
    --bind "unix:${APP_DIR}/meuapp.sock" \
    -m 777 \
    --chdir "${APP_DIR}" \
    wsgi:application \
    >> "${APP_DIR}/logs/gunicorn.manual.log" 2>&1 &
  sleep 3
  [[ -S "${APP_DIR}/meuapp.sock" ]] || fail "Socket não criado após restart manual"
}

if sudo -n "${SYSTEMCTL}" restart meuapp 2>/dev/null; then
  sleep 2
  if sudo -n "${SYSTEMCTL}" is-active --quiet meuapp 2>/dev/null; then
    log "meuapp.service reiniciado via systemd"
  else
    log "AVISO: meuapp.service não ficou active; fallback Gunicorn"
    restart_gunicorn_manual
  fi
else
  log "AVISO: sudo/systemctl indisponível; fallback Gunicorn"
  restart_gunicorn_manual
fi

if sudo -n "${NGINX}" -t 2>/dev/null; then
  sudo -n "${SYSTEMCTL}" reload nginx 2>/dev/null || log "AVISO: reload nginx falhou"
else
  log "AVISO: nginx -t via sudo indisponível"
fi

log ">>> 5/5 Verificação pós-deploy (porta 80)"
[[ -S "${APP_DIR}/meuapp.sock" ]] || fail "Socket meuapp.sock ausente"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1/login}"
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "${HEALTH_URL}" || true)"
if [[ "${HTTP_CODE}" =~ ^(200|302|301|303|307|308)$ ]]; then
  log "Health-check OK: ${HEALTH_URL} → HTTP ${HTTP_CODE}"
else
  fail "Health-check falhou em ${HEALTH_URL} (HTTP ${HTTP_CODE:-sem resposta})"
fi

ls -1t "${LOG_DIR}"/deploy_*.log 2>/dev/null | tail -n +31 | xargs -r rm -f || true
ln -sfn "${LOG_FILE}" "${LOG_DIR}/latest.log"
log "========== DEPLOY CONCLUÍDO COM SUCESSO =========="
log "Commit em produção: $(git rev-parse --short HEAD)"
log "Acesso: http://192.168.0.253/ (Nginx :80)"
log "Log completo: ${LOG_FILE}"
exit 0
