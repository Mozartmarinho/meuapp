#!/bin/bash
# One-shot: install runner as systemd service (needs sudo once)
set -e
cd /home/administrador/actions-runner
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
