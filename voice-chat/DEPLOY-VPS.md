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
sudo apt-get install -y podman git curl python3-venv python3-pip
sudo loginctl enable-linger "$USER"
podman info   # should report rootless (optional if you use --local / HTTPS venv path)
```

`python3-venv` + `python3-pip` are required for `./deploy-vps.sh --https` (venv path). Without them you get `.venv/bin/python: No module named pip`.

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

**One-time enroll page (Mac Chrome → Google Authenticator setup key):** the secret/QR is **not** left on a permanent public URL. On the VPS, with the app already serving HTTPS and `LINGOCOACH_TOTP_SECRET` set:

```bash
cd ~/lingocoach/voice-chat
# Preferred helper (uses LINGOCOACH_PUBLIC_BASE / DOMAIN from env or ~/lingocoach.env;
# default base https://103-195-5-86.as-cloud-xip.com:8066):
./lingocoachctl.sh qr
# alias: ./lingocoachctl.sh new-qr

# Or call the module directly:
# export LINGOCOACH_PUBLIC_BASE=https://103-195-5-86.as-cloud-xip.com:8066
# .venv/bin/python -m app.totp_qr
# equivalent: .venv/bin/python -m app.totp_setup --qr-link
```

That prints `https://103-195-5-86.as-cloud-xip.com:8066/setup/qr?token=…` (shape: `/setup/qr?token=<high-entropy>`). Every `qr` / `new-qr` call mints a **new** random `?token=` (overwrites hashed `.totp_qr_token` and invalidates any previous enroll URL immediately). Open the **latest** URL **once on the Mac** (Chrome). Leave the page open (do not refresh).

**Primary — Enter a setup key in Google Authenticator (do not use iPhone Camera):**

1. On the Mac, open the enroll URL; keep the page on screen.
2. On the iPhone, open **Google Authenticator** → **+** → **Enter a setup key** / **輸入設定密鑰**.
3. Account: `LingoCoach`. Key: paste the huge base32 key (Copy). Type: **Time based** / **基於時間**.
4. Tap **Add**, then open `/login` and enter the 6-digit code.

Do **not** scan this page with the iPhone Camera app. Camera opens Apple Passwords / 安全金鑰, **not** Google Authenticator. If GA shows 「請改用相機」, ignore that prompt and use the setup key.

**Secondary — scan from inside Google Authenticator (or Android):**

Google Authenticator → **+** → **Scan a QR code**, pointed at the white SVG QR on the Mac. Not the Camera app.

**If the page is opened on the iPhone:** tap **Open in Google Authenticator** (`otpauth://` deep link). iOS may still offer Passwords; if so, Cancel and use the setup key. After restart/deploy, remint with `./lingocoachctl.sh qr` (or `new-qr`) and use the newly printed URL — do not reuse an older `?token=` from chat/history. The token is stored **hashed** in gitignored `voice-chat/.totp_qr_token` (mode 600), expires in ~20 minutes, is **replaced on every remint**, and is **invalidated after the first successful page load**. A refresh or second visit returns 404.

When `LINGOCOACH_TOTP_SECRET` / `TOTP_SECRET` / `.totp_secret` is absent, the gate stays off (open access). On a public VPS, keep the secret set.

## 4a. HTTP-only on 8066

From `voice-chat/`:

```bash
cd ~/lingocoach/voice-chat
chmod +x deploy-vps.sh lingocoachctl.sh restart.sh run-local.sh
./deploy-vps.sh
```

That builds the Podman image from `Containerfile` and runs:

`0.0.0.0:8066` → container port 8066.

Optional long-running systemd:

```bash
# Recommended (venv + uvicorn unit — survives reboot; no Podman required):
./deploy-vps.sh --systemd
# alias: ./deploy-vps.sh --install-service
# Podman quadlet instead:
./deploy-vps.sh --podman --systemd
```

If Podman is not installed yet, `./deploy-vps.sh` falls back to `./restart.sh` (venv + uvicorn), same as the Mac.

