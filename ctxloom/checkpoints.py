from __future__ import annotations

import json
import sqlite3
import urllib.parse
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, cast


class CheckpointBackend(ABC):
    """Interface for saving and loading the Workspace state."""

    @abstractmethod
    def save(self, data: dict[str, Any]) -> None:
        """Saves the state dictionary."""
        ...

    @abstractmethod
    def load(self) -> dict[str, Any]:
        """Loads the state dictionary."""
        ...


class KVBackend(ABC):
    """Key-value store. Used for sessions (session_id → Context)."""

    @abstractmethod
    def set(self, key: str, data: dict[str, Any]) -> None: ...

    @abstractmethod
    def get(self, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def keys(self) -> list[str]: ...


class FileKVBackend(KVBackend):
    """File KV backend: one JSON file per key in a directory."""

    def __init__(self, directory: str):
        self.directory = Path(directory)

    def _path(self, key: str) -> Path:
        safe = urllib.parse.quote(key, safe="")
        return self.directory / f"{safe}.json"

    def set(self, key: str, data: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"key": key, "data": data}, f)
        tmp.replace(path)

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return cast(dict[str, Any] | None, json.load(f).get("data"))

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def keys(self) -> list[str]:
        self.directory.mkdir(parents=True, exist_ok=True)
        return [
            urllib.parse.unquote(p.stem) for p in sorted(self.directory.glob("*.json"))
        ]


class SQLiteKVBackend(KVBackend):
    """SQLite KV backend: table kv_entries(key PRIMARY KEY, data JSON)."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kv_entries (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
            """)
        conn.commit()
        conn.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def set(self, key: str, data: dict[str, Any]) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT OR REPLACE INTO kv_entries (key, data) VALUES (?, ?)",
            (key, json.dumps(data)),
        )
        conn.commit()
        conn.close()

    def get(self, key: str) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT data FROM kv_entries WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
        return cast(dict[str, Any], json.loads(row[0])) if row is not None else None

    def delete(self, key: str) -> None:
        conn = self._connect()
        conn.execute("DELETE FROM kv_entries WHERE key = ?", (key,))
        conn.commit()
        conn.close()

    def keys(self) -> list[str]:
        conn = self._connect()
        rows = conn.execute("SELECT key FROM kv_entries").fetchall()
        conn.close()
        return [r[0] for r in rows]


class FileBackend(CheckpointBackend):
    """File backend: state is stored in a JSON file."""

    def __init__(self, path: str):
        self.path = path

    def save(self, data: dict[str, Any]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self) -> dict[str, Any]:
        with open(self.path, encoding="utf-8") as f:
            return cast(dict[str, Any], json.load(f))


class SQLiteBackend(CheckpointBackend):
    """SQLite backend: state is stored in the checkpoint table (single row)."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoint (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL
            )
            """)
        conn.commit()
        conn.close()

    def save(self, data: dict[str, Any]) -> None:
        json_data = json.dumps(data)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO checkpoint (id, data) VALUES (1, ?)",
            (json_data,),
        )
        conn.commit()
        conn.close()

    def load(self) -> dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT data FROM checkpoint WHERE id = 1").fetchone()
        conn.close()
        if row is None:
            raise ValueError("Checkpoint not found in SQLite database")
        return cast(dict[str, Any], json.loads(row[0]))
