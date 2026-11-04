from __future__ import annotations

import io
import json
import signal
from pathlib import Path
from urllib.error import URLError

import pytest

from app import dev_port

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_decide_port_action_start_replace_refuse():
    assert dev_port.decide_port_action([], None) == dev_port.START
    assert dev_port.decide_port_action([], "development") == dev_port.START
    assert (
        dev_port.decide_port_action([4242], "development") == dev_port.REPLACE
    )
    assert dev_port.decide_port_action([4242], None) == dev_port.REFUSE
    assert dev_port.decide_port_action([4242], "production") == dev_port.REFUSE
    assert dev_port.decide_port_action([4242], "staging") == dev_port.REFUSE


def test_parse_lsof_pids_skips_junk_and_pid_one():
    raw = "4242\n\n1\n4242\nnot-a-pid\n99\n"
    assert dev_port.parse_lsof_pids(raw) == [4242, 99]
    assert dev_port.parse_lsof_pids("") == []


def test_parse_health_env_accepts_spaced_json_and_rejects_garbage():
    body = json.dumps({"status": "ok", "env": "development"})
    assert dev_port.parse_health_env(body) == "development"
    assert dev_port.parse_health_env(b'{"env":"development"}') == "development"
    assert dev_port.parse_health_env(b'{"env": "production"}') == "production"
    assert dev_port.parse_health_env(b"not json") is None
    assert dev_port.parse_health_env(b"[]") is None
    assert dev_port.parse_health_env(b"{}") is None
    assert dev_port.parse_health_env(b'{"env": 1}') is None


