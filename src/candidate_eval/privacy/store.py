"""SQLite store for sensitive candidate fields that must not leave the Mac."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalCandidateStore:
    """Local-only database for PII and full message bodies."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> LocalCandidateStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
              run_id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL,
              keywords_json TEXT NOT NULL,
              mbox_path TEXT,
              db_path TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS candidates (
              candidate_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              message_id TEXT,
              email_hash TEXT,
              name TEXT,
              email TEXT,
              phone TEXT,
              linkedin TEXT,
              address TEXT,
              subject TEXT,
              raw_headers_json TEXT,
              raw_body TEXT,
              allowed_payload_json TEXT,
              scorecard_json TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS redactions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              candidate_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              original TEXT NOT NULL,
              placeholder TEXT NOT NULL,
              FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id)
            );

            CREATE INDEX IF NOT EXISTS idx_candidates_run ON candidates(run_id);
            """
        )
        self._conn.commit()

    def create_run(
        self,
        run_id: str,
        *,
        keywords: list[str],
        mbox_path: str | None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO runs (run_id, created_at, keywords_json, mbox_path, db_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, _utc_now(), json.dumps(keywords), mbox_path, str(self.db_path)),
        )
        self._conn.commit()

    def upsert_candidate(
        self,
        *,
        candidate_id: str,
        run_id: str,
        message_id: str | None,
        email_hash: str,
        sensitive: dict[str, Any],
        subject: str | None,
        raw_headers: dict[str, Any],
        raw_body: str,
        allowed_payload: dict[str, Any],
        redactions: list[dict[str, str]],
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO candidates (
              candidate_id, run_id, message_id, email_hash,
              name, email, phone, linkedin, address, subject,
              raw_headers_json, raw_body, allowed_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id) DO UPDATE SET
              run_id=excluded.run_id,
              message_id=excluded.message_id,
              email_hash=excluded.email_hash,
              name=excluded.name,
              email=excluded.email,
              phone=excluded.phone,
              linkedin=excluded.linkedin,
              address=excluded.address,
              subject=excluded.subject,
              raw_headers_json=excluded.raw_headers_json,
              raw_body=excluded.raw_body,
              allowed_payload_json=excluded.allowed_payload_json
            """,
            (
                candidate_id,
                run_id,
                message_id,
                email_hash,
                sensitive.get("name"),
                sensitive.get("email"),
                sensitive.get("phone"),
                sensitive.get("linkedin"),
                sensitive.get("address"),
                subject,
                json.dumps(raw_headers),
                raw_body,
                json.dumps(allowed_payload),
                _utc_now(),
            ),
        )
        self._conn.execute(
            "DELETE FROM redactions WHERE candidate_id = ?", (candidate_id,)
        )
        for item in redactions:
            self._conn.execute(
                """
                INSERT INTO redactions (candidate_id, kind, original, placeholder)
                VALUES (?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    item["kind"],
                    item["original"],
                    item["placeholder"],
                ),
            )
        self._conn.commit()

    def save_scorecard(self, candidate_id: str, scorecard: dict[str, Any]) -> None:
        self._conn.execute(
            "UPDATE candidates SET scorecard_json = ? WHERE candidate_id = ?",
            (json.dumps(scorecard), candidate_id),
        )
        self._conn.commit()

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_candidates(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM candidates WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def summary(self, run_id: str) -> dict[str, Any]:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS n,
                   SUM(CASE WHEN scorecard_json IS NOT NULL THEN 1 ELSE 0 END) AS scored
            FROM candidates WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        redaction_count = self._conn.execute(
            """
            SELECT COUNT(*) AS n FROM redactions
            WHERE candidate_id IN (SELECT candidate_id FROM candidates WHERE run_id = ?)
            """,
            (run_id,),
        ).fetchone()["n"]
        return {
            "run_id": run_id,
            "candidate_count": int(row["n"] or 0),
            "scored_count": int(row["scored"] or 0),
            "redaction_count": int(redaction_count or 0),
            "db_path": str(self.db_path),
        }
