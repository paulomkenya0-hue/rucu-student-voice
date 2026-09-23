-- RUCU Student Voice — Supabase (Postgres) schema
-- Run in Supabase SQL editor, then set DATABASE_URL and deploy.



CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'OFFICER',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  description TEXT DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roster_students (
  id SERIAL PRIMARY KEY,
  full_name TEXT NOT NULL,
  registration_number TEXT UNIQUE NOT NULL,
  programme TEXT DEFAULT '',
  year_of_study TEXT DEFAULT '',
  phone TEXT DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
  id SERIAL PRIMARY KEY,
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
  id SERIAL PRIMARY KEY,
  feedback_id INTEGER NOT NULL,
  admin_id INTEGER,
  response TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (feedback_id) REFERENCES feedback(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS internal_notes (
  id SERIAL PRIMARY KEY,
  feedback_id INTEGER NOT NULL,
  admin_id INTEGER,
  note TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (feedback_id) REFERENCES feedback(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS status_history (
  id SERIAL PRIMARY KEY,
  feedback_id INTEGER NOT NULL,
  old_status TEXT,
  new_status TEXT NOT NULL,
  changed_by INTEGER,
  created_at TEXT NOT NULL,
  FOREIGN KEY (feedback_id) REFERENCES feedback(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attachments (
  id SERIAL PRIMARY KEY,
  feedback_id INTEGER NOT NULL,
  file_path TEXT NOT NULL,
  file_name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (feedback_id) REFERENCES feedback(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS verification_codes (
  id SERIAL PRIMARY KEY,
  reference_number TEXT NOT NULL,
  phone TEXT DEFAULT '',
  code TEXT NOT NULL,
  verified INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sms_log (
  id SERIAL PRIMARY KEY,
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
  id SERIAL PRIMARY KEY,
  registration_number TEXT UNIQUE NOT NULL,
  full_name TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS otp_codes (
  id SERIAL PRIMARY KEY,
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
  id SERIAL PRIMARY KEY,
  full_name TEXT NOT NULL,
  registration_number TEXT DEFAULT '',
  phone TEXT NOT NULL,
  amount TEXT DEFAULT '',
  status TEXT DEFAULT 'active',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_loan_phone ON loan_recipients(phone);

CREATE TABLE IF NOT EXISTS announcements (
  id SERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  audience TEXT NOT NULL DEFAULT 'all',
  active INTEGER NOT NULL DEFAULT 1,
  created_by INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS polls (
  id SERIAL PRIMARY KEY,
  question TEXT NOT NULL,
  semester TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS poll_votes (
  id SERIAL PRIMARY KEY,
  poll_id INTEGER NOT NULL,
  registration_number TEXT NOT NULL,
  rating INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(poll_id, registration_number),
  FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS appeals (
  id SERIAL PRIMARY KEY,
  feedback_id INTEGER NOT NULL,
  registration_number TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'Open',
  admin_response TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (feedback_id) REFERENCES feedback(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS system_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS submit_log (
  id SERIAL PRIMARY KEY,
  ip TEXT,
  created_at TEXT NOT NULL
);