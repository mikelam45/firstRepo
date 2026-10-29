# LingoCoach

IELTS-style speaking practice on a phone, with explanations in English, Putonghua, or Cantonese, plus a daily-conversation track in those three languages.

The current spec is [docs/language-learning-webapp-prd-revOct23.md](docs/language-learning-webapp-prd-revOct23.md) (revOct23). It covers IELTS practice, the six partners aged 27, OpenRouter, and Podman on a MacBook first and an Ubuntu VPS later. On the Mac the OpenRouter key is `/Users/mikelam/firstRepo/openrouter_key/.env_voice_chat`, which is gitignored. The running app is in [voice-chat](voice-chat). On the Mac, `voice-chat/run-local.sh` serves it at http://127.0.0.1:8066 and reads the OpenRouter key from `/Users/mikelam/firstRepo/openrouter_key/.env_voice_chat` when that file is present.

Ubuntu VPS (same port **8066**): see [voice-chat/DEPLOY-VPS.md](voice-chat/DEPLOY-VPS.md). Prefer `voice-chat/deploy-vps.sh` (Podman image from `voice-chat/Containerfile`, or `./restart.sh` if Podman is missing). Put the key in `~/lingocoach.env` (mode 600), not in git.
