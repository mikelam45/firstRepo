# Deploy LingoCoach on an Ubuntu VPS (port 8066)

Same port as the Mac (`run-local.sh` / `restart.sh`): **8066**.

- **HTTP-only:** app published on `0.0.0.0:8066` (fine for typing smoke tests).
- **HTTPS (recommended for phones / mic):** Caddy terminates TLS on **443**, redirects **80→443**, and reverse-proxies to `127.0.0.1:8066`. The app is not exposed publicly on 8066.

This cloud agent has **no SSH credentials** for your VPS. Run the steps below on the VPS yourself. **Never invent a hostname** — use the DNS name you control.

## 1. One-time host setup

```bash
sudo apt-get update
sudo apt-get install -y podman git curl
sudo loginctl enable-linger "$USER"
podman info   # should report rootless
```

For HTTPS you will also need Caddy (the deploy script can install it):

```bash
# optional manual install; otherwise: ./deploy-vps.sh --https installs via apt
sudo apt-get install -y caddy
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

## 3. Secrets (never commit)

On the Mac the OpenRouter key lives at `/Users/mikelam/firstRepo/openrouter_key/.env_voice_chat` (gitignored).

On the VPS put secrets outside the git tree in `~/lingocoach.env` (mode 600):

```bash
# Generate a TOTP secret once (on any machine with pyotp), then store only on the VPS:
#   python3 -c 'import pyotp; print(pyotp.random_base32())'
# Or on the VPS after venv exists:
#   cd ~/lingocoach/voice-chat && .venv/bin/python -m app.totp_setup
#   (writes gitignored voice-chat/.totp_secret; for Podman prefer the env var below)

cat > ~/lingocoach.env <<'EOF'
OPENROUTER_API_KEY=PASTE_KEY_HERE
LINGOCOACH_TOTP_SECRET=PASTE_BASE32_SECRET_HERE
EOF
chmod 600 ~/lingocoach.env
```

Or use `~/lingocoach/voice-chat/.env` with mode `600` (also gitignored). Do not paste keys or TOTP secrets into chat or commit them.

**TOTP enroll:** add the same base32 secret (or the printed `otpauth://` URI from `python -m app.totp_setup`) in Google Authenticator / Authy / 1Password as issuer **LingoCoach**. After deploy, open `/login` on your public URL, enter the 6-digit code, then the coach unlocks (HttpOnly cookie, 7 days; **Secure** when HTTPS is enabled).

When `LINGOCOACH_TOTP_SECRET` / `TOTP_SECRET` / `.totp_secret` is absent, the gate stays off (open access). On a public VPS, keep the secret set.

## 4a. HTTP-only on 8066

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

Firewall for HTTP-only:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 8066/tcp
sudo ufw enable
```

Open `http://VPS_HOST:8066` (replace with your IP or hostname). Microphone needs HTTPS on a public IP; for typing-only smoke tests plain HTTP is enough.

## 4b. HTTPS with Caddy (recommended)

You need:

1. A **real domain** (or subdomain) whose DNS **A** (and optional **AAAA**) record points at this VPS.
2. Ports **80** and **443** reachable from the internet (Let's Encrypt HTTP-01 + HTTPS).
3. Env var **`LINGOCOACH_DOMAIN`** set to that name (aliases: `DOMAIN`, `VPS_HOST`). Optional: `LINGOCOACH_ACME_EMAIL` for the Let's Encrypt account contact.

```bash
# DNS first: A/AAAA → this VPS, then:
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
# Prefer leaving 8066 closed to the internet when using --https
sudo ufw enable

cd ~/lingocoach/voice-chat
chmod +x deploy-vps.sh restart.sh run-local.sh

# Replace with YOUR domain — never commit it into the repo defaults.
export LINGOCOACH_DOMAIN=YOUR_DOMAIN_HERE
# optional:
# export LINGOCOACH_ACME_EMAIL=you@YOUR_DOMAIN_HERE

./deploy-vps.sh --https
# durable unit + HTTPS:
# ./deploy-vps.sh --https --systemd
```

What `--https` does:

1. Starts the app (Podman or `./restart.sh`) bound to **`127.0.0.1:8066`** only.
2. Sets `LINGOCOACH_HTTPS=1` so the TOTP `lc_session` cookie gets the **Secure** flag (and trusts `X-Forwarded-Proto` from the proxy).
3. Renders `Caddyfile.template` → `/etc/caddy/Caddyfile` with your domain (validates with `caddy validate`).
4. Enables/reloads Caddy. Caddy obtains a Let's Encrypt certificate, serves **https://YOUR_DOMAIN/**, and **redirects HTTP :80 → HTTPS**.
5. Sends `Strict-Transport-Security` (HSTS) on HTTPS responses.

Visit **`https://YOUR_DOMAIN/`** (login at `/login`). Health from the VPS:

```bash
curl -fsS http://127.0.0.1:8066/health
curl -fsS https://YOUR_DOMAIN/health
```

Companion-only (app already running on loopback): set `LINGOCOACH_DOMAIN` and re-run `./deploy-vps.sh --https` — it rewrites Caddy and restarts/replaces the container bind as needed.

Template: `voice-chat/Caddyfile.template` (placeholders only; no real hostname in git).

## 5. Health check

On the VPS:

```bash
curl -fsS http://127.0.0.1:8066/health
# {"status":"ok"}
```

From your laptop (replace host and SSH user):

```bash
ssh YOUR_USER@VPS_HOST 'curl -fsS http://127.0.0.1:8066/health'
```

## Update after a new commit

```bash
cd ~/lingocoach
git pull origin cursor/enhance-lingocoach-prd-aecd
cd voice-chat
./deploy-vps.sh
# HTTPS again (keeps Caddy + localhost bind):
# LINGOCOACH_DOMAIN=YOUR_DOMAIN_HERE ./deploy-vps.sh --https
# or: systemctl --user restart lingocoach.service
```
