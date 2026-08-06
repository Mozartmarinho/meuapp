#!/usr/bin/env bash
# Deploy de produção do MeuApp (chamado pelo GitHub Actions self-hosted).
# - atualiza código (git)
# - instala dependências Python se necessário
# - executa migrações pendentes
# - reinicia meuapp e recarrega nginx
# - grava log completo em logs/deploy/

set -euo pipefail

APP_DIR="${APP_DIR:-/home/administrador/meuapp}"
BRANCH="${DEPLOY_BRANCH:-main}"
REMOTE="${DEPLOY_REMOTE:-origin}"
VENV_DIR="${APP_DIR}/venv"
LOG_DIR="${APP_DIR}/logs/deploy"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/deploy_${TIMESTAMP}.log"
LOCK_FILE="${APP_DIR}/logs/deploy/.deploy.lock"

mkdir -p "${LOG_DIR}"

exec > >(tee -a "${LOG_FILE}") 2>&1

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

fail() {
  log "ERRO: $*"
  log "Deploy FALHOU. Log: ${LOG_FILE}"
  exit 1
}

cleanup() {
  rm -f "${LOCK_FILE}" 2>/dev/null || true
}
trap cleanup EXIT

# Evita deploys paralelos
if command -v flock >/dev/null 2>&1; then
  exec 9>"${LOCK_FILE}"
  flock -n 9 || fail "Outro deploy já está em andamento"
else
  if [[ -f "${LOCK_FILE}" ]]; then
    fail "Outro deploy já está em andamento (${LOCK_FILE})"
  fi
  echo $$ > "${LOCK_FILE}"
fi

cd "${APP_DIR}" || fail "Diretório ${APP_DIR} não encontrado"

log "========== INÍCIO DO DEPLOY =========="
log "Diretório: ${APP_DIR}"
log "Branch: ${BRANCH}"
log "Commit atual: $(git rev-parse --short HEAD 2>/dev/null || echo 'n/a')"
log "Log: ${LOG_FILE}"

# Trava de segurança: só faz git reset quando o arquivo existir no servidor.
# Ative com:  touch /home/administrador/meuapp/.ci_deploy_enabled
if [[ ! -f "${APP_DIR}/.ci_deploy_enabled" ]]; then
  fail "Deploy bloqueado: crie ${APP_DIR}/.ci_deploy_enabled para habilitar (veja CICD.md)"
fi

# --- 1. Atualizar código ---
log ">>> 1/5 Atualizando código (${REMOTE}/${BRANCH})"
git fetch --prune "${REMOTE}" "${BRANCH}" || fail "git fetch falhou"
BEFORE="$(git rev-parse HEAD)"
git checkout "${BRANCH}" || fail "git checkout ${BRANCH} falhou"
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

# --- 2. Dependências ---
log ">>> 2/5 Instalando/atualizando dependências Python"
if [[ ! -x "${VENV_DIR}/bin/pip" ]]; then
  fail "venv não encontrado em ${VENV_DIR}. Crie com: python3 -m venv venv"
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt
log "Dependências OK"

# --- 3. Migrações ---
log ">>> 3/5 Executando migrações de banco"
python scripts/run_migrations.py || fail "Migrações falharam"

# --- 4. Reiniciar aplicação e Nginx ---
log ">>> 4/5 Reiniciando serviços"
if ! command -v sudo >/dev/null 2>&1; then
  fail "sudo não disponível"
fi

sudo systemctl restart meuapp || fail "Falha ao reiniciar meuapp"
sleep 2
sudo systemctl is-active --quiet meuapp || fail "meuapp não está active após restart"

sudo nginx -t || fail "nginx -t falhou (config inválida)"
sudo systemctl reload nginx || fail "Falha ao recarregar nginx"
sudo systemctl is-active --quiet nginx || fail "nginx não está active"

log "Status meuapp:"
sudo systemctl status meuapp --no-pager -l | head -20 || true
log "Status nginx:"
sudo systemctl status nginx --no-pager -l | head -15 || true

# --- 5. Verificação rápida (produção = HTTP porta 80 via Nginx) ---
log ">>> 5/5 Verificação pós-deploy (porta 80)"
if [[ -S "${APP_DIR}/meuapp.sock" ]]; then
  log "Socket OK: ${APP_DIR}/meuapp.sock"
else
  log "AVISO: socket meuapp.sock não encontrado (verifique gunicorn)"
fi

HEALTH_URL="${HEALTH_URL:-http://127.0.0.1/login}"
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "${HEALTH_URL}" || true)"
if [[ "${HTTP_CODE}" =~ ^(200|302|301|303|307|308)$ ]]; then
  log "Health-check OK: ${HEALTH_URL} → HTTP ${HTTP_CODE}"
else
  fail "Health-check falhou em ${HEALTH_URL} (HTTP ${HTTP_CODE:-sem resposta}). App pode estar fora na porta 80."
fi

# Mantém só os últimos 30 logs de deploy
ls -1t "${LOG_DIR}"/deploy_*.log 2>/dev/null | tail -n +31 | xargs -r rm -f || true

# Symlink para o último deploy
ln -sfn "${LOG_FILE}" "${LOG_DIR}/latest.log"

log "========== DEPLOY CONCLUÍDO COM SUCESSO =========="
log "Commit em produção: $(git rev-parse --short HEAD)"
log "Acesso: http://192.168.0.253/ (Nginx :80 → Gunicorn socket)"
log "Log completo: ${LOG_FILE}"
exit 0
