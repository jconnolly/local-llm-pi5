# Hailo-10H install — Pi 5 AI HAT+ 2 (parallel/experimental track)

Run on the Pi (`ssh <user>@<pi-ip>`).

**Not for Claude Code.** Use for vision, Whisper, toy chat.

## 1. Add Hailo apt repo (Pi-hosted mirror)

```bash
sudo tee /etc/apt/sources.list.d/hailo.sources <<'EOF'
Types: deb
URIs: https://hailo:chahy5Zo@extranet.raspberrypi.org/hailo
Suites: trixie
Components: main
Signed-By: /usr/share/keyrings/raspberrypi-archive-keyring.pgp
EOF

sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

## 2. Install Hailo-10H meta package

```bash
sudo apt install dkms hailo-h10-all
sudo reboot
```

**Note:** `hailo-all` (no `-h10-`) is the older Hailo-8/8L variant — do not use it on Hailo-10H.

## 3. Verify driver loaded

```bash
ls /dev/hailo*           # should show /dev/hailo0
lsmod | grep hailo       # should show hailo_pci
hailortcli fw-control identify
```

Expected output: device serial, board name, firmware version (5.1.x from apt).

## 4. (Optional) Upgrade to HailoRT 5.2.0 from Developer Zone

Required only for newest LLM HEFs (e.g. Qwen3-VL). Free Hailo Developer Zone signup → download:
- `hailort_5.2.0_arm64.deb`
- `hailort-pcie-driver_5.2.0_all.deb`
- `hailo_gen_ai_model_zoo_5.2.0_arm64.deb`
- `hailo-tappas-core_5.2.0_arm64.deb`

```bash
sudo apt remove h10-hailort-pcie-driver hailo-gen-ai-model-zoo h10-hailort
sudo dpkg --install hailort_*.deb hailort-pcie-driver_*.deb \
                    hailo_gen_ai_model_zoo_*.deb hailo-tappas-core_*.deb
sudo apt install rpicam-apps-hailo-postprocess
sudo reboot
```

## 5. Clone example apps

```bash
cd ~
git clone https://github.com/hailo-ai/hailo-apps.git
cd hailo-apps
./setup.sh   # sets up venv, downloads HEFs
```

Available app categories (under `hailo_apps/python/`):
- `gen_ai_apps/` — LLM, VLM, speech (Whisper)
- `vision_apps/` — detection, pose, segmentation
- `tappas_apps/` — GStreamer-based pipelines

## 6. Run a toy LLM chat

```bash
cd ~/hailo-apps
source venv/bin/activate
python -m hailo_apps.python.gen_ai_apps.llm_chat \
    --model qwen2-1.5b-instruct-function-calling-v1
```

Expected: ~6-8 tok/s decode, 2048 token context cap.

## 7. PCIe Gen3 (informational)

Not needed on AI HAT+ 2 — the device tree overlay enables Gen3 automatically. If `hailortcli identify` reports Gen2 link speed and perf is low, force it:

```bash
sudo sed -i 's/^#\?dtparam=pciex1_gen=.*/dtparam=pciex1_gen=3/' /boot/firmware/config.txt
# or append if missing:
grep -q pciex1_gen /boot/firmware/config.txt || \
  echo 'dtparam=pciex1_gen=3' | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

## Available LLM HEFs (Hailo Model Zoo GenAI v5.3.0)

| Model | Params | Quant | Ctx | Tok/s (decode) | Tool use |
|---|---|---|---|---|---|
| Llama3.2-1B-Instruct | 1B | A8W4 group | 2048 | 9.89 | No |
| Qwen2-1.5B-Instruct | 1.5B | A8W4 channel | 2048 | 8.06 | No |
| **Qwen2-1.5B-Function-Calling-v1** | **1.5B** | **A8W4** | **2048** | **6.69** | **Yes** |
| Qwen2.5-1.5B-Instruct | 1.5B | A8W4 group | 2048 | 7.35 | No |
| Qwen2.5-Coder-1.5B-Instruct | 1.5B | A8W4 channel | 2048 | 8.13 | No |
| Qwen3-1.7B-Instruct | 1.7B | A8W4 group | 2048 | 4.78 | No |
| DeepSeek-R1-Distill-Qwen-1.5B | 1.5B | A8W4 group | 2048 | 7.96 | No |
| Qwen2-VL-2B / Qwen3-VL-2B | 2B | A8W4/A16W4 | 2048 | 7.04 / 4.74 | No |

Source: https://github.com/hailo-ai/hailo_model_zoo_genai/blob/main/docs/MODELS.rst

## Rollback

```bash
sudo apt remove --purge hailo-h10-all dkms
sudo rm /etc/apt/sources.list.d/hailo.sources
sudo apt autoremove
sudo reboot
```
