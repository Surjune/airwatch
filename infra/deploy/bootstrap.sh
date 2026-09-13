#!/usr/bin/env bash
# First-time setup of an AirWatch server (Ubuntu 22.04 or 24.04).
#
#   curl -fsSL https://raw.githubusercontent.com/Surjune/airwatch/main/infra/deploy/bootstrap.sh -o bootstrap.sh
#   less bootstrap.sh        # read it before running it
#   bash bootstrap.sh
#
# Safe to re-run: every step checks whether it is already done.
set -euo pipefail

REPO_URL="https://github.com/Surjune/airwatch.git"
APP_DIR="${APP_DIR:-$HOME/airwatch}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

say "Installing Docker (skipped if present)"
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl gnupg git
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
  sudo usermod -aG docker "$USER"
fi

say "Adding 2 GB of swap (skipped if present), so builds cannot run out of memory"
if ! swapon --show | grep -q '/swapfile'; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

say "Enabling automatic security updates"
sudo apt-get install -y unattended-upgrades >/dev/null
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

say "Fetching the code into $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
mkdir -p secrets backups
chmod 700 secrets

if [ ! -f .env ]; then
  cp .env.production.example .env
  chmod 600 .env
  cat <<'EOF'

.env was created from .env.production.example. Before starting:
  1. Edit it:            nano ~/airwatch/.env
     Generate secrets:   openssl rand -hex 24   (POSTGRES_PASSWORD)
                         openssl rand -hex 32   (OPERATOR_API_KEY)
  2. Copy the Earth Engine key (optional), from your own computer:
                         scp gee-key.json ubuntu@<server>:~/airwatch/secrets/gee-key.json
  3. Point your domain's A record at this server's public IP.
  4. Log out and back in (so Docker works without sudo), then run:
                         bash ~/airwatch/infra/deploy/deploy.sh
EOF
  exit 0
fi

say "Configuration found; deploying"
exec bash infra/deploy/deploy.sh
