"""One-shot TOTP enrollment helper.

Usage (from voice-chat/):
  .venv/bin/python -m app.totp_setup
  .venv/bin/python -m app.totp_setup --qr-link

Uses the same canonical secret loader as the running gate
(``LINGOCOACH_TOTP_SECRET`` / ``TOTP_SECRET`` / ``.totp_secret``). Writes
``.totp_secret`` (mode 600) only when none of those are set. With --qr-link,
mints a one-time HTTPS page (see app.totp_qr). ``--qr-link`` / ``qr`` remints
the URL token only — it does not rotate the TOTP secret.
"""

from __future__ import annotations

import sys

from app.totp_gate import (
    create_secret_file,
    current_secret,
    ensure_configured,
    is_enabled,
    provisioning_uri,
)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    qr_link = "--qr-link" in args
    if qr_link:
        args = [a for a in args if a != "--qr-link"]

    # Same order as the uvicorn process: env first, then .totp_secret.
    ensure_configured()
    secret = current_secret() if is_enabled() else None
    if secret:
        print("TOTP secret already configured.")
        print(f"Secret length: {len(secret)}")
        if not qr_link:
            print(provisioning_uri(secret))
            print("Add that URI in your authenticator, then open /login.")
            print("Or mint a one-time QR page: python -m app.totp_setup --qr-link")
            print("(qr remints the URL token only; it does not rotate this secret.)")
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
