"""Local SQLite store for progress, assessments, preferences, bookmarks and mistakes.

All data stays on this computer. FinPilot collects no telemetry and needs no
account. The database is checked for integrity on open; a damaged file is set
aside (never deleted) and a fresh one is created, and the caller is told.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import shutil
import sqlite3
import zipfile
from pathlib import Path
from typing import Any, Iterable, Optional

from .. import __version__
from ..config import backups_dir, data_dir

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lesson_progress (
    lesson_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'in_progress',
    step_index INTEGER NOT NULL DEFAULT 0,
    best_score REAL,
    last_score REAL,
    attempts INTEGER NOT NULL DEFAULT 0,
    mode TEXT,
    started_at TEXT, completed_at TEXT);
CREATE TABLE IF NOT EXISTS step_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id TEXT NOT NULL, item_id TEXT NOT NULL, step_type TEXT NOT NULL,
    correct INTEGER NOT NULL, score REAL NOT NULL, attempts INTEGER NOT NULL,
    hints_used INTEGER NOT NULL DEFAULT 0, ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL, ref TEXT, score REAL NOT NULL, passed INTEGER NOT NULL,
    details TEXT, ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS xp_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount INTEGER NOT NULL, reason TEXT NOT NULL, ref TEXT NOT NULL, ts TEXT NOT NULL,
    UNIQUE(reason, ref));
CREATE TABLE IF NOT EXISTS badges (id TEXT PRIMARY KEY, earned_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL, ref TEXT NOT NULL, title TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(kind, ref));
CREATE TABLE IF NOT EXISTS mistakes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref TEXT NOT NULL, lesson_id TEXT, skill TEXT, question TEXT NOT NULL,
    your_answer TEXT, expected TEXT, explanation TEXT,
    created_at TEXT NOT NULL, next_review TEXT NOT NULL,
    interval_days INTEGER NOT NULL DEFAULT 1, streak INTEGER NOT NULL DEFAULT 0,
    reviews INTEGER NOT NULL DEFAULT 0, resolved INTEGER NOT NULL DEFAULT 0,
    UNIQUE(ref));
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, path TEXT NOT NULL UNIQUE, kind TEXT NOT NULL,
    updated_at TEXT NOT NULL, validated INTEGER NOT NULL DEFAULT 0, progress REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS skill_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill TEXT NOT NULL, source TEXT NOT NULL, score REAL NOT NULL, weight REAL NOT NULL, ts TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_evidence_skill ON skill_evidence(skill);
CREATE INDEX IF NOT EXISTS ix_steps_lesson ON step_results(lesson_id);
"""

DEFAULT_SETTINGS = {
    "learner_name": "",
    "onboarded": False,
    "theme": "light",
    "practice_mode": "guided",        # guided | practice | challenge
    "gamification": True,
    "daily_goal_xp": 0,               # 0 = off (optional goal, no streaks)
    "currency_symbol": "$",
    "unlock_all": False,
    "autosave": True,
    "reduce_motion": False,
}

