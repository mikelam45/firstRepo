import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    from app.limits import LIMITER

    LIMITER.reset()
    yield
    LIMITER.reset()


@pytest.fixture(autouse=True)
def _totp_off_by_default(monkeypatch, tmp_path):
    """Keep the suite ungated unless a test opts in with LINGOCOACH_TOTP_SECRET."""
    from app import totp_gate
    from app import totp_qr

    totp_gate.reset_for_tests()
    totp_qr.reset_for_tests(tmp_path / ".totp_qr_token_absent")
    monkeypatch.delenv("LINGOCOACH_TOTP_SECRET", raising=False)
    monkeypatch.delenv("TOTP_SECRET", raising=False)
    monkeypatch.setattr(totp_gate, "_SECRET_FILE", tmp_path / ".totp_secret_absent")
    yield
    totp_gate.reset_for_tests()
    totp_qr.reset_for_tests()
