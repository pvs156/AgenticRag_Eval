#!/usr/bin/env bash
# One-time VM setup (Ubuntu 22.04/24.04). Run as a sudo-capable user:
#   curl -fsSL https://raw.githubusercontent.com/<owner>/dispute-assistant/main/deploy/scripts/bootstrap-vm.sh | bash
set -euo pipefail

sudo apt-get update -y
sudo apt-get install -y ca-certificates curl git ufw unattended-upgrades fail2ban

# Docker Engine + compose plugin (official convenience script)
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi

# Firewall: SSH, HTTP, HTTPS only. Everything else (Grafana, Prometheus, Qdrant, API) stays internal.
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# Key-only SSH
sudo sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl reload ssh || sudo systemctl reload sshd

# Automatic security updates
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

# Small VMs: add 2 GB swap so model loading never OOMs
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

echo "done. Log out and back in (docker group), then follow deploy/README.md"
