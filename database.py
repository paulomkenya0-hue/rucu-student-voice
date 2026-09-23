"""RUCU Student Voice - SQLite schema & helpers."""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "rucu_voice.db")

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'OFFICER',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  description TEXT DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roster_students (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL,
  registration_number TEXT UNIQUE NOT NULL,
  programme TEXT DEFAULT '',
  year_of_study TEXT DEFAULT '',
  phone TEXT DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reference_number TEXT UNIQUE NOT NULL,
  submission_type TEXT NOT NULL,
  category_id INTEGER,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  incident_date TEXT DEFAULT '',
  location TEXT DEFAULT '',
  suggested_solution TEXT DEFAULT '',
  satisfaction_rating INTEGER DEFAULT 0,
  priority TEXT NOT NULL DEFAULT 'Medium',
  is_anonymous INTEGER NOT NULL DEFAULT 0,
  student_name TEXT DEFAULT '',
  registration_number TEXT DEFAULT '',
  programme TEXT DEFAULT '',
  year_of_study TEXT DEFAULT '',
  phone TEXT DEFAULT '',
  email TEXT DEFAULT '',
  reg_verified INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'New',
  assigned_to INTEGER,
  is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  resolved_at TEXT,
  FOREIGN KEY (category_id) REFERENCES categories(id),
  FOREIGN KEY (assigned_to) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_fb_ref ON feedback(reference_number);
CREATE INDEX IF NOT EXISTS idx_fb_status ON feedback(status);
CREATE INDEX IF NOT EXISTS idx_fb_cat ON feedback(category_id);
CREATE INDEX IF NOT EXISTS idx_fb_created ON feedback(created_at);

CREATE TABLE IF NOT EXISTS responses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feedback_id INTEGER NOT NULL,
  admin_id INTEGER,
  response TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (feedback_id) REFERENCES feedback(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS internal_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feedback_id INTEGER NOT NULL,
  admin_id INTEGER,
  note TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (feedback_id) REFERENCES feedback(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS status_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feedback_id INTEGER NOT NULL,
  old_status TEXT,
  new_status TEXT NOT NULL,
  changed_by INTEGER,
  created_at TEXT NOT NULL,
  FOREIGN KEY (feedback_id) REFERENCES feedback(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attachments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feedback_id INTEGER NOT NULL,
  file_path TEXT NOT NULL,
  file_name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (feedback_id) REFERENCES feedback(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS verification_codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reference_number TEXT NOT NULL,
  phone TEXT DEFAULT '',
  code TEXT NOT NULL,
  verified INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sms_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT NOT NULL,
  message TEXT NOT NULL,
  reference_number TEXT DEFAULT '',
  provider TEXT DEFAULT 'demo-log',
  status TEXT DEFAULT 'logged',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS student_accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  registration_number TEXT UNIQUE NOT NULL,
  full_name TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS otp_codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  registration_number TEXT NOT NULL,
  phone TEXT NOT NULL,
  code TEXT NOT NULL,
  purpose TEXT NOT NULL DEFAULT 'submit',
  verified INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_otp_reg ON otp_codes(registration_number);

CREATE TABLE IF NOT EXISTS student_tokens (
  token TEXT PRIMARY KEY,
  registration_number TEXT NOT NULL,
  phone TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loan_recipients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL,
  registration_number TEXT DEFAULT '',
  phone TEXT NOT NULL,
  amount TEXT DEFAULT '',
  status TEXT DEFAULT 'active',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_loan_phone ON loan_recipients(phone);

CREATE TABLE IF NOT EXISTS announcements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  audience TEXT NOT NULL DEFAULT 'all',
  active INTEGER NOT NULL DEFAULT 1,
  created_by INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS polls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question TEXT NOT NULL,
  semester TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS poll_votes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  poll_id INTEGER NOT NULL,
  registration_number TEXT NOT NULL,
  rating INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(poll_id, registration_number),
  FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS appeals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feedback_id INTEGER NOT NULL,
  registration_number TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'Open',
  admin_response TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (feedback_id) REFERENCES feedback(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ip TEXT,
  question TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS submit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ip TEXT,
  created_at TEXT NOT NULL
);
"""

DEFAULT_CATEGORIES = [
    ("Loans & Student Financing", "HELSB, fees, loans and financing issues"),
    ("Student Welfare", "General student welfare matters"),
    ("Academic Services", "Lectures, timetable, courses, results"),
    ("Registration", "Course registration and enrolment"),
    ("Examination Services", "Exams, timetables, results, scripts"),
    ("Accommodation", "Hostels and housing"),
    ("Food/Cafeteria", "Cafeteria and food services"),
    ("Library", "Library services and resources"),
    ("ICT/Internet", "Wi-Fi, internet, systems, computers"),
    ("Finance/Payments", "Fees, payments, receipts"),
    ("Administration", "General administration services"),
    ("Student Leadership", "RUCUSO and student leadership"),
    ("Campus Environment", "Cleanliness, environment, facilities"),
    ("Security", "Campus security and safety"),
    ("Health Services", "Dispensary and health support"),
    ("Other", "Any other matter"),
]

DEFAULT_SETTINGS = {
    "university_name": "Ruaha Catholic University (RUCU)",
    "academic_year": "2026/2027",
    "contact_email": "info@rucu.ac.tz",
    "contact_phone": "+255 ...",
    "ref_prefix": "RUCU",
    "sms_provider": "demo-log",
    "sms_api_key": "",
    "sms_sender": "RUCU",
    "sla_days": "7",
    "poll_question": "Muhula huu, unaridhika vipi na huduma za mikopo (BOOM/Ada)?",
    "poll_semester": "Semester 1 - 2026/2027",
    "lang_default": "sw",
}


DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _psycopg():
    try:
        import psycopg  # psycopg v3 (binary). pip install psycopg[binary]
        return psycopg
    except ImportError:
        return None


def pg_enabled():
    return DATABASE_URL.startswith("postgres") and _psycopg() is not None


class _Row(dict):
    """Dict row that also supports integer indexing like sqlite3.Row."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _PGCursor:
    def __init__(self, cur):
        self._cur = cur
        self.lastrowid = None
        try:
            self.lastrowid = cur.lastrowid
        except Exception:
            pass

    def fetchone(self):
        r = self._cur.fetchone()
        return _Row(r) if r is not None else None

    def fetchall(self):
        return [_Row(r) for r in self._cur.fetchall()]

    def __getitem__(self, i):
        return self.fetchall()[i]


class _PGConn:
    """Wraps a psycopg connection so existing sqlite-style code keeps working.

    - Translates ? placeholders to %s
    - Converts INSERT OR IGNORE to ON CONFLICT DO NOTHING
    """

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, args=()):
        original = sql
        sql = sql.replace("?", "%s")
        if "INSERT OR IGNORE INTO" in sql:
            sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            if "ON CONFLICT" not in sql.upper():
                sql = sql + " ON CONFLICT DO NOTHING"
        try:
            from psycopg.rows import dict_row  # psycopg required for PG mode
        except ImportError:
            dict_row = None
        try:
            cur = self._conn.cursor(row_factory=dict_row)
        except TypeError:
            cur = self._conn.cursor()
        cur.execute(sql, args)
        out = _PGCursor(cur)
        if original.strip().upper().startswith("INSERT") and "RETURNING" not in original.upper():
            try:
                cur.execute("SELECT LASTVAL()")
                out.lastrowid = cur.fetchone()["lastval"]
            except Exception:
                pass
        return out

    def executelastrowid(self, sql, args=()):
        return self.execute(sql, args).lastrowid

    def commit(self):
        return self._conn.commit()

    def close(self):
        return self._conn.close()


def get_db():
    if pg_enabled():
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False)
        return _PGConn(conn)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def pg_schema():
    """Postgres/Supabase version of SCHEMA for the SQL editor."""
    s = SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    return "\n".join(l for l in s.splitlines() if not l.strip().startswith("PRAGMA"))


def init_db():
    conn = get_db()
    if pg_enabled():
        for stmt in pg_schema().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        for col in ("phone_verified",):
            try:
                conn.execute(f"ALTER TABLE feedback ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
            except Exception:
                try:
                    conn._conn.rollback()
                except Exception:
                    pass
    else:
        conn.executescript(SCHEMA)
        for col in ("phone_verified",):
            try:
                conn.execute(f"ALTER TABLE feedback ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
            except Exception:
                pass
    now = datetime.utcnow().isoformat()
    for name, desc in DEFAULT_CATEGORIES:
        conn.execute(
            "INSERT OR IGNORE INTO categories (name, description, active, created_at) VALUES (?,?,1,?)",
            (name, desc, now),
        )
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES (?,?)", (k, v))
    # default semester poll
    try:
        row = conn.execute("SELECT id FROM polls WHERE active=1").fetchone()
        if not row:
            conn.execute("INSERT INTO polls (question,semester,active,created_at) VALUES (?,?,1,?)",
                         (DEFAULT_SETTINGS["poll_question"], DEFAULT_SETTINGS["poll_semester"], now))
    except Exception:
        pass
    conn.commit()
    conn.close()


def get_setting(key, default=""):
    conn = get_db()
    row = conn.execute("SELECT value FROM system_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_db()
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()