Force the non-container path:

```bash
./deploy-vps.sh --local
# HTTPS without Podman (venv + Caddy):
./deploy-vps.sh --https --local
```

### Podman build / DNS (`Temporary failure resolving 'deb.debian.org'` / `pypi.org`)

**Do this on the VPS (recommended):** HTTPS deploy uses the **venv** path by default so you never wait on broken Podman DNS:

```bash
sudo apt-get install -y python3-venv python3-pip
cd ~/lingocoach
git pull origin cursor/enhance-lingocoach-prd-aecd
cd voice-chat
# If you already hit "No module named pip", drop the broken tree once:
rm -rf .venv
./deploy-vps.sh --https
# same as: ./deploy-vps.sh --https --local
```

If you still see `apt-get` / `espeak-ng` in the build log, you are on an **old** commit — `git pull` first. Current `Containerfile` has **no** `apt-get`.

Force a Podman image only when DNS works (`--network=host` is passed to `podman build`):

```bash
./deploy-vps.sh --https --podman
# or: LINGOCOACH_USE_PODMAN=1 ./deploy-vps.sh --https
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
chmod +x deploy-vps.sh lingocoachctl.sh restart.sh run-local.sh

# Domain: already in ~/lingocoach.env (see §3), or export here instead:
# export LINGOCOACH_DOMAIN=103-195-5-86.as-cloud-xip.com
# optional:
# export LINGOCOACH_ACME_EMAIL=you@example.com
# export LINGOCOACH_HTTPS_PORT=8066
# export LINGOCOACH_INTERNAL_PORT=18066

./deploy-vps.sh --https
# Recommended durable path (venv systemd unit + Caddy; survives reboot):
./deploy-vps.sh --https --systemd
```

What `--https` does:

1. Starts the app (Podman, `./restart.sh`, or **systemd unit** with `--systemd`) bound to **`127.0.0.1:18066`** only (so Caddy can bind public **8066**).
2. Sets `LINGOCOACH_HTTPS=1` so the TOTP `lc_session` cookie gets the **Secure** flag (and trusts `X-Forwarded-Proto` from the proxy).
3. Renders `Caddyfile.template` → `/etc/caddy/Caddyfile` with your domain and ports (validates with `caddy validate`).
4. Enables/reloads Caddy. Caddy obtains a Let's Encrypt certificate (HTTP-01 on **:80**), serves **`https://YOUR_DOMAIN:8066/`**, and redirects plain **HTTP :80** → that HTTPS URL.
5. Does **not** enable HSTS (HSTS would push browsers to `:443`, which this layout does not serve).

**Why `--systemd`:** a bare `./deploy-vps.sh --https` backgrounds uvicorn with `nohup`. If that process dies, **Caddy stays up and clients see 502**. The venv unit (`lingocoach.service`) restarts the app on failure and after reboot.

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

## 5. systemd service (venv + uvicorn)

Use this after (or instead of) a one-shot `nohup` HTTPS deploy so the **app** survives reboot and restarts on crash. **Caddy** remains the distro unit `caddy.service` (separate).

Paths assume the usual clone at `~/lingocoach` (as root that is `/root/lingocoach`).

### Install / enable (first time or after pull)

```bash
cd ~/lingocoach
git pull origin cursor/enhance-lingocoach-prd-aecd
cd voice-chat
chmod +x deploy-vps.sh lingocoachctl.sh restart.sh run-local.sh

# Preferred: deploy + install unit + Caddy in one shot
./deploy-vps.sh --https --systemd

# Or install/refresh the unit only (app on 127.0.0.1:18066):
./lingocoachctl.sh install
# alias via deploy:
# ./deploy-vps.sh --install-service
# ./deploy-vps.sh --systemd
```

As **root** the unit is installed system-wide:

```bash
# installed to: /etc/systemd/system/lingocoach.service
systemctl enable --now lingocoach.service
journalctl -u lingocoach.service -f
```

