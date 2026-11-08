"""SQLite 持久化层。

单文件数据库，默认为项目根下的 buglens.db，可用 BUGLENS_DB 覆盖。
全部使用标准库 sqlite3，不引入 ORM。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .models import (
    Bug,
    ChecklistItem,
    HistoryEntry,
    now_iso,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS bugs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    module      TEXT NOT NULL,
    severity    TEXT NOT NULL,
    status      TEXT NOT NULL,
    reporter    TEXT NOT NULL,
    env         TEXT NOT NULL,
    steps       TEXT NOT NULL,
    actual      TEXT NOT NULL,
    expected    TEXT NOT NULL,
    assignee    TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bug_id      INTEGER NOT NULL REFERENCES bugs(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status   TEXT NOT NULL,
    actor       TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checklist (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    release     TEXT NOT NULL,
    item        TEXT NOT NULL,
    done        INTEGER NOT NULL DEFAULT 0,
    owner       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bugs_status   ON bugs(status);
CREATE INDEX IF NOT EXISTS idx_bugs_severity ON bugs(severity);
CREATE INDEX IF NOT EXISTS idx_bugs_module   ON bugs(module);
CREATE INDEX IF NOT EXISTS idx_history_bug   ON history(bug_id);
CREATE INDEX IF NOT EXISTS idx_check_release ON checklist(release);
"""


def default_db_path() -> Path:
    """数据库路径优先级：环境变量 > 当前目录 buglens.db。"""
    env = os.environ.get("BUGLENS_DB")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd() / "buglens.db"


class Store:
    """所有读写都走这里，CLI 层不直接碰 sqlite。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- 生命周期 ----------

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---------- 缺陷 ----------

    def add_bug(self, bug: Bug, actor: str = "", note: str = "") -> int:
        """写入缺陷并记一条 new 的历史。"""
        ts = now_iso()
        cur = self.conn.execute(
            """INSERT INTO bugs
               (title, module, severity, status, reporter, env, steps,
                actual, expected, assignee, tags, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                bug.title, bug.module, bug.severity, bug.status or "new",
                bug.reporter, bug.env, bug.steps, bug.actual, bug.expected,
                bug.assignee, bug.tags, ts, ts,
            ),
        )
        bug_id = int(cur.lastrowid)
        self.conn.execute(
            """INSERT INTO history (bug_id, from_status, to_status, actor, note, at)
               VALUES (?,?,?,?,?,?)""",
            (bug_id, None, bug.status or "new", actor or bug.reporter, note or "创建", ts),
        )
        self.conn.commit()
        return bug_id

    def get_bug(self, bug_id: int) -> Bug | None:
        row = self.conn.execute("SELECT * FROM bugs WHERE id = ?", (bug_id,)).fetchone()
        return Bug.from_row(row) if row else None

    def list_bugs(
        self,
        status: str | None = None,
        severity: str | None = None,
        module: str | None = None,
        assignee: str | None = None,
        tag: str | None = None,
        keyword: str | None = None,
        limit: int | None = None,
    ) -> list[Bug]:
        """多条件组合过滤。参数均为 None 时返回全部。"""
        sql = "SELECT * FROM bugs WHERE 1=1"
        params: list[Any] = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if severity:
            sql += " AND severity = ?"
            params.append(severity.upper())
        if module:
            sql += " AND module = ?"
            params.append(module)
        if assignee:
            sql += " AND assignee = ?"
            params.append(assignee)
        if tag:
            sql += " AND (',' || tags || ',') LIKE ?"
            params.append(f"%,{tag},%")
        if keyword:
            sql += " AND (title LIKE ? OR steps LIKE ? OR actual LIKE ? OR expected LIKE ?)"
            like = f"%{keyword}%"
            params.extend([like, like, like, like])
        sql += " ORDER BY CASE severity WHEN 'S1' THEN 1 WHEN 'S2' THEN 2" \
               " WHEN 'S3' THEN 3 ELSE 4 END, id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return [Bug.from_row(r) for r in self.conn.execute(sql, params).fetchall()]

    def update_status(
        self, bug_id: int, to_status: str, actor: str, note: str = ""
    ) -> tuple[str, str]:
        """更新状态并留痕，返回 (旧状态, 新状态)。合法性由调用方保证。"""
        bug = self.get_bug(bug_id)
        if bug is None:
            raise KeyError(f"缺陷 #{bug_id} 不存在")
        old = bug.status
        ts = now_iso()
        self.conn.execute(
            "UPDATE bugs SET status = ?, updated_at = ? WHERE id = ?",
            (to_status, ts, bug_id),
        )
        self.conn.execute(
            """INSERT INTO history (bug_id, from_status, to_status, actor, note, at)
               VALUES (?,?,?,?,?,?)""",
            (bug_id, old, to_status, actor, note, ts),
        )
        self.conn.commit()
        return old, to_status

    def assign(self, bug_id: int, assignee: str) -> None:
        self.conn.execute(
            "UPDATE bugs SET assignee = ?, updated_at = ? WHERE id = ?",
            (assignee, now_iso(), bug_id),
        )
        self.conn.commit()

    def delete_bug(self, bug_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM bugs WHERE id = ?", (bug_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def history(self, bug_id: int) -> list[HistoryEntry]:
        rows = self.conn.execute(
            "SELECT * FROM history WHERE bug_id = ? ORDER BY id", (bug_id,)
        ).fetchall()
        return [
            HistoryEntry(
                id=r["id"], bug_id=r["bug_id"], from_status=r["from_status"],
                to_status=r["to_status"], actor=r["actor"], note=r["note"], at=r["at"],
            )
            for r in rows
        ]

    # ---------- 验收清单 ----------

    def add_check(self, release: str, item: str, owner: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO checklist (release, item, done, owner, created_at) VALUES (?,?,0,?,?)",
            (release, item, owner, now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_checks(self, release: str) -> list[ChecklistItem]:
        rows = self.conn.execute(
            "SELECT * FROM checklist WHERE release = ? ORDER BY id", (release,)
        ).fetchall()
        return [
            ChecklistItem(
                id=r["id"], release=r["release"], item=r["item"],
                done=bool(r["done"]), owner=r["owner"], created_at=r["created_at"],
            )
            for r in rows
        ]

    def check_item(self, check_id: int, done: bool = True) -> bool:
        cur = self.conn.execute(
            "UPDATE checklist SET done = ? WHERE id = ?", (1 if done else 0, check_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def releases(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT release FROM checklist ORDER BY release DESC"
        ).fetchall()
        return [r["release"] for r in rows]

    def check_progress(self, release: str) -> tuple[int, int]:
        """返回 (已完成, 总数)。"""
        row = self.conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(done),0) AS done "
            "FROM checklist WHERE release = ?",
            (release,),
        ).fetchone()
        return int(row["done"]), int(row["total"])

    # ---------- 维护 ----------

    def counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM bugs GROUP BY status"
        ).fetchall()
        return {r["status"]: int(r["n"]) for r in rows}

    def modules(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT module FROM bugs ORDER BY module"
        ).fetchall()
        return [r["module"] for r in rows]

    def bulk_insert(self, bugs: Iterable[Bug], actor: str = "import") -> int:
        n = 0
        for bug in bugs:
            self.add_bug(bug, actor=actor, note="批量导入")
            n += 1
        return n

    def reset(self) -> None:
        self.conn.executescript(
            "DELETE FROM history; DELETE FROM bugs; DELETE FROM checklist;"
        )
        self.conn.execute("DELETE FROM sqlite_sequence")
        self.conn.commit()
