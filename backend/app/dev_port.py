"""Free the Mac development port before uvicorn starts.

A previous copy of this app (GET /health JSON env == \"development\") is stopped.
A foreign listener on the same port is left alone.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

START = "start"
REPLACE = "replace"
REFUSE = "refuse"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8099
HEALTH_TIMEOUT_SECONDS = 1.5
TERM_WAIT_SECONDS = 2.0
KILL_WAIT_SECONDS = 0.5
POLL_INTERVAL_SECONDS = 0.05


class PortInUseError(RuntimeError):
    def __init__(self, port: int, lsof_output: str = "") -> None:
        self.port = port
        self.lsof_output = lsof_output
        super().__init__(f"Port {port} is in use by another process.")


def decide_port_action(listener_pids: list[int], health_env: str | None) -> str:
    """Choose start / replace / refuse from lsof pids and GET /health env."""
    if not listener_pids:
        return START
    if health_env == "development":
        return REPLACE
    return REFUSE


def parse_lsof_pids(output: str) -> list[int]:
    """Parse `lsof -t` stdout into unique positive PIDs, in order."""
    seen: set[int] = set()
    pids: list[int] = []
    for line in output.splitlines():
        token = line.strip()
        if not token.isdigit():
            continue
        pid = int(token)
        if pid <= 1 or pid in seen:
            continue
        seen.add(pid)
        pids.append(pid)
    return pids


def parse_health_env(body: bytes | str) -> str | None:
    """Return the JSON env field from a /health body, else None."""
    if isinstance(body, bytes):
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return None
    else:
        text = body
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    env = data.get("env")
    if isinstance(env, str) and env:
        return env
    return None


def list_listener_pids(port: int) -> list[int]:
    """PIDs in TCP LISTEN on port, via lsof. Missing lsof or no match → []."""
    try:
        completed = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    return parse_lsof_pids(completed.stdout)


def lsof_listing(port: int) -> str:
    try:
        completed = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return "lsof is not installed\n"
    return completed.stdout or completed.stderr


def health_env(host: str, port: int, timeout: float = HEALTH_TIMEOUT_SECONDS) -> str | None:
    url = f"http://{host}:{port}/health"
    try:
        with urlopen(url, timeout=timeout) as response:
            body = response.read()
    except (URLError, HTTPError, TimeoutError, OSError):
        return None
    return parse_health_env(body)


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_field(pid: int, field: str) -> str:
    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", f"{field}="],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def parent_pid(pid: int) -> int | None:
    raw = _process_field(pid, "ppid")
    if not raw.isdigit():
        return None
    ppid = int(raw)
    if ppid <= 1:
        return None
    return ppid


def is_uvicorn_process(pid: int) -> bool:
    args = _process_field(pid, "args")
    return "uvicorn" in args


def pids_to_signal(listen_pids: list[int]) -> list[int]:
    """LISTEN pids, plus a uvicorn parent so --reload cannot respawn the worker.

    Never includes PID 1 or this process. Does not kill by name or all Python.
    """
    our_pid = os.getpid()
    selected: list[int] = []
    seen: set[int] = set()

    def add(pid: int) -> None:
        if pid <= 1 or pid == our_pid or pid in seen:
            return
        seen.add(pid)
        selected.append(pid)

    for pid in listen_pids:
        ppid = parent_pid(pid)
        if ppid is not None and is_uvicorn_process(ppid):
            add(ppid)
        add(pid)
    return selected


def stop_pids(
    pids: list[int],
    *,
    term_wait: float = TERM_WAIT_SECONDS,
    kill_wait: float = KILL_WAIT_SECONDS,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    kill: Callable[[int, int], None] = os.kill,
    sleep: Callable[[float], None] = time.sleep,
    alive: Callable[[int], bool] | None = None,
) -> None:
    """SIGTERM each pid, wait briefly, SIGKILL whoever is still alive."""
    is_alive = alive or _pid_is_alive
    remaining = [pid for pid in pids if pid > 1]
    for pid in remaining:
        try:
            kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError:
            continue

    deadline = time.monotonic() + term_wait
    while remaining and time.monotonic() < deadline:
        remaining = [pid for pid in remaining if is_alive(pid)]
        if remaining:
            sleep(poll_interval)

    remaining = [pid for pid in remaining if is_alive(pid)]
    for pid in remaining:
        try:
            kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            continue
        except PermissionError:
            continue

    deadline = time.monotonic() + kill_wait
    while remaining and time.monotonic() < deadline:
        remaining = [pid for pid in remaining if is_alive(pid)]
        if remaining:
            sleep(poll_interval)


def ensure_dev_port_free(host: str, port: int) -> None:
    """Replace our previous development server, or refuse a foreign listener."""
    listener_pids = list_listener_pids(port)
    env = health_env(host, port) if listener_pids else None
    action = decide_port_action(listener_pids, env)
    if action == START:
        return
    if action == REPLACE:
        targets = pids_to_signal(listener_pids)
        pid_list = ", ".join(str(pid) for pid in targets) or "unknown"
        print(
            f"Stopping previous development server on {host}:{port} (pid {pid_list})",
            file=sys.stderr,
        )
        stop_pids(targets)
        return
    raise PortInUseError(port, lsof_listing(port))


def main() -> int:
    raw_port = os.environ.get("PORT") or str(DEFAULT_PORT)
    try:
        port = int(raw_port)
    except ValueError:
        print(f"PORT={raw_port!r} is not an integer.", file=sys.stderr)
        return 1
    host = DEFAULT_HOST
    try:
        ensure_dev_port_free(host, port)
    except PortInUseError as exc:
        print(f"Port {exc.port} is in use by another process.", file=sys.stderr)
        listing = (exc.lsof_output or "").rstrip()
        if listing:
            print(listing, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
