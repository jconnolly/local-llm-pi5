# Repurposing a spare MacBook as a local-LLM server

Pivoted from Pi 5 to a spare MacBook Air M2 16GB ("Maral") because:

- Apple Silicon = Metal GPU acceleration + unified memory bandwidth (~100 GB/s) vs Pi 5 LPDDR4X (~17 GB/s)
- M2 16GB runs **qwen3:14b** at **10.13 tok/s decode, 64 tok/s prefill** vs Pi 5 + qwen3:8b at 2 tok/s
- Hits ~65-70% SWE-bench Verified (vs Pi 5 + qwen3:8b at ~50%)
- $0 hardware cost — sitting idle anyway
- Eliminates the SD-card / USB-NVMe storage problem on the Pi
- Eliminates the need to buy a $999 Mac Mini M4 24GB BTO

Network: MacBook on 192.168.x.x, my Mac on 192.168.x.x, Google Wifi mesh bridges between them. mDNS still resolves cross-subnet.

## Install path (Ollama headless on macOS via SSH)

Apple Silicon, macOS Tahoe 26.5+, no Homebrew required.

```bash
# 1. Find the MacBook (mDNS)
dns-sd -B _rfb._tcp local. &    # Mac advertises Screen Sharing
# Note the instance name, then resolve:
dns-sd -G v4 <name>.local

# 2. SSH (key auth assumed; otherwise password)
ssh youruser@maral.local

# 3. Download Ollama macOS binary (no installer needed)
cd /tmp
curl -L -o Ollama-darwin.zip https://ollama.com/download/Ollama-darwin.zip
unzip -q Ollama-darwin.zip -d ollama-extract
mkdir -p ~/bin
cp ollama-extract/Ollama.app/Contents/Resources/ollama ~/bin/
chmod +x ~/bin/ollama
echo 'export PATH=$HOME/bin:$PATH' >> ~/.zshrc

# 4. Launchd plist — runs Ollama as a user agent, restarts on crash, binds to LAN
mkdir -p ~/Library/LaunchAgents
cat > ~/Library/LaunchAgents/com.ollama.serve.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ollama.serve</string>
  <key>ProgramArguments</key>
  <array>
    <string>$HOME/bin/ollama</string>
    <string>serve</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key><string>0.0.0.0:11434</string>
    <key>OLLAMA_MAX_LOADED_MODELS</key><string>1</string>
    <key>OLLAMA_NUM_PARALLEL</key><string>1</string>
    <key>OLLAMA_KEEP_ALIVE</key><string>10m</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/ollama.log</string>
  <key>StandardErrorPath</key><string>$HOME/ollama.err</string>
</dict>
</plist>
EOF
launchctl load ~/Library/LaunchAgents/com.ollama.serve.plist
sleep 3
curl -s http://localhost:11434/api/version   # {"version":"0.24.0"}

# 5. Pull models
ollama pull qwen3:14b   # ~9 GB, main model
ollama pull qwen3:8b    # ~5 GB, small/fast for SMALL_FAST_MODEL routing
```

## Keep-awake (headless)

MacBooks sleep when idle and especially when lid closed. Two layers:

```bash
# Layer 1 (no sudo) — caffeinate via launchd, prevents idle/display/disk sleep
cat > ~/Library/LaunchAgents/com.user.caffeinate.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.user.caffeinate</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string>
    <string>-dimsu</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
EOF
launchctl load ~/Library/LaunchAgents/com.user.caffeinate.plist

# Layer 2 (needs sudo, system-wide) — disable lid-close sleep entirely
sudo pmset -a disablesleep 1
sudo pmset -a sleep 0
```

If you skip layer 2, keep the lid open OR connect an external display (clamshell mode requires external display + AC power on Apple Silicon).

## Wire Claude Code (from any LAN client)

```bash
export ANTHROPIC_BASE_URL=http://maral.local:11434
export ANTHROPIC_AUTH_TOKEN=ollama
export ANTHROPIC_API_KEY=""
export ANTHROPIC_MODEL=qwen3:14b
export ANTHROPIC_SMALL_FAST_MODEL=qwen3:8b
claude
```

Ollama 0.24.0 has a native `/v1/messages` Anthropic-compatible endpoint. Tool use, `thinking` blocks, and `stop_reason: "tool_use"` all translate cleanly. Verified end-to-end with qwen3:14b.

## Measured performance (M2 MacBook Air 16GB, macOS 26.5)

| Model | Decode tok/s | Prefill tok/s | Load ms (warm) | RAM resident |
|---|---|---|---|---|
| qwen3:14b Q4_K_M | 10.13 | 64.19 | 118 | ~9.5 GB |
| qwen3:8b Q4_K_M | est. 18-22 | est. 100+ | ~80 | ~5 GB |

Compared to Pi 5:

| Device | Model | Decode tok/s | Speedup |
|---|---|---|---|
| Pi 5 16GB CPU | qwen3:8b | 1.92 | baseline |
| Pi 5 16GB CPU | qwen3:4b | 4.05 | 2.1x |
| MacBook Air M2 16GB | qwen3:14b | 10.13 | **5.3x** at larger model |
| MacBook Air M2 16GB | qwen3:8b | ~20 (est.) | ~10x at same model |

## Why this beats buying a Mac Mini M4 24GB BTO ($999)

- Mac Mini M4 24GB would unlock Qwen3.6-27B (~77% SWE-bench Verified) — but requires 24GB unified
- MacBook Air M2 16GB ceiling = qwen3:14b (~65-70% SWE-bench) — meaningful but lower
- Trade: 7-10 percentage points SWE-bench vs $999 saved
- Verdict: **save the $999.** 65-70% SWE-bench is already a working local coding agent. Upgrade later if the gap matters in practice.

If you do later want 27B/77%-class on Apple Silicon:
- Refurb Mac Mini M4 Pro 24GB ~$1,189
- Used Mac Studio M1 Max 32GB ~$700-900 on eBay (cheapest path to 27B + headroom)
- New Mac Mini M4 24GB BTO $999

## Network notes

- MacBook on 192.168.x.x (some other Google Wifi node)
- My Mac on 192.168.x.x
- Google Wifi mesh routes between them transparently
- mDNS (`_rfb._tcp`, `_workstation._tcp`, `_airplay._tcp`) propagates cross-subnet
- TCP 11434 (Ollama) reachable directly from 192.168.x.x → 192.168.x.x

## Storage / NVMe — skipping for now

Plan was to buy a USB3 NVMe enclosure + drive (~$80-90) for the Pi 5 to avoid SD I/O stalls. Maral solves the storage *and* perf problem in one shot — Maral has 550 GB free internal SSD, way faster than any USB-NVMe-on-Pi setup. **Skip the SSD purchase.** Pi 5 + Hailo stays as a vision/Whisper experimentation box.
