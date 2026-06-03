#!/usr/bin/env bash
# setup-newbox.sh — bootstrap the new Mac Studio M3 Ultra 96GB as the primary
# local-LLM server, replacing Maral (M2 16GB) as the default backend.
#
# RUN ON THE NEW MAC STUDIO once, after initial macOS setup + on the LAN.
# Idempotent. Safe to re-run.
#
# Prereqs you do by hand first:
#   1. Complete macOS setup, sign in, connect to LAN.
#   2. STRONGLY recommended: plug in a USB-C -> Gigabit Ethernet adapter and use
#      wired, NOT WiFi. (Maral's WiFi driver crashed 3x under LLM memory/network
#      pressure — Act 15. Wired eliminates that entire failure class.)
#   3. Enable Remote Login (System Settings > General > Sharing > Remote Login)
#      so you can SSH in headless.
#   4. Note this box's hostname:  scutil --get LocalHostName   (use <name>.local)
#
# After this script: pull/copy models, then point ~/.zshrc LOCAL_LLM_HOST at
# <name>.local:11434 on your laptop.

set -euo pipefail

BIN="$HOME/bin"
LA="$HOME/Library/LaunchAgents"
mkdir -p "$BIN" "$LA"

echo "=== 1/4 Install Ollama (binary, no installer) ==="
if [[ ! -x "$BIN/ollama" ]]; then
  cd /tmp
  curl -fL -o Ollama-darwin.zip https://ollama.com/download/Ollama-darwin.zip
  unzip -qo Ollama-darwin.zip -d ollama-extract
  cp ollama-extract/Ollama.app/Contents/Resources/ollama "$BIN/ollama"
  chmod +x "$BIN/ollama"
fi
grep -q 'export PATH=$HOME/bin' "$HOME/.zshrc" 2>/dev/null || \
  echo 'export PATH=$HOME/bin:$PATH' >> "$HOME/.zshrc"
"$BIN/ollama" --version

echo "=== 2/4 Ollama launchd agent (LAN-bound, tuned) ==="
# 96GB headroom: bump loaded models + context vs the Maral config. KV q8 +
# flash-attn keep cache small; 32k context comfortably fits.
cat > "$LA/com.ollama.serve.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ollama.serve</string>
  <key>ProgramArguments</key>
  <array><string>$BIN/ollama</string><string>serve</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key><string>0.0.0.0:11434</string>
    <key>OLLAMA_MAX_LOADED_MODELS</key><string>1</string>
    <key>OLLAMA_NUM_PARALLEL</key><string>1</string>
    <key>OLLAMA_KEEP_ALIVE</key><string>15m</string>
    <key>OLLAMA_FLASH_ATTENTION</key><string>1</string>
    <key>OLLAMA_KV_CACHE_TYPE</key><string>q8_0</string>
    <key>OLLAMA_CONTEXT_LENGTH</key><string>32768</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/ollama.log</string>
  <key>StandardErrorPath</key><string>$HOME/ollama.err</string>
</dict>
</plist>
PLIST
launchctl unload "$LA/com.ollama.serve.plist" 2>/dev/null || true
launchctl load -w "$LA/com.ollama.serve.plist"
sleep 4
curl -sf http://localhost:11434/api/version && echo "  ollama up"

echo "=== 3/4 caffeinate keep-awake (headless never sleeps) ==="
cat > "$LA/com.user.caffeinate.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.user.caffeinate</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/caffeinate</string><string>-dimsu</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
PLIST
launchctl unload "$LA/com.user.caffeinate.plist" 2>/dev/null || true
launchctl load -w "$LA/com.user.caffeinate.plist"

echo "=== 4/4 Models ==="
echo "Option A (fast, if Maral pre-staged them) — LAN copy from Maral:"
echo "  rsync -aP youruser@maral.local:~/.ollama/models/ ~/.ollama/models/"
echo "Option B — pull fresh from internet:"
echo "  $BIN/ollama pull qwen3:32b              # ~20GB, largest dense, ~76% SWE-bench"
echo "  $BIN/ollama pull qwen3-coder:30b-a3b-q8_0  # ~32GB, coder MoE, ~77%, fast"
echo "  $BIN/ollama pull qwen3:8b               # small/fast routing"
echo
echo "=== DONE. Next: on your LAPTOP, edit ~/.zshrc local-llm router block ==="
echo "  LOCAL_LLM_HOST=\"$(scutil --get LocalHostName 2>/dev/null || echo NEWBOX).local:11434\""
echo "  LOCAL_LLM_MODEL=\"qwen3-coder:30b-a3b-q8_0\"   # or qwen3:32b"
echo "  (keep think:false / ENABLE_TOOL_SEARCH=auto:5 / 120s timeout)"
echo "Then: re-run benchmarks/minibench/harness.py local  vs the 12/12 baseline."
