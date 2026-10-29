# Deploy LingoCoach on an Ubuntu VPS (port 8066)

Same port as the Mac (`run-local.sh` / `restart.sh`): **8066**, bound to `0.0.0.0`.

This cloud agent has **no SSH credentials** for your VPS. Run the steps below on the VPS yourself.

## 1. One-time host setup

```bash
sudo apt-get update
sudo apt-get install -y podman git curl
sudo loginctl enable-linger "$USER"
podman info   # should report rootless
```

## 2. Clone / pull this branch

```bash
# first time
git clone https://github.com/mikelam45/firstRepo.git ~/lingocoach
cd ~/lingocoach
git checkout cursor/enhance-lingocoach-prd-aecd

# later updates
cd ~/lingocoach
git fetch origin
git checkout cursor/enhance-lingocoach-prd-aecd
git pull origin cursor/enhance-lingocoach-prd-aecd
```

## 3. OpenRouter key (never commit)

On the Mac the key lives at `/Users/mikelam/firstRepo/openrouter_key/.env_voice_chat` (gitignored).

On the VPS put the **same value** outside the git tree:

```bash
printf 'OPENROUTER_API_KEY=PASTE_KEY_HERE\n' > ~/lingocoach.env
chmod 600 ~/lingocoach.env
```

Or use `~/lingocoach/voice-chat/.env` with mode `600` (also gitignored). Do not paste the key into chat or commit it.

## 4. Start on 8066

From `voice-chat/`:

```bash
cd ~/lingocoach/voice-chat
chmod +x deploy-vps.sh restart.sh run-local.sh
./deploy-vps.sh
```

That builds the Podman image from `Containerfile` and runs:

`0.0.0.0:8066` → container port 8066.

Optional long-running systemd (user quadlet):

```bash
./deploy-vps.sh --systemd
# logs: journalctl --user -u lingocoach.service -f
```

If Podman is not installed yet, `./deploy-vps.sh` falls back to `./restart.sh` (venv + uvicorn), same as the Mac.

Force the non-container path:

```bash
./deploy-vps.sh --local
```

## 5. Health check

On the VPS:

```bash
curl -fsS http://127.0.0.1:8066/health
# {"status":"ok"}
```

From your laptop (replace `VPS_HOST` and SSH user):

```bash
ssh YOUR_USER@VPS_HOST 'curl -fsS http://127.0.0.1:8066/health'
```

Open `http://VPS_HOST:8066` in a browser. Microphone needs HTTPS on a public IP; for typing-only smoke tests plain HTTP is enough. For phones, put Caddy (or similar) in front later — see PRD §21.5 (that section still mentions 8080; this checkout uses **8066**).

## 6. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 8066/tcp
sudo ufw enable
```

## Update after a new commit

```bash
cd ~/lingocoach
git pull origin cursor/enhance-lingocoach-prd-aecd
cd voice-chat
./deploy-vps.sh
# or: systemctl --user restart lingocoach.service
```
