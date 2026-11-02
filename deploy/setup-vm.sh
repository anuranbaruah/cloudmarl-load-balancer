#!/usr/bin/env bash
# Deploys the whole CloudMARL stack on a fresh Ubuntu 22.04 / 24.04 cloud VM
# (Azure, AWS EC2, Google Cloud...). Run on the VM over SSH:
#
#   curl -fsSL https://raw.githubusercontent.com/anuranbaruah/cloudmarl-load-balancer/main/deploy/setup-vm.sh | bash
#
# Safe to run again: it updates the code and restarts the stack.
set -euo pipefail

# 2 GB swap so small VMs (1-2 GB RAM) can hold Postgres + Grafana + 10 Python services
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

command -v docker >/dev/null || curl -fsSL https://get.docker.com | sudo sh

[ -d cloudmarl-load-balancer ] || git clone https://github.com/anuranbaruah/cloudmarl-load-balancer.git
cd cloudmarl-load-balancer
git pull --ff-only

if [ ! -f .env ]; then
  cp .env.example .env
  echo "GRAFANA_ADMIN_PASSWORD=$(openssl rand -hex 12)" >> .env
fi

sudo docker compose up -d --build

IP=$(curl -fsS https://api.ipify.org || hostname -I | awk '{print $1}')
echo
echo "CloudMARL is running."
echo "  Public dashboard : http://$IP:3000   (open inbound TCP port 3000 in the VM's firewall)"
echo "  Grafana admin    : admin / $(grep GRAFANA_ADMIN_PASSWORD .env | cut -d= -f2)"
echo "  Agent logs       : sudo docker compose logs -f lb-mumbai"