As a **non-root** user (user unit + linger for reboot survival):

```bash
# installed to: ~/.config/systemd/user/lingocoach.service
systemctl --user enable --now lingocoach.service
sudo loginctl enable-linger "$USER"
journalctl --user -u lingocoach.service -f
```

Unit essentials (HTTPS layout):

| Key | Value |
|-----|--------|
| WorkingDirectory | `~/lingocoach/voice-chat` (absolute path written at install) |
| EnvironmentFile | `~/lingocoach.env` (mode 600; secrets not printed) |
| Environment | `PORT=18066`, `HOST=127.0.0.1`, `LINGOCOACH_HTTPS=1` |
| ExecStart | `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18066` |
| Type | `simple` (uvicorn is not sd_notify; readiness is via ctl `/health` wait) |
| Restart | `on-failure` |

Podman quadlet (optional): `./deploy-vps.sh --podman --systemd` still installs `lingocoach.container` under `~/.config/containers/systemd/`.

### start / stop / restart / qr

```bash
cd ~/lingocoach/voice-chat

./lingocoachctl.sh start      # start unit, then wait for /health (up to ~45s)
./lingocoachctl.sh stop       # stop app unit only (Caddy stays up)
./lingocoachctl.sh stop-all   # stop app + caddy.service
./lingocoachctl.sh restart    # restart unit, then wait for /health
./lingocoachctl.sh status
./lingocoachctl.sh qr         # mint a fresh one-time Authenticator QR URL (~20 min, single use)
# alias: ./lingocoachctl.sh new-qr

# Or raw systemctl (root / system unit):
sudo systemctl start lingocoach.service
sudo systemctl stop lingocoach.service
sudo systemctl restart lingocoach.service
```

`start` / `restart` / `install` wait for `http://127.0.0.1:18066/health` after systemd reports the unit active (`Type=simple` is active before uvicorn binds). On timeout or crash they print `journalctl -u lingocoach -n 40`. Prefer the ctl over raw `systemctl start` when you want that readiness check.

`stop` leaves Caddy running on purpose (TLS front-end). Use `stop-all` when you want both down. `qr` prints only the enroll URL (never the TOTP secret). Treat any enroll URL pasted into chat as burned: remint with `./lingocoachctl.sh qr`.

### status check

```bash
cd ~/lingocoach/voice-chat
./lingocoachctl.sh status
```

Prints clear **OK/FAIL** for:

1. `lingocoach.service` active
2. `curl -fsS http://127.0.0.1:18066/health` (retries a few seconds if the unit is already active)
3. `caddy.service` active
4. optional external `https://103-195-5-86.as-cloud-xip.com:8066/health` (short timeout; failure often means cloud firewall, not a dead app)

If the unit is active but loopback `/health` still fails after the short retry, `status` dumps recent journal lines. Prefer `./lingocoachctl.sh start` (which already waits) over racing `status` immediately after a raw `systemctl start`.

Manual equivalents:

```bash
systemctl is-active lingocoach.service    # or: systemctl --user is-active lingocoach.service
curl -fsS --connect-timeout 3 --max-time 5 http://127.0.0.1:18066/health
systemctl is-active caddy
curl -fsS --connect-timeout 3 --max-time 8 \
  https://103-195-5-86.as-cloud-xip.com:8066/health
```

## 6. Health check

On the VPS:

```bash
# Prefer the combined status helper (unit + health + Caddy):
cd ~/lingocoach/voice-chat && ./lingocoachctl.sh status

# HTTP-only deploy:
curl -fsS http://127.0.0.1:8066/health
# HTTPS deploy (app on internal port):
curl -fsS http://127.0.0.1:18066/health
# {"status":"ok"}
```

If deploy says `health check failed for http://127.0.0.1:18066/health`:

```bash
tail -n 50 ~/lingocoach-uvicorn.log
ss -lntp | grep -E '18066|8066' || true
# Re-pull and retry (deps install in foreground first now):
cd ~/lingocoach && git pull origin cursor/enhance-lingocoach-prd-aecd
cd voice-chat && ./deploy-vps.sh --https
```

