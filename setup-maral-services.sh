#!/usr/bin/env bash
# Run ON MARAL (maral.local) once. Installs Homebrew + Colima/Docker + Caddy.
# Idempotent. Safe to re-run.

set -euo pipefail

echo "=== 1/5 Homebrew ==="
if ! command -v brew >/dev/null 2>&1; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Add brew to PATH for this session
  eval "$(/opt/homebrew/bin/brew shellenv)"
  echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
fi
echo "brew $(brew --version | head -1)"

echo "=== 2/5 Colima + Docker CLI ==="
brew install colima docker docker-compose
# Start Colima with 4 CPU, 6 GB RAM, 60 GB disk (leaves headroom for Ollama)
colima start --cpu 4 --memory 6 --disk 60 --vm-type=vz --vz-rosetta 2>&1 | tail -5 || colima status

echo "=== 3/5 Caddy with Porkbun DNS plugin ==="
# Standalone caddy with porkbun plugin baked in (caddyserver.com download API)
mkdir -p ~/bin
if [ ! -x ~/bin/caddy ]; then
  curl -fsSL -o /tmp/caddy.tar.gz \
    "https://caddyserver.com/api/download?os=darwin&arch=arm64&p=github.com%2Fcaddy-dns%2Fporkbun&idempotency=$(date +%s)"
  # The download API returns a binary, not a tarball; rename
  mv /tmp/caddy.tar.gz ~/bin/caddy
  chmod +x ~/bin/caddy
fi
~/bin/caddy version
grep -q '$HOME/bin' ~/.zprofile 2>/dev/null || echo 'export PATH=$HOME/bin:$PATH' >> ~/.zprofile

echo "=== 4/5 Directories ==="
mkdir -p ~/caddy ~/langfuse
echo "configs will live in ~/caddy and ~/langfuse"

echo "=== 5/5 Done ==="
echo
echo "Verify:"
echo "  brew --version"
echo "  docker version --format '{{.Server.Version}}'"
echo "  ~/bin/caddy version"
echo
echo "Next steps will be driven remotely. Tell John 'maral setup done'."
