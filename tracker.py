import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "seen_jobs.db"

# Parenthetical noise that staffing agencies vary between reposts:
# "Data Analyst (Remote)" / "(W2)" / "(Urgent)" are the same job
_NOISE_PARENS = re.compile(
    r"\s*\((?:remote|hybrid|on-?site|onsite|contract|w2|c2c|1099|"
    r"urgent|immediate(?:ly)?|repost(?:ed)?|full[- ]?time|part[- ]?time)[^)]*\)",
    re.IGNORECASE,
)


def _norm_title(title: str) -> str:
    t = _NOISE_PARENS.sub("", title or "")
    return re.sub(r"\s+", " ", t).strip().lower()


class JobTracker:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        # WAL lets the dashboard read while a scan thread writes
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_db()
        self._migrate()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_jobs (
                job_id    TEXT PRIMARY KEY,
                source    TEXT,
                company   TEXT,
                title     TEXT,
                location  TEXT,
                url       TEXT,
                posted_at TEXT,
                applied   INTEGER DEFAULT 0,
                seen_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def _migrate(self):
        """Add columns introduced after initial release without breaking existing DBs."""
        for col, definition in [
            ("posted_at",       "TEXT"),
            ("applied",         "INTEGER DEFAULT 0"),
            ("auto_applied",    "INTEGER DEFAULT 0"),
            ("auto_applied_at", "TEXT"),
            ("needs_review",    "INTEGER DEFAULT 0"),
            ("review_reason",   "TEXT"),
            ("fit_reason",      "TEXT"),   # agent: why this job fits
            ("fit_gap",         "TEXT"),   # agent: honest gap
            ("agent_match",     "INTEGER"),# agent: blended score
        ]:
            try:
                self.conn.execute(f"ALTER TABLE seen_jobs ADD COLUMN {col} {definition}")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists

        # Indexes for the hot lookups (seen_by_title_company was a full scan)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_title_company "
            "ON seen_jobs (lower(trim(title)), lower(trim(company)))"
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_seen_at ON seen_jobs (seen_at)")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_company ON seen_jobs (lower(trim(company)))"
        )
        # One-time cleanup: sources were stored with mixed case (LinkedIn vs linkedin)
        self.conn.execute("UPDATE seen_jobs SET source = lower(source) WHERE source != lower(source)")
        self.conn.commit()

    # ── write ──────────────────────────────────────────────────────────────

    def seen(self, job_id: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM seen_jobs WHERE job_id = ?", (job_id,)
        )
        return cur.fetchone() is not None

    def seen_by_title_company(self, title: str, company: str) -> bool:
        """Dedup reposts: same title+company already in DB under any ID.
        Falls back to a normalized comparison that ignores parenthetical
        noise like "(Remote)" / "(W2)" that agencies vary between reposts."""
        cur = self.conn.execute(
            "SELECT 1 FROM seen_jobs WHERE lower(trim(title))=lower(trim(?)) AND lower(trim(company))=lower(trim(?))",
            (title, company),
        )
        if cur.fetchone() is not None:
            return True

        # Normalized pass over this company's existing titles
        target = _norm_title(title)
        if not target:
            return False
        cur = self.conn.execute(
            "SELECT title FROM seen_jobs WHERE lower(trim(company))=lower(trim(?)) AND title != '__repost__'",
            (company,),
        )
        return any(_norm_title(row["title"]) == target for row in cur.fetchall())

    def mark_seen(self, job: dict):
        self.conn.execute(
            """INSERT OR IGNORE INTO seen_jobs
               (job_id, source, company, title, location, url, posted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                job["id"], (job["source"] or "").lower(), job["company"],
                job["title"], job["location"], job["url"],
                job.get("posted_at"),
            ),
        )
        self.conn.commit()

    def mark_needs_review(self, job_id: str, reason: str):
        self.conn.execute(
            "UPDATE seen_jobs SET needs_review = 1, review_reason = ? WHERE job_id = ?",
            (reason, job_id),
        )
        self.conn.commit()

    def clear_review(self, job_id: str):
        self.conn.execute(
            "UPDATE seen_jobs SET needs_review = 0, review_reason = NULL WHERE job_id = ?",
            (job_id,),
        )
        self.conn.commit()

    def mark_auto_applied(self, job_id: str):
        from datetime import datetime
        self.conn.execute(
            "UPDATE seen_jobs SET auto_applied = 1, auto_applied_at = ?, applied = 1 WHERE job_id = ?",
            (datetime.now().isoformat(), job_id),
        )
        self.conn.commit()

    def toggle_applied(self, job_id: str) -> bool:
        """Flip applied flag. Returns new state (True = applied)."""
        cur = self.conn.execute(
            "SELECT applied FROM seen_jobs WHERE job_id = ?", (job_id,)
        )
        row = cur.fetchone()
        if row is None:
            return False
        new_val = 0 if row["applied"] else 1
        self.conn.execute(
            "UPDATE seen_jobs SET applied = ? WHERE job_id = ?", (new_val, job_id)
        )
        self.conn.commit()
        return bool(new_val)

    # ── read ───────────────────────────────────────────────────────────────

    def save_agent_assessment(self, job_id: str, match: int | None,
                              reason: str | None, gap: str | None):
        """Persist the agent's fit reasoning so the UI can show it."""
        self.conn.execute(
            "UPDATE seen_jobs SET agent_match = ?, fit_reason = ?, fit_gap = ? "
            "WHERE job_id = ?",
            (match, reason, gap, job_id),
        )
        self.conn.commit()

    def all_jobs(self) -> list[dict]:
        cur = self.conn.execute(
            """SELECT job_id, source, company, title, location,
                      url, posted_at, applied, auto_applied, auto_applied_at,
                      needs_review, review_reason, seen_at,
                      fit_reason, fit_gap, agent_match
               FROM seen_jobs
               WHERE title != '__repost__'
               ORDER BY
                 CASE WHEN posted_at IS NOT NULL THEN posted_at ELSE seen_at END DESC"""
        )
        return [dict(row) for row in cur.fetchall()]

    def stats(self) -> dict:
        cur = self.conn.execute("""
            SELECT
              COUNT(*)                                                             AS total,
              SUM(CASE WHEN applied = 1 THEN 1 ELSE 0 END)                       AS applied,
              SUM(CASE WHEN needs_review = 1 AND applied = 0 THEN 1 ELSE 0 END)  AS needs_review,
              SUM(CASE WHEN datetime(COALESCE(posted_at, seen_at)) >=
                            datetime('now', '-1 hour') THEN 1 ELSE 0 END)        AS last_hour,
              SUM(CASE WHEN datetime(COALESCE(posted_at, seen_at)) >=
                            datetime('now', '-24 hours') THEN 1 ELSE 0 END)      AS last_day
            FROM seen_jobs
            WHERE title != '__repost__'
        """)
        row = cur.fetchone()
        return dict(row) if row else {}

    def recent(self, limit: int = 50) -> list[dict]:
        cur = self.conn.execute(
            """SELECT company, title, location, url, seen_at
               FROM seen_jobs ORDER BY seen_at DESC LIMIT ?""",
            (limit,),
        )
        cols = ["company", "title", "location", "url", "seen_at"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def close(self):
        self.conn.close()
