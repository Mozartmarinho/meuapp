#!/usr/bin/env bash
# Confia na CA local do MeuApp (Chrome/Chromium via NSS).
# Uso:
#   bash scripts/trust_local_cert.sh
# Depois feche o navegador por completo e abra https://192.168.0.253/
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${APP_DIR}"

PYTHON="${APP_DIR}/venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3 || command -v python)"
fi

"${PYTHON}" "${APP_DIR}/generate_certs.py"
exec "${PYTHON}" "${APP_DIR}/generate_certs.py" --trust