def test_list_listener_pids_uses_lsof_listen_filter(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return type("Result", (), {"stdout": "111\n222\n", "stderr": "", "returncode": 0})()

    monkeypatch.setattr(dev_port.subprocess, "run", fake_run)
    assert dev_port.list_listener_pids(8099) == [111, 222]
    assert calls == [["lsof", "-nP", "-iTCP:8099", "-sTCP:LISTEN", "-t"]]


def test_list_listener_pids_missing_lsof_is_empty(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("lsof")

    monkeypatch.setattr(dev_port.subprocess, "run", fake_run)
    assert dev_port.list_listener_pids(8099) == []


def test_health_env_reads_url_and_swallows_network_errors(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"status":"ok","env":"development"}'

    monkeypatch.setattr(dev_port, "urlopen", lambda url, timeout=1.5: FakeResponse())
    assert dev_port.health_env("127.0.0.1", 8099) == "development"

    def boom(url, timeout=1.5):
        raise URLError("down")

    monkeypatch.setattr(dev_port, "urlopen", boom)
    assert dev_port.health_env("127.0.0.1", 8099) is None


def test_stop_pids_sigterm_then_sigkill_only_for_listed(monkeypatch):
    monkeypatch.setattr(dev_port.time, "monotonic", lambda: 0)
    sent: list[tuple[int, int]] = []
    alive = {10, 11, 999}

    def fake_kill(pid, sig):
        sent.append((pid, sig))
        if sig == signal.SIGKILL:
            alive.discard(pid)

    def fake_alive(pid):
        return pid in alive

    dev_port.stop_pids(
        [10, 11],
        term_wait=0,
        kill_wait=0,
        poll_interval=0,
        kill=fake_kill,
        sleep=lambda _s: None,
        alive=fake_alive,
    )
    assert (10, signal.SIGTERM) in sent
    assert (11, signal.SIGTERM) in sent
    assert (10, signal.SIGKILL) in sent
    assert (11, signal.SIGKILL) in sent
    assert all(pid != 999 for pid, _sig in sent)


def test_stop_pids_skips_sigkill_when_term_works():
    sent: list[tuple[int, int]] = []
    alive: set[int] = {50}

    def fake_kill(pid, sig):
        sent.append((pid, sig))
        if sig == signal.SIGTERM:
            alive.discard(pid)

    def fake_alive(pid):
        return pid in alive

    dev_port.stop_pids(
        [50],
        term_wait=0,
        kill_wait=0,
        poll_interval=0,
        kill=fake_kill,
        sleep=lambda _s: None,
        alive=fake_alive,
    )
    assert sent == [(50, signal.SIGTERM)]


def test_pids_to_signal_includes_uvicorn_parent_only(monkeypatch):
    monkeypatch.setattr(dev_port.os, "getpid", lambda: 7)
    monkeypatch.setattr(dev_port, "parent_pid", lambda pid: 300 if pid == 400 else None)
    monkeypatch.setattr(dev_port, "is_uvicorn_process", lambda pid: pid == 300)
    assert dev_port.pids_to_signal([400]) == [300, 400]

    monkeypatch.setattr(dev_port, "is_uvicorn_process", lambda pid: False)
    assert dev_port.pids_to_signal([400]) == [400]


def test_ensure_dev_port_free_when_empty(monkeypatch):
    monkeypatch.setattr(dev_port, "list_listener_pids", lambda port: [])
    monkeypatch.setattr(
        dev_port,
        "health_env",
        lambda host, port: pytest.fail("health must not run on a free port"),
    )
    monkeypatch.setattr(
        dev_port,
        "stop_pids",
        lambda pids, **kwargs: pytest.fail("must not kill on a free port"),
    )
    dev_port.ensure_dev_port_free("127.0.0.1", 8099)


def test_ensure_dev_port_free_replaces_development_listener(monkeypatch, capsys):
    stopped: list[list[int]] = []
    monkeypatch.setattr(dev_port, "list_listener_pids", lambda port: [4242])
    monkeypatch.setattr(dev_port, "health_env", lambda host, port: "development")
    monkeypatch.setattr(dev_port, "pids_to_signal", lambda pids: [4241, 4242])
    monkeypatch.setattr(dev_port, "stop_pids", lambda pids, **kwargs: stopped.append(list(pids)))
    monkeypatch.setattr(
        dev_port,
        "lsof_listing",
        lambda port: pytest.fail("replace must not print a foreign lsof listing"),
    )
    dev_port.ensure_dev_port_free("127.0.0.1", 8099)
    assert stopped == [[4241, 4242]]
    err = capsys.readouterr().err
    assert "Stopping previous development server on 127.0.0.1:8099" in err
    assert "4241" in err


def test_ensure_dev_port_free_refuses_foreign_and_does_not_kill(monkeypatch):
    monkeypatch.setattr(dev_port, "list_listener_pids", lambda port: [9999])
    monkeypatch.setattr(dev_port, "health_env", lambda host, port: None)
    monkeypatch.setattr(
        dev_port,
        "stop_pids",
        lambda pids, **kwargs: pytest.fail("must not kill a foreign listener"),
    )
    monkeypatch.setattr(dev_port, "lsof_listing", lambda port: "Python  9999 ... *:8099\n")
    with pytest.raises(dev_port.PortInUseError) as excinfo:
        dev_port.ensure_dev_port_free("127.0.0.1", 8099)
    assert excinfo.value.port == 8099
    assert "9999" in excinfo.value.lsof_output


def test_main_prints_lsof_and_exits_one_for_foreign_process(monkeypatch):
    monkeypatch.setenv("PORT", "8099")
    monkeypatch.setattr(dev_port, "list_listener_pids", lambda port: [77])
    monkeypatch.setattr(dev_port, "health_env", lambda host, port: "production")
    monkeypatch.setattr(
        dev_port,
        "stop_pids",
        lambda pids, **kwargs: pytest.fail("must not kill a foreign listener"),
    )
    monkeypatch.setattr(
        dev_port,
        "lsof_listing",
        lambda port: "COMMAND  PID\nnginx     77\n",
    )
    stderr = io.StringIO()
    monkeypatch.setattr(dev_port.sys, "stderr", stderr)
    assert dev_port.main() == 1
    text = stderr.getvalue()
    assert "Port 8099 is in use by another process." in text
    assert "nginx" in text
    assert "77" in text


def test_main_defaults_to_8099_and_succeeds_when_free(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    seen: list[tuple[str, int]] = []

    def fake_ensure(host, port):
        seen.append((host, port))

    monkeypatch.setattr(dev_port, "ensure_dev_port_free", fake_ensure)
    assert dev_port.main() == 0
    assert seen == [("127.0.0.1", 8099)]


def test_dev_sh_reclaims_port_before_uvicorn():
    script = (REPO_ROOT / "scripts" / "dev.sh").read_text(encoding="utf-8")
    reclaim_at = script.index("python -m app.dev_port")
    banner_at = script.index("Open this URL in Safari or Chrome on this Mac:")
    uvicorn_at = script.index("exec .venv/bin/uvicorn")
    assert reclaim_at < banner_at < uvicorn_at
    assert "http://127.0.0.1:${PORT:-8099}" in script
    assert "not reachable from Cursor Cloud" in script
    assert "127.0.0.1" in script
    assert "${PORT:-8099}" in script
    assert "--host 127.0.0.1" in script
    assert "--port" in script
    assert "load_openrouter_key" in script
    assert "--host 0.0.0.0" not in script


def test_dev_status_script_curls_loopback_health():
    script = (REPO_ROOT / "scripts" / "dev-status.sh").read_text(encoding="utf-8")
    assert "http://127.0.0.1:${PORT}/health" in script
    assert "nothing is listening" in script
    assert "OPENROUTER" not in script


def test_readme_says_second_dev_sh_replaces_own_server_only():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "replaces the previous development server on 8099" in readme
    assert "foreign process on that port is left alone" in readme
    assert "Open `http://127.0.0.1:8099` in Safari or Chrome on this MacBook itself." in readme
    assert "Cursor Cloud cannot load 127.0.0.1 on the laptop" in readme
    assert "bash scripts/dev-status.sh" in readme
    assert "lsof -nP -iTCP:8099 -sTCP:LISTEN" in readme


def test_production_port_stays_8000():
    example = (REPO_ROOT / ".env.production.example").read_text(encoding="utf-8")
    compose = (REPO_ROOT / "compose.prod.yaml").read_text(encoding="utf-8")
    assert "PORT=8000" in example
    assert "127.0.0.1:8000:8000" in compose
    assert "PORT=8099" not in example