If **`Job for caddy.service failed`** after “Valid configuration”:

```bash
sudo journalctl -u caddy -n 50 --no-pager
sudo ss -lntp | grep -E ':80|:8066'
# Almost always: leftover uvicorn still on public 8066. Free it, then:
cd ~/lingocoach && git pull origin cursor/enhance-lingocoach-prd-aecd
cd voice-chat
PORT=8066 bash -c '. ./local-common.sh && force_stop_port'
./deploy-vps.sh --https
```

Also free **:80** if another web server owns it (Apache/nginx). Caddy needs :80 for Let’s Encrypt HTTP-01 and :8066 for HTTPS.

From your laptop (replace host and SSH user):

```bash
ssh YOUR_USER@VPS_HOST 'curl -fsS http://127.0.0.1:18066/health'
```

### External `curl` hangs on `:8066` (firewall — not the app)

If **`:80` returns Caddy’s 301** to `https://YOUR_DOMAIN:8066/...` but **`https://YOUR_DOMAIN:8066/` hangs** until timeout, the app and Caddy are usually fine. A **TCP connect timeout** means packets never reach the VPS on **8066** — almost always the **cloud provider security group / firewall panel**, even when `ufw` already allows the port. Do **not** keep debugging uvicorn until listeners and local HTTPS curl succeed.

Use short timeouts so the client does not hang forever:

```bash
curl -v --connect-timeout 5 --max-time 10 https://YOUR_DOMAIN:8066/
```

**On the VPS (ordered):**

```bash
# 1) Who is listening?
sudo ss -lntp | grep -E ':80|:8066|:18066'

# 2) App + Caddy locally (expect JSON / HTML; -k ignores cert name mismatch on 127.0.0.1)
curl -fsS --connect-timeout 5 --max-time 10 http://127.0.0.1:18066/health
curl -vsk --connect-timeout 5 --max-time 10 https://127.0.0.1:8066/health \
  -H "Host: 103-195-5-86.as-cloud-xip.com"

# 3) Host firewall
sudo ufw allow 80/tcp
sudo ufw allow 8066/tcp
sudo ufw status verbose
```

**Cloud panel (usual fix):** open **inbound TCP 8066** (and **80** for ACME / HTTP→HTTPS) to the VPS in the provider’s security group / network ACL. `ufw` alone is not enough if the panel still drops 8066.

**From your laptop:**

```bash
curl -v --connect-timeout 5 --max-time 10 http://103-195-5-86.as-cloud-xip.com/
# expect 301 → https://…:8066/
curl -v --connect-timeout 5 --max-time 10 https://103-195-5-86.as-cloud-xip.com:8066/
# if this hangs at "Trying …:8066", the panel is still blocking 8066
```

**Optional — TLS on `:443` instead** (avoids odd-port blocks when providers only allow 80/443):

```bash
# after ufw allow 443/tcp and opening 443 in the cloud panel:
export LINGOCOACH_DOMAIN=103-195-5-86.as-cloud-xip.com
export LINGOCOACH_HTTPS_PORT=443
cd ~/lingocoach/voice-chat && ./deploy-vps.sh --https
# then visit https://103-195-5-86.as-cloud-xip.com/  (no :8066 in the URL)
```

Keep **:80** open for Let’s Encrypt. Re-run deploy after changing `LINGOCOACH_HTTPS_PORT` so Caddyfile + redirects match.

## Update after a new commit

```bash
cd ~/lingocoach
git pull origin cursor/enhance-lingocoach-prd-aecd
cd voice-chat
# Durable HTTPS (reinstalls/refreshes unit + Caddy):
./deploy-vps.sh --https --systemd
# Or restart the already-installed unit after a code-only change:
./lingocoachctl.sh restart
# (root) systemctl restart lingocoach.service
# (user)  systemctl --user restart lingocoach.service
```
