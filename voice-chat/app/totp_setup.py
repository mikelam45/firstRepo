"""One-shot TOTP enrollment helper.

Usage (from voice-chat/):
  .venv/bin/python -m app.totp_setup
  .venv/bin/python -m app.totp_setup --qr-link

Writes .totp_secret (mode 600) if missing, then prints the otpauth:// URI once
so you can add it in Google Authenticator / Authy. With --qr-link, mints a
one-time HTTPS page that shows a QR (see app.totp_qr). The secret is not committed.
"""

from __future__ import annotations

import sys

from app.totp_gate import (
    create_secret_file,
    current_secret,
    ensure_configured,
    is_enabled,
    provisioning_uri,
    secret_file_path,
)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    qr_link = "--qr-link" in args
    if qr_link:
        args = [a for a in args if a != "--qr-link"]

    path = secret_file_path()
    file_secret = ""
    if path.is_file():
        try:
            file_secret = path.read_text(encoding="utf-8").strip()
        except OSError:
            file_secret = ""

    if file_secret:
        print("Existing TOTP secret file found.")
        print(f"Secret length: {len(file_secret)}")
        if not qr_link:
            print(provisioning_uri(file_secret))
            print("Add that URI in your authenticator, then open /login.")
            print("Or mint a one-time QR page: python -m app.totp_setup --qr-link")
            return 0
    else:
        # Prefer an already-configured env secret; do not invent a second one.
        ensure_configured()
        if is_enabled() and current_secret():
            print("TOTP secret already configured (env).")
            print(f"Secret length: {len(current_secret() or '')}")
            if not qr_link:
                print(provisioning_uri(current_secret()))
                print("Add that URI in your authenticator, then open /login.")
                print("Or mint a one-time QR page: python -m app.totp_setup --qr-link")
                return 0
        else:
            secret, uri = create_secret_file()
            print("TOTP secret created.")
            print(f"Secret length: {len(secret)}")
            if not qr_link:
                print(uri)
                print("Add that URI in your authenticator, then open /login.")
                print("Or mint a one-time QR page: python -m app.totp_setup --qr-link")
                return 0

    # --qr-link: mint one-time page URL (never print the secret / otpauth).
    from app.totp_qr import main as qr_main

    return qr_main(args)


if __name__ == "__main__":
    sys.exit(main())
