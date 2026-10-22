"""Safe local mailbox / folder browser for the Mac loopback UI.

Only paths under the user home directory or the project root may be listed.
Optimized for browsing Thunderbird mail trees on a MacBook.
"""

from __future__ import annotations

import platform
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
    """Resolve a user/path query to an allowed absolute directory (or file).

    Raises ValueError when the path escapes allowlisted roots.
    """
    text = (raw or "").strip()
    # mailbox:// URIs are not filesystem paths — fall back to Mac defaults.
    if not text or text.lower().startswith("mailbox:"):
        return default_browse_cwd()

    path = Path(text).expanduser()
    if not path.is_absolute():
        path = project_root() / path

    try:
        resolved = path.resolve()
    except OSError as exc:
        raise ValueError(f"Cannot resolve path: {exc}") from exc

    if not is_allowed_path(resolved):
        raise ValueError(
            "Path is outside allowed browse roots (your Mac home and this project)."
        )

    if resolved.is_file() or resolved.is_dir():
        return resolved
    parent = resolved.parent
    if parent.is_dir() and is_allowed_path(parent):
        raise ValueError(f"Path not found: {resolved}")
    raise ValueError(f"Path not found: {resolved}")


def _thunderbird_profiles_dir() -> Path | None:
    home = Path.home()
    candidates = [
        home / "Library" / "Thunderbird" / "Profiles",  # macOS
        home / ".thunderbird",  # Linux
        home / "AppData" / "Roaming" / "Thunderbird" / "Profiles",  # Windows
    ]
    for cand in candidates:
        try:
            resolved = cand.expanduser().resolve()
        except OSError:
            continue
        if resolved.is_dir() and is_allowed_path(resolved):
            return resolved
    return None


def _discover_thunderbird_mail_dirs() -> list[dict]:
    """Find Mail / ImapMail dirs under each Thunderbird profile."""
    profiles = _thunderbird_profiles_dir()
    if not profiles:
        return []
    found: list[dict] = []
    try:
        profile_dirs = [p for p in profiles.iterdir() if p.is_dir() and not p.name.startswith(".")]
    except OSError:
        return []
    for profile in sorted(profile_dirs, key=lambda p: p.name.lower()):
        for sub in ("Mail", "ImapMail"):
            mail_root = profile / sub
            if not mail_root.is_dir():
                continue
            try:
                resolved = mail_root.resolve()
            except OSError:
                continue
            if not is_allowed_path(resolved):
                continue
            label = f"TB {profile.name[:18]}…/{sub}" if len(profile.name) > 18 else f"TB {profile.name}/{sub}"
            found.append(
                {
                    "id": f"tb-{profile.name}-{sub}".lower(),
                    "label": label,
                    "path": str(resolved),
                    "exists": True,
                }
            )
            # Also shortcut each account folder one level down (e.g. Local Folders).
            try:
                for account in sorted(mail_root.iterdir(), key=lambda p: p.name.lower()):
                    if not account.is_dir() or account.name.startswith("."):
                        continue
                    acc_resolved = account.resolve()
                    if not is_allowed_path(acc_resolved):
                        continue
                    found.append(
                        {
                            "id": f"tb-acc-{profile.name}-{sub}-{account.name}".lower()[:80],
                            "label": f"{account.name}",
                            "path": str(acc_resolved),
                            "exists": True,
                        }
                    )
            except OSError:
                continue
    return found[:24]  # keep shortcut bar usable


def default_browse_cwd() -> Path:
    """Prefer Thunderbird mail on Mac, else demo fixtures, else home."""
    # On macOS (and when TB profiles exist), open near real mail first.
    tb_mail = _discover_thunderbird_mail_dirs()
    if tb_mail:
        return Path(tb_mail[0]["path"])

    tb = _thunderbird_profiles_dir()
    if tb:
        return tb

    root = project_root()
    fixture = (root / "fixtures" / "mbox").resolve()
    if fixture.is_dir() and is_allowed_path(fixture):
        return fixture

    if is_allowed_path(root):
        return root.resolve()
    return Path.home().resolve()


def shortcuts() -> list[dict]:
    """Named jump targets for the UI (Mac home + Thunderbird + project)."""
    home = Path.home().resolve()
    root = project_root().resolve()
    candidates: list[dict] = [
        {"id": "home", "label": "Home", "path": str(home)},
        {"id": "desktop", "label": "Desktop", "path": str(home / "Desktop")},
        {"id": "documents", "label": "Documents", "path": str(home / "Documents")},
        {"id": "downloads", "label": "Downloads", "path": str(home / "Downloads")},
    ]

    tb = _thunderbird_profiles_dir()
    candidates.append(
        {
            "id": "thunderbird",
            "label": "Thunderbird Profiles",
            "path": str(tb) if tb else str(home / "Library" / "Thunderbird" / "Profiles"),
        }
    )
    candidates.extend(_discover_thunderbird_mail_dirs())

    candidates.append(
        {
            "id": "fixtures",
            "label": "Demo fixtures/mbox",
            "path": str(root / "fixtures" / "mbox"),
        }
    )
    candidates.append({"id": "project", "label": "Project root", "path": str(root)})

    # Deduplicate by path while preserving order.
    seen: set[str] = set()
    out: list[dict] = []
    for item in candidates:
        p = Path(item["path"])
        try:
            resolved = p.expanduser().resolve()
            path_key = str(resolved)
        except OSError:
            path_key = str(p)
            resolved = None

        if path_key in seen:
            continue

        if resolved is None or not resolved.exists():
            if item["id"] in {"thunderbird"}:
                seen.add(path_key)
                out.append({**item, "exists": False, "path": str(p)})
            continue
        if not is_allowed_path(resolved):
            continue
        seen.add(path_key)
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
    if lower.endswith(".msf"):
        return False
    if any(
        lower.endswith(ext)
        for ext in (
            ".py",
            ".pyc",
            ".json",
            ".yaml",
            ".yml",
            ".md",
            ".html",
            ".js",
            ".css",
            ".png",
            ".jpg",
            ".sqlite",
            ".db",
            ".log",
            ".ini",
            ".jsonlz4",
        )
    ):
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


def list_mail_entries(cwd: Path, *, show_all_files: bool = False) -> list[dict]:
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
            kind = "dir"
            # Thunderbird nested folder packs end with .sbd
            label_extra = " (folders)" if name.endswith(".sbd") else ""
            entries.append(
                {
                    "name": name + label_extra,
                    "path": path_str,
                    "type": kind,
                    "is_mbox": False,
                }
            )
        elif child.is_file():
            is_mbox = looks_like_mbox(child)
            if not is_mbox and not show_all_files:
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
                    "is_mbox": is_mbox,
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


def browse_mail(path: str | None = None, *, show_all_files: bool = False) -> dict:
    """Build JSON payload for GET /api/browse-mail."""
    target = resolve_browse_path(path)
    listing_cwd = target.parent if target.is_file() else target

    entries = list_mail_entries(listing_cwd, show_all_files=show_all_files)
    return {
        "cwd": str(listing_cwd.resolve()),
        "parent": parent_if_allowed(listing_cwd),
        "entries": entries,
        "shortcuts": shortcuts(),
        "roots": [str(r) for r in browse_roots()],
        "selected": str(target.resolve()) if target.is_file() else None,
        "platform": platform.system(),
        "hint": (
            "Browse folders on this Mac. Open a Thunderbird Mail/ImapMail account, "
            "then select an mbox file (e.g. Inbox) or use the current folder."
        ),
    }