REVIEW_INTERVALS = [1, 3, 7, 14, 30]


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else data_dir() / "finpilot.db"
        self.recovered_from: Optional[Path] = None
        self.conn = self._open()

    # ------------------------------------------------------------ lifecycle

    def _open(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and not self._healthy(self.path):
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            aside = self.path.with_name(f"finpilot.corrupt-{stamp}.db")
            shutil.move(str(self.path), str(aside))
            self.recovered_from = aside
            log.error("Database failed integrity check; moved to %s", aside)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)
        cur = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if cur is None:
            conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
            conn.execute("INSERT INTO meta(key, value) VALUES('created_with', ?)", (__version__,))
        conn.commit()
        return conn

    @staticmethod
    def _healthy(path: Path) -> bool:
        try:
            c = sqlite3.connect(path)
            ok = c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            c.execute("SELECT count(*) FROM sqlite_master").fetchone()
            c.close()
            return ok
        except sqlite3.DatabaseError:
            return False

    def integrity_ok(self) -> bool:
        try:
            return self.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        except sqlite3.DatabaseError:
            return False

    def close(self) -> None:
        self.conn.close()

    def _exec(self, sql: str, params: Iterable = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, tuple(params))
        self.conn.commit()
        return cur

    # ------------------------------------------------------------- settings

    def get_setting(self, key: str) -> Any:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row is None:
            return DEFAULT_SETTINGS.get(key)
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return DEFAULT_SETTINGS.get(key)

    def set_setting(self, key: str, value: Any) -> None:
        self._exec("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, json.dumps(value)))

    def settings(self) -> dict:
        out = dict(DEFAULT_SETTINGS)
        for row in self.conn.execute("SELECT key, value FROM settings"):
            try:
                out[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                pass
        return out

    # ------------------------------------------------------------- progress

    def lesson_progress(self, lesson_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM lesson_progress WHERE lesson_id=?", (lesson_id,)).fetchone()
        return dict(row) if row else None

    def all_progress(self) -> dict[str, dict]:
        return {r["lesson_id"]: dict(r) for r in self.conn.execute("SELECT * FROM lesson_progress")}

    def start_lesson(self, lesson_id: str, mode: str) -> dict:
        p = self.lesson_progress(lesson_id)
        if p is None:
            self._exec("INSERT INTO lesson_progress(lesson_id, status, step_index, mode, started_at, attempts) "
                       "VALUES(?, 'in_progress', 0, ?, ?, 1)", (lesson_id, mode, now()))
        elif p["status"] == "completed":
            self._exec("UPDATE lesson_progress SET attempts=attempts+1, mode=? WHERE lesson_id=?", (mode, lesson_id))
        return self.lesson_progress(lesson_id)

    def save_step(self, lesson_id: str, step_index: int) -> None:
        self._exec("UPDATE lesson_progress SET step_index=? WHERE lesson_id=?", (step_index, lesson_id))

    def complete_lesson(self, lesson_id: str, score: float) -> None:
        p = self.lesson_progress(lesson_id)
        best = max(score, p["best_score"] or 0) if p else score
        if p is None:
            self._exec("INSERT INTO lesson_progress(lesson_id, status, step_index, best_score, last_score, attempts, "
                       "started_at, completed_at) VALUES(?, 'completed', 0, ?, ?, 1, ?, ?)",
                       (lesson_id, best, score, now(), now()))
        else:
            self._exec("UPDATE lesson_progress SET status='completed', best_score=?, last_score=?, completed_at=? "
                       "WHERE lesson_id=?", (best, score, now(), lesson_id))

    def reset_lesson(self, lesson_id: str) -> None:
        self._exec("UPDATE lesson_progress SET step_index=0 WHERE lesson_id=?", (lesson_id,))

    def record_step(self, lesson_id: str, item_id: str, step_type: str, correct: bool, score: float,
                    attempts: int, hints_used: int = 0) -> None:
        self._exec("INSERT INTO step_results(lesson_id, item_id, step_type, correct, score, attempts, hints_used, ts) "
                   "VALUES(?,?,?,?,?,?,?,?)", (lesson_id, item_id, step_type, int(correct), score, attempts,
                                               hints_used, now()))

    def step_results(self, lesson_id: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM step_results WHERE lesson_id=? ORDER BY id", (lesson_id,))]

    # ---------------------------------------------------------- assessments

    def record_assessment(self, kind: str, ref: str, score: float, passed: bool, details: dict) -> int:
        cur = self._exec("INSERT INTO assessments(kind, ref, score, passed, details, ts) VALUES(?,?,?,?,?,?)",
                         (kind, ref, score, int(passed), json.dumps(details), now()))
        return int(cur.lastrowid)

    def assessments(self, kind: Optional[str] = None) -> list[dict]:
        sql = "SELECT * FROM assessments" + (" WHERE kind=?" if kind else "") + " ORDER BY id"
        rows = self.conn.execute(sql, (kind,) if kind else ())
        out = []
        for r in rows:
            d = dict(r)
            d["details"] = json.loads(d["details"] or "{}")
            out.append(d)
        return out

    # ------------------------------------------------------------------- XP

    def award_xp(self, amount: int, reason: str, ref: str) -> bool:
        """Award XP once per (reason, ref). Returns False if already awarded."""
        try:
            self._exec("INSERT INTO xp_events(amount, reason, ref, ts) VALUES(?,?,?,?)", (amount, reason, ref, now()))
            return True
        except sqlite3.IntegrityError:
            return False

    def total_xp(self) -> int:
        return int(self.conn.execute("SELECT COALESCE(SUM(amount),0) FROM xp_events").fetchone()[0])

    def xp_today(self) -> int:
        today = dt.date.today().isoformat()
        return int(self.conn.execute("SELECT COALESCE(SUM(amount),0) FROM xp_events WHERE substr(ts,1,10)=?",
                                     (today,)).fetchone()[0])

    def award_badge(self, badge_id: str) -> bool:
        try:
            self._exec("INSERT INTO badges(id, earned_at) VALUES(?,?)", (badge_id, now()))
            return True
        except sqlite3.IntegrityError:
            return False

    def badges(self) -> dict[str, str]:
        return {r["id"]: r["earned_at"] for r in self.conn.execute("SELECT * FROM badges ORDER BY earned_at")}

    # ------------------------------------------------------------ bookmarks

    def add_bookmark(self, kind: str, ref: str, title: str) -> None:
        self._exec("INSERT OR IGNORE INTO bookmarks(kind, ref, title, created_at) VALUES(?,?,?,?)",
                   (kind, ref, title, now()))

    def remove_bookmark(self, kind: str, ref: str) -> None:
        self._exec("DELETE FROM bookmarks WHERE kind=? AND ref=?", (kind, ref))

    def is_bookmarked(self, kind: str, ref: str) -> bool:
        return self.conn.execute("SELECT 1 FROM bookmarks WHERE kind=? AND ref=?", (kind, ref)).fetchone() is not None

    def bookmarks(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM bookmarks ORDER BY created_at DESC")]

    # ------------------------------------------------------------- mistakes

    def add_mistake(self, ref: str, lesson_id: str, skill: str, question: str, your_answer: str,
                    expected: str, explanation: str) -> None:
        tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        self._exec(
            "INSERT INTO mistakes(ref, lesson_id, skill, question, your_answer, expected, explanation, created_at, "
            "next_review, interval_days, streak) VALUES(?,?,?,?,?,?,?,?,?,1,0) "
            "ON CONFLICT(ref) DO UPDATE SET your_answer=excluded.your_answer, explanation=excluded.explanation, "
            "next_review=excluded.next_review, interval_days=1, streak=0, resolved=0",
            (ref, lesson_id, skill, question, your_answer, expected, explanation, now(), tomorrow))

    def mistakes(self, include_resolved: bool = False) -> list[dict]:
        sql = "SELECT * FROM mistakes" + ("" if include_resolved else " WHERE resolved=0") + " ORDER BY next_review"
        return [dict(r) for r in self.conn.execute(sql)]

    def due_reviews(self, today: Optional[dt.date] = None) -> list[dict]:
        day = (today or dt.date.today()).isoformat()
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM mistakes WHERE resolved=0 AND next_review<=? ORDER BY next_review", (day,))]

    def review_mistake(self, mistake_id: int, correct: bool, today: Optional[dt.date] = None) -> dict:
        """Spaced repetition: 1, 3, 7, 14, 30 days; three correct reviews in a row resolve it."""
        row = self.conn.execute("SELECT * FROM mistakes WHERE id=?", (mistake_id,)).fetchone()
        if row is None:
            raise KeyError(mistake_id)
        day = today or dt.date.today()
        if correct:
            streak = row["streak"] + 1
            idx = min(streak, len(REVIEW_INTERVALS) - 1)
            interval = REVIEW_INTERVALS[idx]
            resolved = 1 if streak >= 3 else 0
        else:
            streak, interval, resolved = 0, REVIEW_INTERVALS[0], 0
        nxt = (day + dt.timedelta(days=interval)).isoformat()
        self._exec("UPDATE mistakes SET streak=?, interval_days=?, next_review=?, reviews=reviews+1, resolved=? "
                   "WHERE id=?", (streak, interval, nxt, resolved, mistake_id))
        return dict(self.conn.execute("SELECT * FROM mistakes WHERE id=?", (mistake_id,)).fetchone())

    # ------------------------------------------------------------- projects

    def upsert_project(self, name: str, path: str, kind: str, validated: bool, progress: float) -> None:
        self._exec("INSERT INTO projects(name, path, kind, updated_at, validated, progress) VALUES(?,?,?,?,?,?) "
                   "ON CONFLICT(path) DO UPDATE SET name=excluded.name, kind=excluded.kind, "
                   "updated_at=excluded.updated_at, validated=MAX(validated, excluded.validated), "
                   "progress=excluded.progress", (name, path, kind, now(), int(validated), progress))

    def projects(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM projects ORDER BY updated_at DESC")]

    def forget_project(self, path: str) -> None:
        self._exec("DELETE FROM projects WHERE path=?", (path,))

    # ------------------------------------------------------------- evidence

    def add_evidence(self, skills: Iterable[str], source: str, score: float, weight: float) -> None:
        ts = now()
        self.conn.executemany("INSERT INTO skill_evidence(skill, source, score, weight, ts) VALUES(?,?,?,?,?)",
                              [(s, source, float(score), float(weight), ts) for s in skills])
        self.conn.commit()

    def evidence(self, skill: Optional[str] = None) -> list[dict]:
        if skill:
            rows = self.conn.execute("SELECT * FROM skill_evidence WHERE skill=? ORDER BY id", (skill,))
        else:
            rows = self.conn.execute("SELECT * FROM skill_evidence ORDER BY id")
        return [dict(r) for r in rows]

    # ------------------------------------------------------ backup / restore

    def backup(self, dest: Optional[Path] = None, extra_files: Iterable[Path] = ()) -> Path:
        """Write a .zip with a consistent copy of the database plus project files."""
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = Path(dest) if dest else backups_dir() / f"FinPilot-backup-{stamp}.zip"
        tmp_db = dest.with_suffix(".tmp.db")
        target = sqlite3.connect(tmp_db)
        with target:
            self.conn.backup(target)
        target.close()
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp_db, "finpilot.db")
            z.writestr("manifest.json", json.dumps({"app": "FinPilot", "version": __version__,
                                                    "schema": SCHEMA_VERSION, "created": now()}))
            for f in extra_files:
                f = Path(f)
                if f.exists() and f.is_file():
                    z.write(f, f"projects/{f.name}")
        tmp_db.unlink(missing_ok=True)
        return dest

    def restore(self, zip_path: Path) -> list[str]:
        """Replace the current database with the one in a backup. Returns restored project file names.

        The backup is validated first; the current database is backed up
        automatically before being replaced, so a restore can be undone.
        """
        zip_path = Path(zip_path)
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            if "finpilot.db" not in names or "manifest.json" not in names:
                raise ValueError("This file is not a FinPilot backup (missing database or manifest).")
            manifest = json.loads(z.read("manifest.json"))
            if manifest.get("app") != "FinPilot":
                raise ValueError("This backup was not created by FinPilot.")
            if int(manifest.get("schema", 0)) > SCHEMA_VERSION:
                raise ValueError("This backup comes from a newer FinPilot version.")
            staging = self.path.with_name("restore-staging.db")
            staging.write_bytes(z.read("finpilot.db"))
            if not self._healthy(staging):
                staging.unlink(missing_ok=True)
                raise ValueError("The database inside this backup is damaged. Nothing was changed.")
            self.backup(backups_dir() / f"before-restore-{dt.datetime.now():%Y%m%d-%H%M%S}.zip")
            self.conn.close()
            shutil.move(str(staging), str(self.path))
            restored = []
            from ..config import projects_dir
            for n in names:
                if n.startswith("projects/") and n.endswith(".finpilot"):
                    data = z.read(n)
                    out = projects_dir() / Path(n).name
                    if out.exists() and out.read_bytes() != data:
                        # never overwrite a project the learner has now; keep both
                        out = out.with_name(f"{out.stem} (restored){out.suffix}")
                    out.write_bytes(data)
                    restored.append(out.name)
        self.conn = self._open()
        return restored

    def reset_all(self) -> Path:
        """Erase all progress after making a backup. Returns the backup path."""
        b = self.backup()
        for t in ("lesson_progress", "step_results", "assessments", "xp_events", "badges", "bookmarks", "mistakes",
                  "projects", "skill_evidence", "settings"):
            self.conn.execute(f"DELETE FROM {t}")
        self.conn.commit()
        return b
