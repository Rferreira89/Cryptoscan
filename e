#!/usr/bin/env bash
# Instala o "runner" do GitHub num servidor na Europa, para o Cryptoscan
# chegar aos dados que os servidores americanos do GitHub nao alcancam
# (derivados da Binance e da Bybit, leitura da conta Bybit UE).
#
# Uso (como root, num Ubuntu 24.04 novo):
#   bash instalar.sh <TOKEN_DO_GITHUB>
# O token vem de: repositorio > Settings > Actions > Runners >
# New self-hosted runner (vale 1 hora).
set -euo pipefail
TOKEN="${1:?falta o token do GitHub}"
REPO="https://github.com/Rferreira89/Cryptoscan"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q && apt-get install -yq curl git python3 python3-venv jq unattended-upgrades
# atualizacoes de seguranca automaticas e firewall so com SSH
dpkg-reconfigure -f noninteractive unattended-upgrades || true
if command -v ufw >/dev/null; then ufw allow OpenSSH && yes | ufw enable || true; fi
id runner >/dev/null 2>&1 || useradd -m -s /bin/bash runner
VER=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | jq -r .tag_name | sed 's/^v//')
cd /home/runner
sudo -u runner mkdir -p actions-runner
cd actions-runner
sudo -u runner curl -sL -o runner.tgz "https://github.com/actions/runner/releases/download/v${VER}/actions-runner-linux-x64-${VER}.tar.gz"
sudo -u runner tar xzf runner.tgz && rm -f runner.tgz
./bin/installdependencies.sh
sudo -u runner ./config.sh --url "$REPO" --token "$TOKEN" --labels eu --name cryptoscan-eu --unattended --replace
./svc.sh install runner
./svc.sh start
echo "Runner instalado e a correr."
