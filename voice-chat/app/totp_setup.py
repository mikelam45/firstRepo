"""One-shot TOTP enrollment helper.

Usage (from voice-chat/):
  .venv/bin/python -m app.totp_setup

Writes .totp_secret (mode 600) if missing, then prints the otpauth:// URI once
so you can add it in Google Authenticator / Authy. The secret is not committed.
"""

from __future__ import annotations

import sys

from app.totp_gate import create_secret_file, provisioning_uri, secret_file_path


def main() -> int:
    path = secret_file_path()
    if path.is_file() and path.read_text(encoding="utf-8").strip():
        # Re-print URI for an existing local secret (stdout only; never logged by the server).
        secret = path.read_text(encoding="utf-8").strip()
        print("Existing TOTP secret file found.")
        print(f"Secret length: {len(secret)}")
        print(provisioning_uri(secret))
        print("Add that URI in your authenticator, then open /login.")
        return 0
    secret, uri = create_secret_file()
    print("TOTP secret created.")
    print(f"Secret length: {len(secret)}")
    print(uri)
    print("Add that URI in your authenticator, then open /login.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
