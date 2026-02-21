from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any


VALID_MODES = {"manual", "roundtable", "orchestrator"}
DEFAULT_SESSION_AGENTS = [
    {
        "id": "researcher",
        "name": "Research Analyst",
        "model_alias": "deepseek",
        "role_prompt": "You extract facts and key points. Keep output concise and structured.",
    },
    {
        "id": "writer",
        "name": "Writer",
        "model_alias": "gpt_oss",
        "role_prompt": "You draft clear and polished responses from prior context.",
    },
    {
        "id": "reviewer",
        "name": "Reviewer",
        "model_alias": "qwen",
        "role_prompt": "You quality-check outputs and provide a final recommendation.",
    },
]


class SqlMemory:
    def __init__(self, db_path: str = "data/pantheon_memory.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    current_mode TEXT NOT NULL,
                    pending_mode TEXT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    agent_name TEXT NULL,
                    mode TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS turn_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    model_alias TEXT NOT NULL,
                    output_text TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS session_agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    model_alias TEXT NOT NULL,
                    role_prompt TEXT NOT NULL,
                    position INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO settings(key, value)
                VALUES('orchestrator_manager_alias', 'deepseek')
                """
            )
            conn.commit()

    def create_session(self, mode: str = "roundtable") -> dict[str, Any]:
        if mode not in VALID_MODES:
            raise ValueError(f"Unsupported mode '{mode}'")
        session_id = str(uuid.uuid4())
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions(id, current_mode, pending_mode) VALUES (?, ?, NULL)",
                (session_id, mode),
            )
            for idx, agent in enumerate(DEFAULT_SESSION_AGENTS, start=1):
                conn.execute(
                    """
                    INSERT INTO session_agents(session_id, agent_id, name, model_alias, role_prompt, position)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        agent["id"],
                        agent["name"],
                        agent["model_alias"],
                        agent["role_prompt"],
                        idx,
                    ),
                )
            conn.commit()
        return {"session_id": session_id, "current_mode": mode, "pending_mode": None}

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, created_at, current_mode, pending_mode FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def set_pending_mode(self, session_id: str, mode: str) -> None:
        if mode not in VALID_MODES:
            raise ValueError(f"Unsupported mode '{mode}'")
        with self._conn() as conn:
            conn.execute(
                "UPDATE sessions SET pending_mode = ? WHERE id = ?",
                (mode, session_id),
            )
            conn.commit()

    def resolve_mode_for_turn(self, session_id: str) -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT current_mode, pending_mode FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Session not found")
            current_mode = row["current_mode"]
            pending_mode = row["pending_mode"]
            if pending_mode:
                conn.execute(
                    "UPDATE sessions SET current_mode = ?, pending_mode = NULL WHERE id = ?",
                    (pending_mode, session_id),
                )
                conn.commit()
                return pending_mode
            return current_mode

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        mode: str,
        agent_name: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO messages(session_id, role, agent_name, mode, content)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, agent_name, mode, content),
            )
            conn.commit()

    def get_messages(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, role, agent_name, mode, content, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def add_turn_steps(
        self,
        session_id: str,
        request_id: str,
        mode: str,
        steps: list[dict[str, str]],
    ) -> None:
        with self._conn() as conn:
            for i, step in enumerate(steps, start=1):
                conn.execute(
                    """
                    INSERT INTO turn_steps(session_id, request_id, step_index, mode, agent_name, model_alias, output_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        request_id,
                        i,
                        mode,
                        step["agent_name"],
                        step["model_alias"],
                        step["output_text"],
                    ),
                )
            conn.commit()

    def get_agents(self, session_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT agent_id AS id, name, model_alias, role_prompt, position
                FROM session_agents
                WHERE session_id = ?
                ORDER BY position ASC, id ASC
                """,
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def replace_agents(self, session_id: str, agents: list[dict[str, str]]) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM session_agents WHERE session_id = ?", (session_id,))
            for idx, agent in enumerate(agents, start=1):
                conn.execute(
                    """
                    INSERT INTO session_agents(session_id, agent_id, name, model_alias, role_prompt, position)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        agent["id"],
                        agent["name"],
                        agent["model_alias"],
                        agent["role_prompt"],
                        idx,
                    ),
                )
            conn.commit()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return row["value"]

    def set_setting(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO settings(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            conn.commit()
