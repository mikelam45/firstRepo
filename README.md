# LingoCoach

IELTS-style speaking practice on a phone, with explanations in English, Putonghua, or Cantonese, plus a daily-conversation track in those three languages.

The current spec is [docs/language-learning-webapp-prd-revOct23.md](docs/language-learning-webapp-prd-revOct23.md) (revOct23). It covers IELTS practice, the six partners aged 27, OpenRouter, and Podman on a MacBook first and an Ubuntu VPS later. On the Mac the OpenRouter key is `/Users/mikelam/firstRepo/openrouter_key/.env_voice_chat`, which is gitignored. The running app is in [voice-chat](voice-chat). On the Mac, `voice-chat/run-local.sh` serves it at http://127.0.0.1:8066 and reads the OpenRouter key from `/Users/mikelam/firstRepo/openrouter_key/.env_voice_chat` when that file is present.

Ubuntu VPS (same port **8066**): see [voice-chat/DEPLOY-VPS.md](voice-chat/DEPLOY-VPS.md). **First clone** the repo (`git clone … ~/lingocoach`) before `cd ~/lingocoach/voice-chat` — that path does not exist until then. Prefer `voice-chat/deploy-vps.sh` (Podman image from `voice-chat/Containerfile`, or `./restart.sh` if Podman is missing). Put secrets in `~/lingocoach.env` (mode 600), not in git.

**HTTPS on the VPS:** point a real domain’s DNS A/AAAA at the VPS, open ports **80** (ACME HTTP-01) and **8066** (public TLS), then:

```bash
# after: git clone https://github.com/mikelam45/firstRepo.git ~/lingocoach
cd ~/lingocoach/voice-chat
# Domain can be in ~/lingocoach.env or exported (example host = operator VPS name):
# export LINGOCOACH_DOMAIN=103-195-5-86.as-cloud-xip.com
# optional: export LINGOCOACH_ACME_EMAIL=you@example.com
./deploy-vps.sh --https
# or: ./deploy-vps.sh --https --systemd
```

That binds the app to `127.0.0.1:18066` and puts **Caddy** in front on **`https://DOMAIN:8066/`** (Let’s Encrypt via :80, HTTP→HTTPS redirect to :8066). Visit `https://103-195-5-86.as-cloud-xip.com:8066/` — include **`:8066`**; this is not port-443 `https://DOMAIN/`. Details and firewall notes are in [voice-chat/DEPLOY-VPS.md](voice-chat/DEPLOY-VPS.md).

## TOTP unlock gate (optional locally, recommended on a VPS)

When a TOTP secret is configured, unauthenticated browsers are sent to `/login` and API calls return `401` until a valid 6-digit authenticator code sets an HttpOnly session cookie (`lc_session`, 7 days).

**Env vars (never commit):** `LINGOCOACH_TOTP_SECRET` (preferred) or `TOTP_SECRET` — base32. Or a local file `voice-chat/.totp_secret` (gitignored, mode 600).

**When unset:** the gate is off (open local/dev access). The process logs `TOTP not configured`. On a public VPS, set the secret so the coach stays locked.

**Enroll (once):**

```bash
cd voice-chat
.venv/bin/python -m app.totp_setup
# Prints an otpauth:// URI once — add it in Google Authenticator / Authy / 1Password.
# Or generate yourself: python -c 'import pyotp; print(pyotp.random_base32())'
# Then put LINGOCOACH_TOTP_SECRET=<that value> in ~/lingocoach.env (VPS) or export it locally.
```

**One-time QR page (phone scan):** after the secret is set on the VPS, mint a single-use link (hash stored in gitignored `.totp_qr_token`, mode 600; expires ~20 minutes; invalidated after the first successful page load):

```bash
cd ~/lingocoach/voice-chat
# URL from LINGOCOACH_PUBLIC_BASE, or DOMAIN + port (example host):
# export LINGOCOACH_DOMAIN=103-195-5-86.as-cloud-xip.com
# export LINGOCOACH_HTTPS_PORT=8066
# optional override: export LINGOCOACH_PUBLIC_BASE=https://103-195-5-86.as-cloud-xip.com:8066
.venv/bin/python -m app.totp_qr
# or: .venv/bin/python -m app.totp_setup --qr-link
# Prints: https://103-195-5-86.as-cloud-xip.com:8066/setup/qr?token=…
```

Open that URL on your phone, scan the QR (or type the manual base32 key), then go to `/login` and enter the 6-digit code. Do not leave `/setup/qr` without a token — it is not a permanent public QR.

Open `http://127.0.0.1:8066/login` (or `https://YOUR_DOMAIN:8066/login` on a VPS with `--https`), enter the current code, then use the coach as usual. On HTTPS deploys the session cookie `lc_session` is HttpOnly **and Secure**.
