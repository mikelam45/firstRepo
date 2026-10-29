# Deploy LingoCoach on an Ubuntu VPS (port 8066)

Same port as the Mac (`run-local.sh` / `restart.sh`): **8066**.

- **HTTP-only:** app published on `0.0.0.0:8066` (fine for typing smoke tests).
- **HTTPS (recommended for phones / mic):** Caddy terminates TLS on **public `:8066`**, uses **`:80` for Let's Encrypt HTTP-01** (and redirects browsers to HTTPS on 8066), and reverse-proxies to the app on **`127.0.0.1:18066`**. The app is not exposed publicly.

Canonical public URL form:

`https://YOUR_DOMAIN:8066/`

Example (operator-supplied VPS host):

`https://103-195-5-86.as-cloud-xip.com:8066/`

This is **not** the usual `https://YOUR_DOMAIN/` on port 443. Include `:8066` in the URL.

This cloud agent has **no SSH credentials** for your VPS. Run the steps below on the VPS yourself. **Never invent a hostname** — use the DNS name you control (`LINGOCOACH_DOMAIN`).

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

## 2. First clone (required — creates `~/lingocoach`)

`cd ~/lingocoach/voice-chat` fails with **No such file or directory** until this step runs. That means the repo was never cloned (not a deploy-script bug). As root, `~` is `/root`, so the tree is `/root/lingocoach/...`. Any path is fine — clone into that name once:

```bash
# first time (creates ~/lingocoach with voice-chat/ inside)
git clone https://github.com/mikelam45/firstRepo.git ~/lingocoach
cd ~/lingocoach
git checkout cursor/enhance-lingocoach-prd-aecd
# then work from: cd ~/lingocoach/voice-chat

# later updates
cd ~/lingocoach
git fetch origin
git checkout cursor/enhance-lingocoach-prd-aecd
git pull origin cursor/enhance-lingocoach-prd-aecd
```

Prefer branch `cursor/enhance-lingocoach-prd-aecd` (current PR). Use `main` only if you intentionally want the default branch instead.

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
LINGOCOACH_DOMAIN=103-195-5-86.as-cloud-xip.com
EOF
chmod 600 ~/lingocoach.env
```

`LINGOCOACH_DOMAIN` can live in that file (read by `./deploy-vps.sh --https`) or be `export`ed in the shell. Replace the example host with your DNS name if different.

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

## 4b. HTTPS with Caddy on :8066 (recommended)

You need:

1. A **real domain** (or subdomain) whose DNS **A** (and optional **AAAA**) record points at this VPS.
2. Port **80** reachable from the internet (Let's Encrypt **HTTP-01**).
3. Port **8066** reachable for **HTTPS** (Caddy TLS + SNI).
4. Env var **`LINGOCOACH_DOMAIN`** set to that name (aliases: `DOMAIN`, `VPS_HOST`). Optional: `LINGOCOACH_ACME_EMAIL` for the Let's Encrypt account contact.

Optional overrides (defaults match the canonical URL):

| Env | Default | Role |
|-----|---------|------|
| `LINGOCOACH_HTTPS_PORT` / `HTTPS_PORT` | `8066` | Public TLS listen port (in the URL) |
| `LINGOCOACH_INTERNAL_PORT` / `INTERNAL_PORT` | `18066` | Loopback upstream for the app |

```bash
# DNS first: A/AAAA → this VPS, then:
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 8066/tcp
# Close any prior plain-HTTP publish of 8066 once Caddy owns that port:
# sudo ufw delete allow 8066/tcp   # only if you had opened it for HTTP-only, then re-add after --https
# (keep 8066 open — it is now HTTPS, not the raw app)
sudo ufw enable

cd ~/lingocoach/voice-chat
chmod +x deploy-vps.sh restart.sh run-local.sh

# Domain: already in ~/lingocoach.env (see §3), or export here instead:
# export LINGOCOACH_DOMAIN=103-195-5-86.as-cloud-xip.com
# optional:
# export LINGOCOACH_ACME_EMAIL=you@example.com
# export LINGOCOACH_HTTPS_PORT=8066
# export LINGOCOACH_INTERNAL_PORT=18066

./deploy-vps.sh --https
# durable unit + HTTPS:
# ./deploy-vps.sh --https --systemd
```

What `--https` does:

1. Starts the app (Podman or `./restart.sh`) bound to **`127.0.0.1:18066`** only (so Caddy can bind public **8066**).
2. Sets `LINGOCOACH_HTTPS=1` so the TOTP `lc_session` cookie gets the **Secure** flag (and trusts `X-Forwarded-Proto` from the proxy).
3. Renders `Caddyfile.template` → `/etc/caddy/Caddyfile` with your domain and ports (validates with `caddy validate`).
4. Enables/reloads Caddy. Caddy obtains a Let's Encrypt certificate (HTTP-01 on **:80**), serves **`https://YOUR_DOMAIN:8066/`**, and redirects plain **HTTP :80** → that HTTPS URL.
5. Does **not** enable HSTS (HSTS would push browsers to `:443`, which this layout does not serve).

Visit **`https://YOUR_DOMAIN:8066/`** (login at `/login`). For the example host:

`https://103-195-5-86.as-cloud-xip.com:8066/login`

Health from the VPS:

```bash
curl -fsS http://127.0.0.1:18066/health
curl -fsSk https://127.0.0.1:8066/health -H "Host: 103-195-5-86.as-cloud-xip.com"
# or, once DNS + cert are ready:
curl -fsS https://103-195-5-86.as-cloud-xip.com:8066/health
```

Companion-only (app already running on loopback): set `LINGOCOACH_DOMAIN` and re-run `./deploy-vps.sh --https` — it rewrites Caddy and restarts/replaces the container bind as needed.

Template: `voice-chat/Caddyfile.template` (placeholders only; no hardcoded “default” domain in the script — the example above is documentation for the operator’s host).

**ACME note:** HTTP-01 needs **:80**. If :80 cannot be opened, use DNS challenge or TLS-ALPN (advanced; not the default path in `deploy-vps.sh`).

**Migrating from an older 443-only Caddy layout:** re-run `./deploy-vps.sh --https` with `LINGOCOACH_DOMAIN` set. The new Caddyfile listens on **8066** for TLS and moves the app to **18066**. Open **8066/tcp** (and **80**); you no longer need public **443** for this pattern. If a previous HTTP-only app was published on public 8066, stop it first (the script’s Podman/restart path does this).

## 5. Health check

On the VPS:

```bash
# HTTP-only deploy:
curl -fsS http://127.0.0.1:8066/health
# HTTPS deploy (app on internal port):
curl -fsS http://127.0.0.1:18066/health
# {"status":"ok"}
```

From your laptop (replace host and SSH user):

```bash
ssh YOUR_USER@VPS_HOST 'curl -fsS http://127.0.0.1:18066/health'
```

## Update after a new commit

```bash
cd ~/lingocoach
git pull origin cursor/enhance-lingocoach-prd-aecd
cd voice-chat
./deploy-vps.sh
# HTTPS again (keeps Caddy + localhost bind on 18066):
# LINGOCOACH_DOMAIN=103-195-5-86.as-cloud-xip.com ./deploy-vps.sh --https
# or: systemctl --user restart lingocoach.service
```
