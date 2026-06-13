from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class TutorMemory:
    """Three-layer SQLite memory for sessions, profiles, and misconceptions."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS students (
                    student_id TEXT PRIMARY KEY,
                    ability TEXT NOT NULL DEFAULT 'beginner',
                    goals TEXT NOT NULL DEFAULT '[]',
                    strengths TEXT NOT NULL DEFAULT '[]',
                    weaknesses TEXT NOT NULL DEFAULT '[]',
                    completed_topics TEXT NOT NULL DEFAULT '[]',
                    learning_progress TEXT NOT NULL DEFAULT '{}',
                    mastered_topics TEXT NOT NULL DEFAULT '[]',
                    struggling_topics TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS session_state (
                    student_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    topic TEXT NOT NULL DEFAULT '',
                    current_question TEXT NOT NULL DEFAULT '',
                    confusion TEXT NOT NULL DEFAULT '',
                    goal TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (student_id, session_id)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    student_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quiz_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    score REAL NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS misconceptions (
                    student_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    misconception TEXT NOT NULL,
                    evidence TEXT NOT NULL DEFAULT '',
                    occurrences INTEGER NOT NULL DEFAULT 1,
                    severity TEXT NOT NULL DEFAULT 'medium',
                    recommended_fix TEXT NOT NULL DEFAULT '',
                    last_seen TEXT NOT NULL,
                    PRIMARY KEY (student_id, topic, misconception)
                );
                """
            )
            self._ensure_column(db, "students", "strengths", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(db, "students", "weaknesses", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(
                db, "students", "completed_topics", "TEXT NOT NULL DEFAULT '[]'"
            )
            self._ensure_column(
                db, "students", "learning_progress", "TEXT NOT NULL DEFAULT '{}'"
            )
            self._ensure_column(
                db, "misconceptions", "evidence", "TEXT NOT NULL DEFAULT ''"
            )
            self._ensure_column(
                db, "misconceptions", "severity", "TEXT NOT NULL DEFAULT 'medium'"
            )
            self._ensure_column(
                db,
                "misconceptions",
                "recommended_fix",
                "TEXT NOT NULL DEFAULT ''",
            )

    @staticmethod
    def _ensure_column(
        db: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {
            row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def profile(self, student_id: str) -> dict:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM students WHERE student_id = ?", (student_id,)
            ).fetchone()
            if row is None:
                now = _now()
                db.execute(
                    "INSERT INTO students(student_id, updated_at) VALUES (?, ?)",
                    (student_id, now),
                )
                return {
                    "student_id": student_id,
                    "ability": "beginner",
                    "goals": [],
                    "strengths": [],
                    "weaknesses": [],
                    "completed_topics": [],
                    "learning_progress": {},
                    "mastered_topics": [],
                    "struggling_topics": [],
                    "misconceptions": [],
                    "quiz_history": [],
                }
            misconceptions = [
                dict(item)
                for item in db.execute(
                    "SELECT topic, misconception, evidence, occurrences, severity, "
                    "recommended_fix, last_seen FROM misconceptions "
                    "WHERE student_id = ? ORDER BY occurrences DESC",
                    (student_id,),
                ).fetchall()
            ]
            quizzes = [
                dict(item)
                for item in db.execute(
                    "SELECT topic, score, created_at FROM quiz_attempts "
                    "WHERE student_id = ? ORDER BY id DESC LIMIT 10",
                    (student_id,),
                ).fetchall()
            ]
            return {
                "student_id": student_id,
                "ability": row["ability"],
                "goals": json.loads(row["goals"]),
                "strengths": json.loads(row["strengths"]),
                "weaknesses": json.loads(row["weaknesses"]),
                "completed_topics": json.loads(row["completed_topics"]),
                "learning_progress": json.loads(row["learning_progress"]),
                "mastered_topics": json.loads(row["mastered_topics"]),
                "struggling_topics": json.loads(row["struggling_topics"]),
                "misconceptions": misconceptions,
                "quiz_history": quizzes,
            }

    def session(self, student_id: str, session_id: str) -> dict:
        """Return the structured working memory for one conversation."""
        with self._connect() as db:
            row = db.execute(
                "SELECT topic, current_question, confusion, goal, updated_at "
                "FROM session_state WHERE student_id = ? AND session_id = ?",
                (student_id, session_id),
            ).fetchone()
        if row is None:
            return {
                "topic": "",
                "current_question": "",
                "confusion": "",
                "goal": "",
            }
        return dict(row)

    def update_session(
        self,
        student_id: str,
        session_id: str,
        *,
        topic: str = "",
        current_question: str = "",
        confusion: str = "",
        goal: str = "",
    ) -> None:
        current = self.session(student_id, session_id)
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO session_state(
                    student_id, session_id, topic, current_question, confusion, goal, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(student_id, session_id)
                DO UPDATE SET
                    topic = excluded.topic,
                    current_question = excluded.current_question,
                    confusion = excluded.confusion,
                    goal = excluded.goal,
                    updated_at = excluded.updated_at
                """,
                (
                    student_id,
                    session_id,
                    topic or current.get("topic", ""),
                    current_question or current.get("current_question", ""),
                    confusion or current.get("confusion", ""),
                    goal or current.get("goal", ""),
                    _now(),
                ),
            )

    def history(self, student_id: str, session_id: str, limit: int = 12) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT role, content FROM messages WHERE student_id = ? AND session_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (student_id, session_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def add_message(
        self, student_id: str, session_id: str, role: str, content: str
    ) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO messages(session_id, student_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, student_id, role, content, _now()),
            )

    def record_misconception(
        self,
        student_id: str,
        topic: str,
        misconception: str,
        *,
        evidence: str = "",
        severity: str | None = None,
        recommended_fix: str = "",
    ) -> None:
        with self._connect() as db:
            existing = db.execute(
                "SELECT severity FROM misconceptions "
                "WHERE student_id = ? AND topic = ? AND misconception = ?",
                (student_id, topic, misconception),
            ).fetchone()
            resolved_severity = severity or (
                existing["severity"] if existing is not None else "medium"
            )
            db.execute(
                """
                INSERT INTO misconceptions(
                    student_id, topic, misconception, evidence, severity,
                    recommended_fix, last_seen
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(student_id, topic, misconception)
                DO UPDATE SET
                    occurrences = occurrences + 1,
                    evidence = CASE
                        WHEN excluded.evidence = '' THEN misconceptions.evidence
                        ELSE excluded.evidence
                    END,
                    severity = excluded.severity,
                    recommended_fix = CASE
                        WHEN excluded.recommended_fix = '' THEN misconceptions.recommended_fix
                        ELSE excluded.recommended_fix
                    END,
                    last_seen = excluded.last_seen
                """,
                (
                    student_id,
                    topic,
                    misconception,
                    evidence,
                    resolved_severity,
                    recommended_fix,
                    _now(),
                ),
            )

    def relevant_misconceptions(self, student_id: str, topic: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT topic, misconception, evidence, occurrences, severity, "
                "recommended_fix, last_seen FROM misconceptions "
                "WHERE student_id = ? AND (topic = ? OR ? = '') "
                "ORDER BY occurrences DESC, last_seen DESC LIMIT 5",
                (student_id, topic, topic),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_quiz(
        self, student_id: str, topic: str, score: float, details: dict
    ) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO quiz_attempts(student_id, topic, score, details, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (student_id, topic, score, json.dumps(details), _now()),
            )

    def update_profile(
        self,
        student_id: str,
        *,
        ability: str | None = None,
        goals: list[str] | None = None,
        strengths: list[str] | None = None,
        weaknesses: list[str] | None = None,
        completed_topics: list[str] | None = None,
        learning_progress: dict | None = None,
        mastered_topics: list[str] | None = None,
        struggling_topics: list[str] | None = None,
    ) -> None:
        current = self.profile(student_id)
        with self._connect() as db:
            db.execute(
                """
                UPDATE students
                SET ability = ?, goals = ?, strengths = ?, weaknesses = ?,
                    completed_topics = ?, learning_progress = ?, mastered_topics = ?,
                    struggling_topics = ?, updated_at = ?
                WHERE student_id = ?
                """,
                (
                    ability or current["ability"],
                    json.dumps(goals if goals is not None else current["goals"]),
                    json.dumps(
                        strengths if strengths is not None else current["strengths"]
                    ),
                    json.dumps(
                        weaknesses if weaknesses is not None else current["weaknesses"]
                    ),
                    json.dumps(
                        completed_topics
                        if completed_topics is not None
                        else current["completed_topics"]
                    ),
                    json.dumps(
                        learning_progress
                        if learning_progress is not None
                        else current["learning_progress"]
                    ),
                    json.dumps(
                        mastered_topics
                        if mastered_topics is not None
                        else current["mastered_topics"]
                    ),
                    json.dumps(
                        struggling_topics
                        if struggling_topics is not None
                        else current["struggling_topics"]
                    ),
                    _now(),
                    student_id,
                ),
            )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
