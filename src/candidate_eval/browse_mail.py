"""Safe local mailbox / folder browser for the Mac loopback UI.

Only paths under the user home directory or the project root may be listed.
"""

from __future__ import annotations

from pathlib import Path

from candidate_eval.service import project_root

# Skip noisy / VCS dirs when listing (Library is kept so Thunderbird is reachable).
_SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".Trash",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
}

# Thunderbird / Apple Mail-ish names often appear as extensionless mbox files.
_KNOWN_MBOX_NAMES = {
    "inbox",
    "sent",
    "sent mail",
    "drafts",
    "trash",
    "junk",
    "spam",
    "archives",
    "archive",
    "applications",
    "outbox",
    "templates",
}


def browse_roots() -> list[Path]:
    """Absolute roots the browser is allowed to traverse."""
    roots: list[Path] = []
    for raw in (Path.home(), project_root()):
        try:
            resolved = raw.expanduser().resolve()
        except OSError:
            continue
        if resolved not in roots:
            roots.append(resolved)
    return roots


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_allowed_path(path: Path) -> bool:
    """True if path resolves under home or project root."""
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False
    return any(_is_under(resolved, root) for root in browse_roots())


def resolve_browse_path(raw: str | None) -> Path:
    """Resolve a user/path query to an allowed absolute directory (or file's parent).

    Raises ValueError when the path escapes allowlisted roots.
    """
    text = (raw or "").strip()
    if not text:
        return default_browse_cwd()

    path = Path(text).expanduser()
    if not path.is_absolute():
        # Relative paths are project-relative (same as mail path resolution).
        path = project_root() / path

    try:
        resolved = path.resolve()
    except OSError as exc:
        raise ValueError(f"Cannot resolve path: {exc}") from exc

    if not is_allowed_path(resolved):
        raise ValueError(
            "Path is outside allowed browse roots (home directory and project root)."
        )

    if resolved.is_file():
        return resolved
    if resolved.is_dir():
        return resolved
    # Missing path: still allow navigating to parent if allowed, else reject.
    parent = resolved.parent
    if parent.is_dir() and is_allowed_path(parent):
        raise ValueError(f"Path not found: {resolved}")
    raise ValueError(f"Path not found: {resolved}")


def default_browse_cwd() -> Path:
    """Prefer demo fixtures, else Thunderbird Profiles, else project root, else home."""
    root = project_root()
    fixture = (root / "fixtures" / "mbox").resolve()
    if fixture.is_dir() and is_allowed_path(fixture):
        return fixture

    tb = (Path.home() / "Library" / "Thunderbird" / "Profiles").expanduser()
    try:
        tb_resolved = tb.resolve()
    except OSError:
        tb_resolved = None
    if tb_resolved and tb_resolved.is_dir() and is_allowed_path(tb_resolved):
        return tb_resolved

    if is_allowed_path(root):
        return root.resolve()
    return Path.home().resolve()


def shortcuts() -> list[dict]:
    """Named jump targets for the UI (only those that exist and are allowed)."""
    home = Path.home().resolve()
    root = project_root().resolve()
    candidates = [
        {"id": "home", "label": "Home", "path": str(home)},
        {
            "id": "thunderbird",
            "label": "Thunderbird Profiles",
            "path": str(home / "Library" / "Thunderbird" / "Profiles"),
        },
        {
            "id": "fixtures",
            "label": "Demo fixtures/mbox",
            "path": str(root / "fixtures" / "mbox"),
        },
        {"id": "project", "label": "Project root", "path": str(root)},
    ]
    out: list[dict] = []
    for item in candidates:
        p = Path(item["path"])
        try:
            resolved = p.expanduser().resolve()
        except OSError:
            continue
        if not resolved.exists():
            # Still advertise Thunderbird shortcut even if missing (UI can show disabled).
            if item["id"] != "thunderbird":
                continue
            item = {**item, "exists": False, "path": str(p)}
            out.append(item)
            continue
        if not is_allowed_path(resolved):
            continue
        out.append({**item, "exists": True, "path": str(resolved)})
    return out


def looks_like_mbox(path: Path) -> bool:
    """Heuristic: Thunderbird mbox files often have no extension."""
    if not path.is_file():
        return False
    name = path.name
    lower = name.lower()
    if lower.endswith(".mbox"):
        return True
    if "." in name and not lower.endswith(".msf"):
        # Has an extension (e.g. .eml, .txt) — usually not a classic mbox folder file.
        # Still allow .mbox handled above; skip obvious non-mail.
        if any(
            lower.endswith(ext)
            for ext in (".py", ".pyc", ".json", ".yaml", ".yml", ".md", ".html", ".js", ".css", ".png", ".jpg")
        ):
            return False
    if lower.endswith(".msf"):
        return False
    if lower in _KNOWN_MBOX_NAMES or name in {"INBOX", "Sent", "Drafts", "Trash", "Junk"}:
        return True
    # Extensionless file: sniff mbox "From " header.
    if "." not in name:
        try:
            with path.open("rb") as fh:
                head = fh.read(5)
            return head.startswith(b"From ")
        except OSError:
            return False
    return False


def list_mail_entries(cwd: Path) -> list[dict]:
    """List directories and mbox-like files under cwd (cwd must be an allowed dir)."""
    if not cwd.is_dir():
        raise ValueError(f"Not a directory: {cwd}")
    if not is_allowed_path(cwd):
        raise ValueError("Path is outside allowed browse roots.")

    entries: list[dict] = []
    try:
        children = sorted(cwd.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError as exc:
        raise ValueError(f"Permission denied: {cwd}") from exc

    for child in children:
        name = child.name
        if name.startswith("."):
            continue
        if child.is_dir():
            if name in _SKIP_DIR_NAMES:
                continue
            try:
                path_str = str(child.resolve())
            except OSError:
                continue
            if not is_allowed_path(child):
                continue
            entries.append(
                {
                    "name": name,
                    "path": path_str,
                    "type": "dir",
                    "is_mbox": False,
                }
            )
        elif child.is_file():
            if not looks_like_mbox(child):
                continue
            try:
                path_str = str(child.resolve())
            except OSError:
                continue
            if not is_allowed_path(child):
                continue
            entries.append(
                {
                    "name": name,
                    "path": path_str,
                    "type": "file",
                    "is_mbox": True,
                }
            )
    return entries


def parent_if_allowed(cwd: Path) -> str | None:
    parent = cwd.parent
    try:
        resolved = parent.resolve()
    except OSError:
        return None
    if resolved == cwd.resolve():
        return None
    if not is_allowed_path(resolved):
        return None
    return str(resolved)


def browse_mail(path: str | None = None) -> dict:
    """Build JSON payload for GET /api/browse-mail."""
    target = resolve_browse_path(path)
    if target.is_file():
        cwd = target.parent
        # Include the file context but list the parent directory.
        listing_cwd = cwd
    else:
        listing_cwd = target

    entries = list_mail_entries(listing_cwd)
    return {
        "cwd": str(listing_cwd.resolve()),
        "parent": parent_if_allowed(listing_cwd),
        "entries": entries,
        "shortcuts": shortcuts(),
        "roots": [str(r) for r in browse_roots()],
        "selected": str(target.resolve()) if target.is_file() else None,
    }
