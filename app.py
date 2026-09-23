"""RUCU STUDENT VOICE & INSTITUTIONAL FEEDBACK SYSTEM - Flask backend."""
import os, re, csv, io, secrets, random
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template, send_file, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import database as db
import sms_util
import rucuso_ai

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".pdf", ".docx", ".txt"}

STATUSES = ["New", "Under Review", "Assigned", "In Progress",
            "Awaiting Information", "Resolved", "Closed", "Rejected/Invalid"]
TYPES = ["General Feedback", "Complaint", "Challenge/Problem", "Suggestion", "Praise/Appreciation"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]


def init():
    db.init_db()
    conn = db.get_db()
    row = conn.execute("SELECT id FROM users WHERE email='admin@rucu.ac.tz'").fetchone()
    if not row:
        conn.execute(
            "INSERT INTO users (name,email,password_hash,role,status,created_at) VALUES (?,?,?,?,?,?)",
            ("Super Admin", "admin@rucu.ac.tz",
             generate_password_hash("RucuAdmin2026"), "SUPER ADMIN", "active",
             datetime.utcnow().isoformat()))
        conn.commit()
    conn.close()


def current_user():
    tok = request.headers.get("Authorization", "").replace("Bearer ", "") or request.cookies.get("rucu_token", "")
    if not tok:
        return None
    conn = db.get_db()
    s = conn.execute("SELECT user_id FROM sessions WHERE token=?", (tok,)).fetchone()
    if not s:
        conn.close()
        return None
    u = conn.execute("SELECT id,name,email,role,status FROM users WHERE id=?", (s["user_id"],)).fetchone()
    conn.close()
    return dict(u) if u and u["status"] == "active" else None


def require_admin(fn):
    @wraps(fn)
    def w(*a, **k):
        u = current_user()
        if not u:
            return jsonify({"error": "Login required"}), 401
        g.admin = u
        return fn(*a, **k)
    return w


def require_super(fn):
    @wraps(fn)
    def w(*a, **k):
        u = current_user()
        if not u or u["role"] != "SUPER ADMIN":
            return jsonify({"error": "Super Admin only"}), 403
        g.admin = u
        return fn(*a, **k)
    return w


def next_reference():
    prefix = db.get_setting("ref_prefix", "RUCU")
    year = db.get_setting("academic_year", "2026/2027")[:4]
    conn = db.get_db()
    n = conn.execute("SELECT COUNT(*) c FROM feedback").fetchone()["c"] + 1
    conn.close()
    return f"{prefix}-{year}-{n:06d}"


# ---------- pages ----------
@app.route("/")
def index(): return render_template("index.html")
@app.route("/submit")
def submit_page(): return render_template("submit.html")
@app.route("/track")
def track_page(): return render_template("track.html")
@app.route("/my")
def my_page(): return render_template("my.html")
@app.route("/robots.txt")
def robots():
    return ("User-agent: *\nAllow: /\nDisallow: /dashboard\nDisallow: /issues\n"
            "Disallow: /issue/\nDisallow: /reports\nDisallow: /settings\nDisallow: /users\n"
            "Disallow: /roster\nDisallow: /appeals\nDisallow: /announcements\n"
            "Disallow: /admin-login\nSitemap: " + request.host_url + "sitemap.xml\n",
            200, {"Content-Type": "text/plain"})


@app.route("/sitemap.xml")
def sitemap():
    urls = ["", "submit", "track", "my", "admin-login"]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        xml.append(f"<url><loc>{request.host_url}{u}</loc><changefreq>weekly</changefreq></url>")
    xml.append("</urlset>")
    return ("\n".join(xml), 200, {"Content-Type": "application/xml"})


@app.route("/admin-login")
def admin_login_page(): return render_template("login.html")
@app.route("/dashboard")
def dash(): return render_template("admin/dashboard.html")
@app.route("/issues")
def issues(): return render_template("admin/issues.html")
@app.route("/issue/<ref>")
def issue_detail(ref): return render_template("admin/issue_detail.html", ref=ref)
@app.route("/reports")
def reports_page(): return render_template("admin/reports.html")
@app.route("/settings")
def settings_page(): return render_template("admin/settings.html")
@app.route("/users")
def users_page(): return render_template("admin/users.html")
@app.route("/roster")
def roster_page(): return render_template("admin/roster.html")
@app.route("/announcements")
def announcements_page(): return render_template("admin/announcements.html")
@app.route("/appeals")
def appeals_page(): return render_template("admin/appeals.html")


# ---------- public APIs ----------
@app.route("/api/settings-public")
def settings_public():
    return jsonify({"university_name": db.get_setting("university_name"),
                    "academic_year": db.get_setting("academic_year"),
                    "contact_email": db.get_setting("contact_email"),
                    "contact_phone": db.get_setting("contact_phone")})


@app.route("/api/categories")
def categories():
    conn = db.get_db()
    rows = conn.execute("SELECT id,name,description FROM categories WHERE active=1 ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/verify-registration")
def verify_reg():
    reg = (request.args.get("reg", "") or "").strip().upper()
    if not reg:
        return jsonify({"found": False})
    conn = db.get_db()
    r = conn.execute("SELECT full_name,registration_number,programme,year_of_study FROM roster_students WHERE UPPER(registration_number)=?",
                     (reg,)).fetchone()
    conn.close()
    if r:
        return jsonify({"found": True, "verified": True, **dict(r)})
    return jsonify({"found": False, "verified": False,
                    "message": "Registration number not found in university roster. You may still submit, but verification is recommended."})


@app.route("/api/feedback", methods=["POST"])
def submit_feedback():
    # Gate: student must have verified reg + TZ phone OTP first.
    tok = request.headers.get("X-Student-Token", "") or request.form.get("student_token", "")
    st = check_student_token(tok)
    if not st:
        return jsonify({"error": "Verify first: registration number -> phone (06/07/255) -> SMS OTP."}), 401
    ip = request.remote_addr or "?"
    conn = db.get_db()
    since = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    n = conn.execute("SELECT COUNT(*) c FROM submit_log WHERE ip=? AND created_at>?", (ip, since)).fetchone()["c"]
    if n >= 15:
        conn.close()
        return jsonify({"error": "Too many submissions. Please try again later."}), 429
    conn.execute("INSERT INTO submit_log (ip, created_at) VALUES (?,?)", (ip, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    f = request.form
    stype = f.get("submission_type", "General Feedback")
    title = (f.get("title", "") or "").strip()
    desc = (f.get("description", "") or "").strip()
    if stype not in TYPES: return jsonify({"error": "Invalid submission type"}), 400
    if len(title) < 5: return jsonify({"error": "Title too short (min 5 characters)"}), 400
    if len(desc) < 10: return jsonify({"error": "Description too short (min 10 characters)"}), 400
    if f.get("consent") != "yes":
        return jsonify({"error": "You must accept the privacy notice (☐ I understand)."}), 400
    try:
        rating = int(f.get("satisfaction_rating", 0) or 0)
    except ValueError:
        rating = 0
    priority = f.get("priority", "Medium")
    if priority not in PRIORITIES: priority = "Medium"
    is_anon = 1 if f.get("is_anonymous") == "yes" else 0

    # duplicate detection
    conn = db.get_db()
    dup = conn.execute(
        "SELECT reference_number FROM feedback WHERE title=? AND description=? AND created_at>?",
        (title, desc, (datetime.utcnow() - timedelta(minutes=10)).isoformat())).fetchone()
    if dup:
        conn.close()
        return jsonify({"error": "Duplicate submission detected.", "reference_number": dup["reference_number"]}), 409

    reg = st["registration_number"]
    verified_phone = st["phone"]
    reg_verified = 1
    r = conn.execute("SELECT full_name,programme,year_of_study FROM roster_students WHERE UPPER(registration_number)=?",
                     (reg,)).fetchone()
    auto_name = r["full_name"] if r else ""
    auto_prog = r["programme"] if r else ""
    auto_year = r["year_of_study"] if r else ""

    ref = next_reference()
    now = datetime.utcnow().isoformat()
    cur = conn.execute(
        """INSERT INTO feedback (reference_number,submission_type,category_id,title,description,
        incident_date,location,suggested_solution,satisfaction_rating,priority,is_anonymous,
        student_name,registration_number,programme,year_of_study,phone,email,reg_verified,
        phone_verified,status,is_demo,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ref, stype, f.get("category_id") or None, title, desc,
         f.get("incident_date", ""), f.get("location", ""), f.get("suggested_solution", ""),
         rating, priority, is_anon,
         "" if is_anon else (f.get("student_name", "") or auto_name),
         reg,
         "" if is_anon else (f.get("programme", "") or auto_prog),
         "" if is_anon else (f.get("year_of_study", "") or auto_year),
         verified_phone, "" if is_anon else f.get("email", ""),
         reg_verified, 1, "New", 0, now, now))
    fb_id = cur.lastrowid
    conn.execute("INSERT INTO status_history (feedback_id,old_status,new_status,changed_by,created_at) VALUES (?,?,?,?,?)",
                 (fb_id, None, "New", None, now))
    # attachments
    for key in request.files:
        file = request.files[key]
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ALLOWED_EXT:
                continue
            safe = secure_filename(file.filename)
            path = os.path.join(UPLOAD_DIR, f"{ref}_{safe}")
            file.save(path)
            conn.execute("INSERT INTO attachments (feedback_id,file_path,file_name,created_at) VALUES (?,?,?,?)",
                         (fb_id, path, safe, now))
    # optional: set login password at submit time (same transaction)
    new_pw = (f.get("new_password") or "").strip()
    pw_hash = generate_password_hash(new_pw) if new_pw and len(new_pw) >= 4 else None
    if pw_hash:
        conn.execute("INSERT INTO student_accounts (registration_number,full_name,phone,password_hash,created_at) VALUES (?,?,?,?,?) "
                     "ON CONFLICT(registration_number) DO UPDATE SET password_hash=excluded.password_hash, phone=excluded.phone",
                     (reg, auto_name, verified_phone, pw_hash, now))
    conn.commit()
    conn.close()
    # receipt SMS AFTER commit (separate connection - avoids SQLite lock)
    sms_util.send_sms(verified_phone, f"RUCU Mikopo: maoni yako {ref} yamepokelewa. Tutakujulisha admin akijibu. Tumia password yako kufuatilia.", ref)
    out = {"message": "Your feedback has been successfully submitted.",
           "reference_number": ref,
           "note": "Keep this reference number if you want to track the progress of your submission. Login with registration number + password to follow responses.",
           "reg_verified": True,
           "phone_verified": True}
    return jsonify(out)


@app.route("/api/track/<ref>")
def track(ref):
    ref = ref.strip().upper()
    conn = db.get_db()
    fb = conn.execute(
        "SELECT f.*, c.name category_name FROM feedback f LEFT JOIN categories c ON c.id=f.category_id "
        "WHERE UPPER(f.reference_number)=?", (ref,)).fetchone()
    if not fb:
        conn.close()
        return jsonify({"error": "Reference number not found"}), 404
    fb = dict(fb)
    hist = [dict(r) for r in conn.execute(
        "SELECT old_status,new_status,created_at FROM status_history WHERE feedback_id=? ORDER BY id", (fb["id"],)).fetchall()]
    resp = [dict(r) for r in conn.execute(
        "SELECT response,created_at FROM responses WHERE feedback_id=? ORDER BY id DESC LIMIT 5", (fb["id"],)).fetchall()]
    conn.close()
    if fb["is_anonymous"]:
        for k in ("student_name", "registration_number", "programme", "phone", "email"):
            fb[k] = "Anonymous"
    for k in ("id", "assigned_to"):
        fb.pop(k, None)
    fb["history"] = hist
    fb["recent_responses"] = resp
    return jsonify(fb)


# ---------- student gate: reg -> TZ phone -> OTP -> password ----------
def normalize_tz_phone(raw: str):
    """Accept 06../07.., 255.., +255.. -> 255XXXXXXXXX or None."""
    if not raw:
        return None
    d = re.sub(r"\D", "", raw)
    if d.startswith("00"):
        d = d[2:]
    if len(d) == 10 and d.startswith("0"):
        d = "255" + d[1:]
    if len(d) == 12 and d.startswith("255") and d[3] in ("6", "7"):
        return d
    return None


def check_student_token(token: str):
    if not token:
        return None
    conn = db.get_db()
    t = conn.execute("SELECT * FROM student_tokens WHERE token=? AND expires_at>?",
                     (token, datetime.utcnow().isoformat())).fetchone()
    conn.close()
    return dict(t) if t else None


@app.route("/api/student/request-otp", methods=["POST"])
def student_request_otp():
    d = request.get_json(force=True)
    reg = (d.get("registration_number") or "").strip().upper()
    phone = normalize_tz_phone(d.get("phone") or "")
    if not reg:
        return jsonify({"error": "Registration number is required first."}), 400
    if not phone:
        return jsonify({"error": "Enter a valid Tanzanian number: 06../07.. or 255.........."}), 400
    conn = db.get_db()
    roster = conn.execute("SELECT full_name,programme,year_of_study FROM roster_students WHERE UPPER(registration_number)=?",
                          (reg,)).fetchone()
    if not roster:
        conn.close()
        return jsonify({"error": "Registration number not found. Contact admin to add your name to the roster."}), 404
    since = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    n = conn.execute("SELECT COUNT(*) c FROM otp_codes WHERE phone=? AND created_at>?",
                     (phone, since)).fetchone()["c"]
    if n >= 5:
        conn.close()
        return jsonify({"error": "Too many codes. Try again after an hour."}), 429
    code = f"{random.randint(100000, 999999)}"
    now = datetime.utcnow()
    conn.execute("INSERT INTO otp_codes (registration_number,phone,code,purpose,expires_at,created_at) VALUES (?,?,?,?,?,?)",
                 (reg, phone, code, "submit", (now + timedelta(minutes=10)).isoformat(), now.isoformat()))
    conn.commit(); conn.close()
    sms_util.send_sms(phone, f"RUCU Mikopo: OTP yako ni {code}. Inaisha dakika 10. Usimpe mtu.", "")
    out = {"ok": True, "message": "OTP sent via SMS.", "name": roster["full_name"]}
    if db.get_setting("sms_provider", "demo-log") == "demo-log":
        out["demo_otp"] = code
    return jsonify(out)


@app.route("/api/student/verify-otp", methods=["POST"])
def student_verify_otp():
    d = request.get_json(force=True)
    reg = (d.get("registration_number") or "").strip().upper()
    phone = normalize_tz_phone(d.get("phone") or "")
    code = (d.get("code") or "").strip()
    conn = db.get_db()
    row = conn.execute("SELECT * FROM otp_codes WHERE registration_number=? AND phone=? AND code=? AND verified=0 "
                       "ORDER BY id DESC LIMIT 1", (reg, phone, code)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Wrong code."}), 400
    if row["expires_at"] < datetime.utcnow().isoformat():
        conn.close()
        return jsonify({"error": "Code expired. Request a new one."}), 400
    conn.execute("UPDATE otp_codes SET verified=1 WHERE id=?", (row["id"],))
    token = secrets.token_hex(16)
    now = datetime.utcnow()
    conn.execute("INSERT INTO student_tokens (token,registration_number,phone,created_at,expires_at) VALUES (?,?,?,?,?)",
                 (token, reg, phone, now.isoformat(), (now + timedelta(hours=2)).isoformat()))
    roster = conn.execute("SELECT full_name,programme,year_of_study FROM roster_students WHERE UPPER(registration_number)=?",
                          (reg,)).fetchone()
    has_pw = conn.execute("SELECT id FROM student_accounts WHERE registration_number=?", (reg,)).fetchone()
    conn.commit(); conn.close()
    return jsonify({"ok": True, "token": token, "has_password": bool(has_pw), **dict(roster)})


@app.route("/api/student/set-password", methods=["POST"])
def student_set_password():
    d = request.get_json(force=True)
    t = check_student_token(d.get("token") or request.headers.get("X-Student-Token", ""))
    if not t:
        return jsonify({"error": "Verify OTP first."}), 401
    pw = d.get("password") or ""
    if len(pw) < 4:
        return jsonify({"error": "Password min 4 characters."}), 400
    conn = db.get_db()
    r = conn.execute("SELECT full_name FROM roster_students WHERE UPPER(registration_number)=?",
                     (t["registration_number"],)).fetchone()
    conn.execute("INSERT INTO student_accounts (registration_number,full_name,phone,password_hash,created_at) VALUES (?,?,?,?,?) "
                 "ON CONFLICT(registration_number) DO UPDATE SET password_hash=excluded.password_hash, phone=excluded.phone",
                 (t["registration_number"], r["full_name"] if r else "", t["phone"],
                  generate_password_hash(pw), datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return jsonify({"ok": True, "message": "Password saved. Use it + registration number to follow up."})


@app.route("/api/student/login", methods=["POST"])
def student_login():
    d = request.get_json(force=True)
    reg = (d.get("registration_number") or "").strip().upper()
    conn = db.get_db()
    acc = conn.execute("SELECT * FROM student_accounts WHERE registration_number=?", (reg,)).fetchone()
    if not acc or not check_password_hash(acc["password_hash"], d.get("password", "")):
        conn.close()
        return jsonify({"error": "Wrong registration number or password."}), 401
    token = secrets.token_hex(16)
    now = datetime.utcnow()
    conn.execute("INSERT INTO student_tokens (token,registration_number,phone,created_at,expires_at) VALUES (?,?,?,?,?)",
                 (token, reg, acc["phone"], now.isoformat(), (now + timedelta(hours=12)).isoformat()))
    conn.commit(); conn.close()
    return jsonify({"ok": True, "token": token})


@app.route("/api/student/profile")
def student_profile():
    t = check_student_token(request.headers.get("X-Student-Token", "") or request.args.get("token", ""))
    if not t:
        return jsonify({"error": "Login required."}), 401
    conn = db.get_db()
    r = conn.execute("SELECT full_name,programme,year_of_study FROM roster_students WHERE UPPER(registration_number)=?",
                     (t["registration_number"],)).fetchone()
    counts = conn.execute("SELECT status, COUNT(*) n FROM feedback WHERE UPPER(registration_number)=? GROUP BY status",
                          (t["registration_number"],)).fetchall()
    conn.close()
    return jsonify({"registration_number": t["registration_number"], "phone": t["phone"],
                    "profile": dict(r) if r else {},
                    "by_status": {x[0]: x[1] for x in counts}})


@app.route("/api/student/my-messages")
def student_my_messages():
    t = check_student_token(request.headers.get("X-Student-Token", "") or request.args.get("token", ""))
    if not t:
        return jsonify({"error": "Login required."}), 401
    conn = db.get_db()
    rows = [dict(r) for r in conn.execute(
        "SELECT message,reference_number,created_at FROM sms_log WHERE phone=? ORDER BY id DESC LIMIT 50",
        (t["phone"],)).fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/student/my-feedback")
def student_my_feedback():
    t = check_student_token(request.headers.get("X-Student-Token", "") or request.args.get("token", ""))
    if not t:
        return jsonify({"error": "Login required (registration number + password)."}), 401
    conn = db.get_db()
    rows = conn.execute(
        "SELECT f.reference_number,f.submission_type,c.name category,f.title,f.status,f.priority,f.created_at,"
        "(SELECT response FROM responses WHERE feedback_id=f.id ORDER BY id DESC LIMIT 1) latest_response "
        "FROM feedback f LEFT JOIN categories c ON c.id=f.category_id "
        "WHERE UPPER(f.registration_number)=? ORDER BY f.id DESC LIMIT 100", (t["registration_number"],)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/verify-code", methods=["POST"])
def verify_code():
    d = request.get_json(force=True)
    conn = db.get_db()
    r = conn.execute("SELECT * FROM verification_codes WHERE reference_number=? AND code=?",
                     ((d.get("reference_number") or "").upper(), d.get("code") or "")).fetchone()
    if not r:
        conn.close()
        return jsonify({"verified": False}), 404
    conn.execute("UPDATE verification_codes SET verified=1 WHERE id=?", (r["id"],))
    conn.commit(); conn.close()
    return jsonify({"verified": True})


# ---------- admin auth ----------
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    d = request.get_json(force=True)
    conn = db.get_db()
    u = conn.execute("SELECT * FROM users WHERE email=?", ((d.get("email") or "").strip().lower(),)).fetchone()
    if not u or u["status"] != "active" or not check_password_hash(u["password_hash"], d.get("password", "")):
        conn.close()
        return jsonify({"error": "Invalid credentials"}), 401
    tok = secrets.token_hex(24)
    conn.execute("INSERT INTO sessions (token,user_id,created_at) VALUES (?,?,?)",
                 (tok, u["id"], datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    resp = jsonify({"token": tok, "name": u["name"], "role": u["role"]})
    resp.set_cookie("rucu_token", tok, httponly=True, samesite="Lax")
    return resp


@app.route("/api/admin/me")
@require_admin
def admin_me(): return jsonify(g.admin)


@app.route("/api/admin/logout", methods=["POST"])
@require_admin
def admin_logout():
    tok = request.headers.get("Authorization", "").replace("Bearer ", "") or request.cookies.get("rucu_token", "")
    conn = db.get_db()
    conn.execute("DELETE FROM sessions WHERE token=?", (tok,)); conn.commit(); conn.close()
    return jsonify({"ok": True})


# ---------- admin data ----------
def sla_cutoff():
    try:
        days = int(db.get_setting("sla_days", "7"))
    except ValueError:
        days = 7
    return (datetime.utcnow() - timedelta(days=days)).isoformat()


def _range_filter(q, args, prefix="f"):
    rng = request.args.get("range", "year")
    now = datetime.utcnow()
    start = None
    if rng == "today": start = now.replace(hour=0, minute=0)
    elif rng == "week": start = now - timedelta(days=7)
    elif rng == "month": start = now - timedelta(days=30)
    elif rng == "semester": start = now - timedelta(days=180)
    if start:
        q += f" AND {prefix}.created_at>=?"
        args.append(start.isoformat())
    return q, args


@app.route("/api/admin/stats")
@require_admin
def admin_stats():
    conn = db.get_db()
    def c(sql, args=()):
        return conn.execute(sql, args).fetchone()[0]
    base = "FROM feedback f"
    q2, a2 = _range_filter("SELECT COUNT(*) " + base, [], "f")
    total = c(q2, a2)
    out = {
        "total": total,
        "new": c("SELECT COUNT(*) FROM feedback WHERE status='New'"),
        "under_review": c("SELECT COUNT(*) FROM feedback WHERE status='Under Review'"),
        "in_progress": c("SELECT COUNT(*) FROM feedback WHERE status='In Progress'"),
        "resolved": c("SELECT COUNT(*) FROM feedback WHERE status IN ('Resolved','Closed')"),
        "critical": c("SELECT COUNT(*) FROM feedback WHERE priority='Critical' AND status NOT IN ('Resolved','Closed')"),
        "avg_satisfaction": round(c("SELECT COALESCE(AVG(satisfaction_rating),0) FROM feedback WHERE satisfaction_rating>0") or 0, 2),
        "demo_count": c("SELECT COUNT(*) FROM feedback WHERE is_demo=1"),
        "overdue": c("SELECT COUNT(*) FROM feedback WHERE created_at<? AND status NOT IN ('Resolved','Closed','Rejected/Invalid')",
                     (sla_cutoff(),)),
        "appeals_open": c("SELECT COUNT(*) FROM appeals WHERE status='Open'"),
    }
    conn.close()
    return jsonify(out)


@app.route("/api/admin/analytics")
@require_admin
def analytics():
    conn = db.get_db()
    by_cat = conn.execute(
        "SELECT COALESCE(c.name,'Unspecified') n, COUNT(*) v FROM feedback f LEFT JOIN categories c ON c.id=f.category_id "
        "GROUP BY n ORDER BY v DESC").fetchall()
    by_status = conn.execute("SELECT status n, COUNT(*) v FROM feedback GROUP BY status").fetchall()
    by_type = conn.execute("SELECT submission_type n, COUNT(*) v FROM feedback GROUP BY n").fetchall()
    by_month = conn.execute("SELECT substr(created_at,1,7) n, COUNT(*) v FROM feedback GROUP BY n ORDER BY n DESC LIMIT 12").fetchall()
    by_sat = conn.execute("SELECT satisfaction_rating n, COUNT(*) v FROM feedback WHERE satisfaction_rating>0 GROUP BY n ORDER BY n").fetchall()
    by_pri = conn.execute("SELECT priority n, COUNT(*) v FROM feedback GROUP BY n").fetchall()
    conn.close()
    J = lambda rows: [{"label": r[0], "value": r[1]} for r in rows]
    return jsonify({"by_category": J(by_cat), "by_status": J(by_status), "by_type": J(by_type),
                    "by_month": J(reversed(by_month)), "by_satisfaction": J(by_sat), "by_priority": J(by_pri)})


@app.route("/api/admin/recurring")
@require_admin
def recurring():
    """Keyword-group recurring detection (transparent, admin confirms)."""
    conn = db.get_db()
    rows = conn.execute("SELECT title, description, category_id, is_demo FROM feedback").fetchall()
    groups: dict = {}
    import re as _re
    STOP = {"the", "na", "ya", "wa", "za", "ni", "kwa", "hii", "hiyo", "a", "an", "of", "in", "is", "to", "and", "de", "demo", "data"}
    for r in rows:
        words = [w.lower() for w in _re.findall(r"[a-zA-Z]{4,}", (r[0] or "") + " " + (r[1] or "")) if w.lower() not in STOP]
        for w in set(words[:8]):
            g = groups.setdefault(w, {"keyword": w, "count": 0})
            g["count"] += 1
    conn.close()
    out = sorted([g for g in groups.values() if g["count"] >= 3], key=lambda x: -x["count"])[:15]
    return jsonify({"note": "AI-GENERATED grouping candidate - admin must confirm before treating as official.",
                    "groups": out})


@app.route("/api/admin/feedback")
@require_admin
def admin_list():
    q = ("SELECT f.*, c.name category_name, u.name officer FROM feedback f "
         "LEFT JOIN categories c ON c.id=f.category_id LEFT JOIN users u ON u.id=f.assigned_to WHERE 1=1")
    args = []
    for key, col in (("status", "f.status"), ("category_id", "f.category_id"),
                     ("type", "f.submission_type"), ("priority", "f.priority")):
        if request.args.get(key):
            q += f" AND {col}=?"; args.append(request.args.get(key))
    if request.args.get("search"):
        q += " AND (f.title LIKE ? OR f.reference_number LIKE ? OR f.description LIKE ?)"
        s = f"%{request.args.get('search')}%"; args += [s, s, s]
    if request.args.get("demo") == "0":
        q += " AND f.is_demo=0"
    q += " ORDER BY f.id DESC LIMIT 300"
    conn = db.get_db()
    rows = conn.execute(q, args).fetchall()
    conn.close()
    out = []
    cutoff = sla_cutoff()
    for r in rows:
        d = dict(r)
        if d["is_anonymous"]:
            d["student_name"] = "Anonymous"
        d["overdue"] = bool(d["created_at"] < cutoff and d["status"] not in ("Resolved", "Closed", "Rejected/Invalid"))
        out.append(d)
    return jsonify(out)


@app.route("/api/admin/feedback/<ref>")
@require_admin
def admin_detail(ref):
    conn = db.get_db()
    fb = conn.execute("SELECT f.*, c.name category_name, u.name officer FROM feedback f "
                      "LEFT JOIN categories c ON c.id=f.category_id LEFT JOIN users u ON u.id=f.assigned_to "
                      "WHERE UPPER(f.reference_number)=?", (ref.upper(),)).fetchone()
    if not fb:
        conn.close(); return jsonify({"error": "Not found"}), 404
    fid = fb["id"]
    data = dict(fb)
    data["responses"] = [dict(r) for r in conn.execute(
        "SELECT r.*, u.name admin_name FROM responses r LEFT JOIN users u ON u.id=r.admin_id WHERE feedback_id=? ORDER BY id DESC", (fid,)).fetchall()]
    data["notes"] = [dict(r) for r in conn.execute(
        "SELECT n.*, u.name admin_name FROM internal_notes n LEFT JOIN users u ON u.id=n.admin_id WHERE feedback_id=? ORDER BY id DESC", (fid,)).fetchall()]
    data["history"] = [dict(r) for r in conn.execute(
        "SELECT h.*, u.name changed_by_name FROM status_history h LEFT JOIN users u ON u.id=h.changed_by WHERE feedback_id=? ORDER BY id", (fid,)).fetchall()]
    data["attachments"] = [dict(r) for r in conn.execute("SELECT * FROM attachments WHERE feedback_id=?", (fid,)).fetchall()]
    if data["is_anonymous"] and g.admin["role"] != "SUPER ADMIN":
        for k in ("student_name", "registration_number", "programme", "phone", "email"):
            data[k] = "Anonymous (protected)"
    conn.close()
    return jsonify(data)


@app.route("/api/admin/feedback/<ref>/status", methods=["PUT"])
@require_admin
def change_status(ref):
    new = (request.get_json(force=True).get("status") or "")
    if new not in STATUSES: return jsonify({"error": "Invalid status"}), 400
    conn = db.get_db()
    fb = conn.execute("SELECT * FROM feedback WHERE UPPER(reference_number)=?", (ref.upper(),)).fetchone()
    if not fb: conn.close(); return jsonify({"error": "Not found"}), 404
    now = datetime.utcnow().isoformat()
    conn.execute("UPDATE feedback SET status=?, updated_at=?, resolved_at=? WHERE id=?",
                 (new, now, now if new in ("Resolved", "Closed") else None, fb["id"]))
    conn.execute("INSERT INTO status_history (feedback_id,old_status,new_status,changed_by,created_at) VALUES (?,?,?,?,?)",
                 (fb["id"], fb["status"], new, g.admin["id"], now))
    conn.commit(); conn.close()
    if fb["phone"]:
        sms_util.send_sms(fb["phone"], f"RUCU Mikopo: ripoti yako {fb['reference_number']} sasa ni '{new}'.", fb["reference_number"])
    return jsonify({"ok": True, "status": new})


@app.route("/api/admin/feedback/<ref>/assign", methods=["PUT"])
@require_admin
def assign(ref):
    oid = request.get_json(force=True).get("officer_id")
    conn = db.get_db()
    fb = conn.execute("SELECT * FROM feedback WHERE UPPER(reference_number)=?", (ref.upper(),)).fetchone()
    if not fb: conn.close(); return jsonify({"error": "Not found"}), 404
    conn.execute("UPDATE feedback SET assigned_to=?, status='Assigned', updated_at=? WHERE id=?",
                 (oid, datetime.utcnow().isoformat(), fb["id"]))
    conn.execute("INSERT INTO status_history (feedback_id,old_status,new_status,changed_by,created_at) VALUES (?,?,?,?,?)",
                 (fb["id"], fb["status"], "Assigned", g.admin["id"], datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/feedback/<ref>/respond", methods=["POST"])
@require_admin
def respond(ref):
    msg = (request.get_json(force=True).get("response") or "").strip()
    if len(msg) < 3: return jsonify({"error": "Response too short"}), 400
    conn = db.get_db()
    fb = conn.execute("SELECT * FROM feedback WHERE UPPER(reference_number)=?", (ref.upper(),)).fetchone()
    if not fb: conn.close(); return jsonify({"error": "Not found"}), 404
    conn.execute("INSERT INTO responses (feedback_id,admin_id,response,created_at) VALUES (?,?,?,?)",
                 (fb["id"], g.admin["id"], msg, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    if fb["phone"]:
        sms_util.send_sms(fb["phone"], f"RUCU Mikopo: jibu jipya kwenye {fb['reference_number']}: {msg[:140]}", fb["reference_number"])
    return jsonify({"ok": True})


@app.route("/api/admin/feedback/<ref>/note", methods=["POST"])
@require_admin
def note(ref):
    msg = (request.get_json(force=True).get("note") or "").strip()
    if len(msg) < 2: return jsonify({"error": "Note too short"}), 400
    conn = db.get_db()
    fb = conn.execute("SELECT * FROM feedback WHERE UPPER(reference_number)=?", (ref.upper(),)).fetchone()
    if not fb: conn.close(); return jsonify({"error": "Not found"}), 404
    conn.execute("INSERT INTO internal_notes (feedback_id,admin_id,note,created_at) VALUES (?,?,?,?)",
                 (fb["id"], g.admin["id"], msg, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return jsonify({"ok": True})


# ---------- categories / users / settings ----------
@app.route("/api/admin/categories", methods=["GET", "POST"])
@require_admin
def cats():
    conn = db.get_db()
    if request.method == "GET":
        rows = [dict(r) for r in conn.execute("SELECT * FROM categories ORDER BY name").fetchall()]
        conn.close(); return jsonify(rows)
    if g.admin["role"] != "SUPER ADMIN":
        conn.close(); return jsonify({"error": "Super Admin only"}), 403
    d = request.get_json(force=True)
    try:
        conn.execute("INSERT INTO categories (name,description,active,created_at) VALUES (?,?,?,?)",
                     (d["name"].strip(), d.get("description", ""), 1 if d.get("active", True) else 0,
                      datetime.utcnow().isoformat()))
        conn.commit()
    except Exception as e:
        conn.close(); return jsonify({"error": str(e)}), 400
    conn.close(); return jsonify({"ok": True})


@app.route("/api/admin/categories/<int:cid>", methods=["PUT", "DELETE"])
@require_super
def cat_one(cid):
    conn = db.get_db()
    if request.method == "DELETE":
        conn.execute("UPDATE categories SET active=0 WHERE id=?", (cid,))
    else:
        d = request.get_json(force=True)
        conn.execute("UPDATE categories SET name=?, description=?, active=? WHERE id=?",
                     (d.get("name"), d.get("description", ""), 1 if d.get("active", True) else 0, cid))
    conn.commit(); conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/officers")
@require_admin
def officers():
    conn = db.get_db()
    rows = [dict(r) for r in conn.execute("SELECT id,name,email,role FROM users WHERE status='active'").fetchall()]
    conn.close(); return jsonify(rows)


@app.route("/api/admin/users", methods=["GET", "POST"])
@require_super
def users():
    conn = db.get_db()
    if request.method == "GET":
        rows = [dict(r) for r in conn.execute("SELECT id,name,email,role,status,created_at FROM users ORDER BY id").fetchall()]
        conn.close(); return jsonify(rows)
    d = request.get_json(force=True)
    try:
        conn.execute("INSERT INTO users (name,email,password_hash,role,status,created_at) VALUES (?,?,?,?,?,?)",
                     (d["name"], d["email"].strip().lower(), generate_password_hash(d["password"]),
                      d.get("role", "OFFICER"), "active", datetime.utcnow().isoformat()))
        conn.commit()
    except Exception as e:
        conn.close(); return jsonify({"error": str(e)}), 400
    conn.close(); return jsonify({"ok": True})


@app.route("/api/admin/settings", methods=["GET", "PUT"])
@require_admin
def settings():
    conn = db.get_db()
    if request.method == "GET":
        rows = conn.execute("SELECT key,value FROM system_settings").fetchall()
        conn.close(); return jsonify({r[0]: r[1] for r in rows})
    if g.admin["role"] != "SUPER ADMIN":
        conn.close(); return jsonify({"error": "Super Admin only"}), 403
    d = request.get_json(force=True)
    for k, v in d.items():
        conn.execute("INSERT INTO system_settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
    conn.commit(); conn.close()
    return jsonify({"ok": True})


# ---------- roster upload (Excel / CSV) ----------
@app.route("/api/admin/roster/upload", methods=["POST"])
@require_super
def roster_upload():
    file = request.files.get("file")
    if not file: return jsonify({"error": "No file"}), 400
    name = file.filename.lower()
    rows = []
    try:
        if name.endswith(".csv"):
            text = file.read().decode("utf-8-sig", errors="ignore")
            reader = csv.DictReader(io.StringIO(text))
            for r in reader: rows.append(r)
        elif name.endswith((".xlsx", ".xls")):
            from openpyxl import load_workbook
            wb = load_workbook(file, read_only=True)
            ws = wb.active
            headers = [str(c.value or "").strip().lower() for c in next(ws.rows)]
            for row in ws.iter_rows(min_row=2, values_only=True):
                rows.append(dict(zip(headers, [str(v or "").strip() for v in row])))
        else:
            return jsonify({"error": "Upload CSV or Excel (.xlsx). For PDF lists, export to Excel first."}), 400
    except Exception as e:
        return jsonify({"error": f"Could not parse file: {e}"}), 400
    conn = db.get_db()
    added = 0
    for r in rows:
        reg = (r.get("registration_number") or r.get("reg") or r.get("regno") or r.get("reg_no") or "").strip().upper()
        nm = (r.get("full_name") or r.get("name") or r.get("jina") or "").strip()
        if not reg or not nm: continue
        try:
            conn.execute("INSERT INTO roster_students (full_name,registration_number,programme,year_of_study,phone,created_at)"
                         " VALUES (?,?,?,?,?,?) ON CONFLICT(registration_number) DO UPDATE SET full_name=excluded.full_name,"
                         " programme=excluded.programme, year_of_study=excluded.year_of_study",
                         (nm, reg, r.get("programme", ""), r.get("year_of_study", r.get("year", "")), r.get("phone", ""),
                          datetime.utcnow().isoformat()))
            added += 1
        except Exception: pass
    conn.commit()
    total = conn.execute("SELECT COUNT(*) c FROM roster_students").fetchone()["c"]
    conn.close()
    return jsonify({"ok": True, "imported": added, "total_in_roster": total})


@app.route("/api/admin/roster")
@require_admin
def roster_list():
    conn = db.get_db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM roster_students ORDER BY id DESC LIMIT 500").fetchall()]
    conn.close(); return jsonify(rows)


@app.route("/api/admin/loan-recipients/upload", methods=["POST"])
@require_super
def loan_upload():
    from openpyxl import load_workbook
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file"}), 400
    name = file.filename.lower()
    rows = []
    try:
        if name.endswith(".csv"):
            reader = csv.DictReader(io.StringIO(file.read().decode("utf-8-sig", errors="ignore")))
            rows = list(reader)
        elif name.endswith((".xlsx", ".xls")):
            wb = load_workbook(file, read_only=True)
            ws = wb.active
            headers = [str(c.value or "").strip().lower() for c in next(ws.rows)]
            for row in ws.iter_rows(min_row=2, values_only=True):
                rows.append(dict(zip(headers, [str(v or "").strip() for v in row])))
        else:
            return jsonify({"error": "Upload CSV or Excel (.xlsx)."}), 400
    except Exception as e:
        return jsonify({"error": f"Could not parse file: {e}"}), 400
    conn = db.get_db()
    added = 0
    for r in rows:
        ph = normalize_tz_phone(r.get("phone") or r.get("simu") or r.get("namba") or "")
        nm = (r.get("full_name") or r.get("name") or r.get("jina") or "").strip()
        if not ph or not nm:
            continue
        conn.execute("INSERT INTO loan_recipients (full_name,registration_number,phone,amount,created_at) VALUES (?,?,?,?,?)",
                     (nm, (r.get("registration_number") or r.get("reg") or "").strip().upper(), ph,
                      r.get("amount") or r.get("kiasi") or "", datetime.utcnow().isoformat()))
        added += 1
    conn.commit()
    total = conn.execute("SELECT COUNT(*) c FROM loan_recipients").fetchone()["c"]
    conn.close()
    return jsonify({"ok": True, "imported": added, "total": total})


@app.route("/api/admin/loan-recipients")
@require_admin
def loan_list():
    conn = db.get_db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM loan_recipients ORDER BY id DESC LIMIT 500").fetchall()]
    total = conn.execute("SELECT COUNT(*) c FROM loan_recipients").fetchone()["c"]
    conn.close()
    return jsonify({"total": total, "recipients": rows})


@app.route("/api/admin/bulk-sms", methods=["POST"])
@require_admin
def bulk_sms():
    d = request.get_json(force=True)
    msg = (d.get("message") or "").strip()
    if len(msg) < 5:
        return jsonify({"error": "Message too short."}), 400
    conn = db.get_db()
    recs = conn.execute("SELECT phone, full_name FROM loan_recipients WHERE status='active'").fetchall()
    conn.close()
    sent = 0
    for r in recs:
        sms_util.send_sms(r["phone"], msg, "BULK")
        sent += 1
    return jsonify({"ok": True, "sent": sent,
                    "note": "Demo-log mode only logs. Connect Beem/Africa'sTalking in Settings for live delivery."})


@app.route("/api/admin/sms-log")
@require_admin
def sms_log():
    conn = db.get_db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM sms_log ORDER BY id DESC LIMIT 100").fetchall()]
    conn.close(); return jsonify(rows)


# ---------- demo data (DEMO: RU/COURSE/YEAR/NUMBER e.g. RU/BAFIT/2024/007) ----------
DEMO_ROSTER = [
    ("Amina Juma", "RU/BAFIT/2024/007", "BAFIT", "Year 2", "0712000007"),
    ("Paulo Mkenya", "RU/BAFIT/2024/012", "BAFIT", "Year 2", "0712000012"),
    ("Neema Kilonzo", "RU/BIT/2023/045", "BIT", "Year 3", "0755000045"),
    ("Juma Said", "RU/BBA/2024/101", "BBA", "Year 1", "0768000101"),
    ("Grace Mushi", "RU/LLB/2022/033", "LLB", "Year 4", "0629000033"),
    ("Baraka Temu", "RU/BED/2024/088", "BEd", "Year 2", "0744000088"),
    ("Rehema Ally", "RU/BAFIT/2023/019", "BAFIT", "Year 3", "0713000019"),
    ("Moses Kweka", "RU/BIT/2024/054", "BIT", "Year 1", "0690000054"),
]

DEMO_LOANS = [
    ("Amina Juma", "RU/BAFIT/2024/007", "0712000007", "2500000"),
    ("Neema Kilonzo", "RU/BIT/2023/045", "0755000045", "2500000"),
    ("Juma Said", "RU/BBA/2024/101", "0768000101", "1800000"),
    ("Grace Mushi", "RU/LLB/2022/033", "0629000033", "2500000"),
    ("Baraka Temu", "RU/BED/2024/088", "0744000088", "1800000"),
]


@app.route("/api/admin/seed-demo", methods=["POST"])
@require_super
def seed_demo():
    conn = db.get_db()
    now = datetime.utcnow()
    for nm, reg, prog, yr, ph in DEMO_ROSTER:
        conn.execute("INSERT INTO roster_students (full_name,registration_number,programme,year_of_study,phone,created_at)"
                     " VALUES (?,?,?,?,?,?) ON CONFLICT(registration_number) DO UPDATE SET full_name=excluded.full_name",
                     (nm, reg, prog, yr, ph, now.isoformat()))
    for nm, reg, ph, amt in DEMO_LOANS:
        conn.execute("DELETE FROM loan_recipients WHERE phone=?", (ph,))
        conn.execute("INSERT INTO loan_recipients (full_name,registration_number,phone,amount,created_at) VALUES (?,?,?,?,?)",
                     (nm, reg, ph, amt, now.isoformat()))
    # demo student login: RU/BAFIT/2024/007 / demo1234
    conn.execute("INSERT INTO student_accounts (registration_number,full_name,phone,password_hash,created_at) VALUES (?,?,?,?,?) "
                 "ON CONFLICT(registration_number) DO UPDATE SET password_hash=excluded.password_hash",
                 ("RU/BAFIT/2024/007", "Amina Juma", "0712000007",
                  generate_password_hash("demo1234"), now.isoformat()))
    conn.execute("DELETE FROM feedback WHERE is_demo=1")
    cats = conn.execute("SELECT id,name FROM categories").fetchall()
    loan_cat = next((c[0] for c in cats if "Loan" in c[1]), cats[0][0])
    samples = [("Complaint", "BOOM imechelewa mwezi huu (DEMO)", "BOOM haijaingia hadi tarehe 15, tunashindwa kulipia chakula. [DEMO DATA]", "High", "RU/BAFIT/2024/007", "Amina Juma"),
               ("Challenge/Problem", "Ada haijaonekana kwenye akaunti (DEMO)", "HELSB walisema wametuma lakini chuo hakijapokea. [DEMO DATA]", "Critical", "RU/BIT/2023/045", "Neema Kilonzo"),
               ("Suggestion", "Ongezeni dirisha la malipo ya mkopo (DEMO)", "Folatini moja husababisha foleni ndefu siku za BOOM. [DEMO DATA]", "Medium", "RU/BBA/2024/101", "Juma Said"),
               ("Praise/Appreciation", "Asante BOOM ya awamu iliyopita (DEMO)", "Iliingia kwa wakati, asanteni sana. [DEMO DATA]", "Low", "RU/LLB/2022/033", "Grace Mushi"),
               ("Complaint", "Jina langu halipo kwenye orodha ya mkopo (DEMO)", "Nimekosa awamu hii bila sababu. [DEMO DATA]", "High", "RU/BED/2024/088", "Baraka Temu")]
    for i, (t, title, desc, pri, reg, nm) in enumerate(samples):
        ref = f"RUCU-2026-{900001 + i:06d}"
        dt = (now - timedelta(days=i * 2)).isoformat()
        conn.execute("""INSERT OR IGNORE INTO feedback (reference_number,submission_type,category_id,title,description,
        satisfaction_rating,priority,is_anonymous,student_name,registration_number,phone,reg_verified,phone_verified,
        status,is_demo,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (ref, t, loan_cat, f"{title} [DEMO {i}]", desc,
                      (i % 5) + 1, pri, 0, nm, reg, "0712000000", 1, 1,
                      "Resolved" if i % 2 else "Under Review", 1, dt, dt))
    conn.commit(); conn.close()
    conn = db.get_db()
    conn.execute("DELETE FROM announcements WHERE title LIKE '%DEMO%'")
    conn.execute("INSERT INTO announcements (title,message,audience,active,created_at) VALUES (?,?,?,?,?)",
                 ("BOOM ya Januari imeingia (DEMO)", "Wanafunzi wote waangalie akaunti zao. [DEMO DATA]",
                  "all", 1, now.isoformat()))
    conn.commit(); conn.close()
    return jsonify({"ok": True, "note": "Demo roster (8), loan list (5), student login RU/BAFIT/2024/007/demo1234, 5 demo feedback."})


@app.route("/api/admin/clear-demo", methods=["POST"])
@require_super
def clear_demo():
    conn = db.get_db()
    conn.execute("DELETE FROM feedback WHERE is_demo=1")
    conn.execute("DELETE FROM student_accounts WHERE registration_number='RU/BAFIT/2024/007'")
    for _, reg, _, _, _ in DEMO_ROSTER:
        conn.execute("DELETE FROM roster_students WHERE registration_number=?", (reg,))
    conn.execute("DELETE FROM loan_recipients")
    conn.execute("DELETE FROM announcements WHERE title LIKE '%DEMO%'")
    conn.execute("DELETE FROM poll_votes")
    conn.commit(); conn.close()
    return jsonify({"ok": True})


# ---------- reports ----------
def _report_rows():
    conn = db.get_db()
    stats = {}
    stats["total"] = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    stats["by_category"] = conn.execute(
        "SELECT COALESCE(c.name,'Unspecified'), COUNT(*) FROM feedback f LEFT JOIN categories c ON c.id=f.category_id "
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 10").fetchall()
    stats["by_status"] = conn.execute("SELECT status, COUNT(*) FROM feedback GROUP BY 1").fetchall()
    stats["avg_sat"] = conn.execute("SELECT COALESCE(AVG(satisfaction_rating),0) FROM feedback WHERE satisfaction_rating>0").fetchone()[0]
    stats["critical"] = conn.execute("SELECT COUNT(*) FROM feedback WHERE priority='Critical' AND status NOT IN ('Resolved','Closed')").fetchone()[0]
    stats["demo"] = conn.execute("SELECT COUNT(*) FROM feedback WHERE is_demo=1").fetchone()[0]
    conn.close()
    return stats


@app.route("/api/admin/report")
@require_admin
def report():
    fmt = request.args.get("format", "json")
    rtype = request.args.get("type", "Academic Year Report")
    approved_by = (request.args.get("approved_by") or "").strip()
    generated_by = g.admin["name"]
    s = _report_rows()
    uni = db.get_setting("university_name"); ay = db.get_setting("academic_year")
    if fmt == "json":
        return jsonify({"title": f"RUCU STUDENT CHALLENGES REPORT — {rtype}", "university": uni,
                        "academic_year": ay, "generated": datetime.utcnow().isoformat(),
                        "generated_by": generated_by, "approved_by": approved_by,
                        "demo_included": s["demo"],
                        "total": s["total"], "avg_satisfaction": round(s["avg_sat"] or 0, 2),
                        "critical_open": s["critical"],
                        "by_category": [{"category": r[0], "count": r[1]} for r in s["by_category"]],
                        "by_status": [{"status": r[0], "count": r[1]} for r in s["by_status"]]})
    if fmt == "excel":
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.title = "RUCU Report"
        ws.append([uni]); ws.append([f"{rtype} — {ay}"]); ws.append([f"Generated {datetime.utcnow().isoformat()} by {generated_by}"])
        ws.append([f"Approved by: {approved_by or '-'}"])
        ws.append([]); ws.append(["Total reports", s["total"]])
        ws.append(["Avg satisfaction", round(s["avg_sat"] or 0, 2)]); ws.append(["Critical open", s["critical"]])
        ws.append([]); ws.append(["Category", "Count"])
        for r in s["by_category"]: ws.append([r[0], r[1]])
        ws.append([]); ws.append(["Status", "Count"])
        for r in s["by_status"]: ws.append([r[0], r[1]])
        buf = io.BytesIO(); wb.save(buf); buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=f"RUCU_report_{rtype}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    # PDF
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4; y = h - 60
    c.setFont("Helvetica-Bold", 16); c.drawString(50, y, uni); y -= 22
    c.setFont("Helvetica", 12); c.drawString(50, y, f"{rtype} — Academic Year {ay}"); y -= 20
    c.drawString(50, y, f"Generated: {datetime.utcnow().isoformat()[:16]} by {generated_by}"); y -= 16
    c.drawString(50, y, f"Approved by: {approved_by or '-'}"); y -= 16
    if s["demo"]:
        c.drawString(50, y, f"NOTE: includes {s['demo']} DEMO records - clear before official use."); y -= 16
    y -= 8
    c.setFont("Helvetica", 11)
    for line in [f"Total reports: {s['total']}", f"Average satisfaction: {round(s['avg_sat'] or 0,2)}/5",
                 f"Critical open: {s['critical']}", "", "Top reported categories:"]:
        c.drawString(50, y, line); y -= 16
    for cat, n in s["by_category"]:
        c.drawString(70, y, f"- {cat}: {n}"); y -= 15
        if y < 80: c.showPage(); y = h - 60
    y -= 10; c.drawString(50, y, "Status breakdown:"); y -= 16
    for st, n in s["by_status"]:
        c.drawString(70, y, f"- {st}: {n}"); y -= 15
    y -= 16; c.drawString(50, y, "Recommendations: focus on top categories and unresolved critical issues.")
    y -= 16; c.setFont("Helvetica-Oblique", 9)
    c.drawString(50, y, "Based on the submitted data. Developed by Paulo Mkenya (c) Ruaha Catholic University.")
    c.showPage(); c.save(); buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"RUCU_report_{rtype}.pdf", mimetype="application/pdf")


# ---------- announcements ----------
@app.route("/api/announcements")
def announcements_public():
    conn = db.get_db()
    rows = [dict(r) for r in conn.execute(
        "SELECT id,title,message,created_at FROM announcements WHERE active=1 ORDER BY id DESC LIMIT 20").fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/admin/announcements", methods=["GET", "POST"])
@require_admin
def announcements_admin():
    conn = db.get_db()
    if request.method == "GET":
        rows = [dict(r) for r in conn.execute("SELECT * FROM announcements ORDER BY id DESC LIMIT 100").fetchall()]
        conn.close()
        return jsonify(rows)
    d = request.get_json(force=True)
    if not (d.get("title") or "").strip() or not (d.get("message") or "").strip():
        conn.close()
        return jsonify({"error": "Title and message required."}), 400
    conn.execute("INSERT INTO announcements (title,message,audience,active,created_by,created_at) VALUES (?,?,?,?,?,?)",
                 (d["title"].strip(), d["message"].strip(), d.get("audience", "all"), 1,
                  g.admin["id"], datetime.utcnow().isoformat()))
    conn.commit()
    notify = bool(d.get("notify_sms"))
    n_loan = 0
    if notify:
        recs = conn.execute("SELECT phone FROM loan_recipients WHERE status='active'").fetchall()
        n_loan = len(recs)
    conn.close()
    if notify:
        for r in recs:
            sms_util.send_sms(r["phone"], f"RUCU Tangazo: {d['title'].strip()} - {d['message'].strip()[:140]}", "NOTICE")
    return jsonify({"ok": True, "sms_sent": n_loan if notify else 0})


@app.route("/api/admin/announcements/<int:aid>", methods=["PUT", "DELETE"])
@require_super
def announcement_one(aid):
    conn = db.get_db()
    if request.method == "DELETE":
        conn.execute("UPDATE announcements SET active=0 WHERE id=?", (aid,))
    else:
        d = request.get_json(force=True)
        conn.execute("UPDATE announcements SET title=?, message=?, audience=?, active=? WHERE id=?",
                     (d.get("title"), d.get("message"), d.get("audience", "all"),
                      1 if d.get("active", True) else 0, aid))
    conn.commit(); conn.close()
    return jsonify({"ok": True})


# ---------- semester poll ----------
@app.route("/api/poll")
def poll_active():
    conn = db.get_db()
    p = conn.execute("SELECT id,question,semester FROM polls WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    if not p:
        conn.close()
        return jsonify({"active": False})
    agg = conn.execute("SELECT rating, COUNT(*) n FROM poll_votes WHERE poll_id=? GROUP BY rating ORDER BY rating",
                       (p["id"],)).fetchall()
    total = sum(r[1] for r in agg)
    avg = round(sum(r[0] * r[1] for r in agg) / total, 2) if total else 0
    conn.close()
    return jsonify({"active": True, "id": p["id"], "question": p["question"], "semester": p["semester"],
                    "total": total, "average": avg,
                    "breakdown": [{"rating": r[0], "votes": r[1]} for r in agg]})


@app.route("/api/poll/vote", methods=["POST"])
def poll_vote():
    d = request.get_json(force=True)
    t = check_student_token(d.get("token") or request.headers.get("X-Student-Token", ""))
    if not t:
        return jsonify({"error": "Login/verify first (My Space)."}), 401
    try:
        rating = int(d.get("rating", 0))
    except (TypeError, ValueError):
        rating = 0
    if rating < 1 or rating > 5:
        return jsonify({"error": "Rating 1-5."}), 400
    conn = db.get_db()
    p = conn.execute("SELECT id FROM polls WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    if not p:
        conn.close()
        return jsonify({"error": "No active poll."}), 404
    try:
        conn.execute("INSERT INTO poll_votes (poll_id,registration_number,rating,created_at) VALUES (?,?,?,?)",
                     (p["id"], t["registration_number"], rating, datetime.utcnow().isoformat()))
        conn.commit()
    except Exception:
        conn.close()
        return jsonify({"error": "Ulishapiga kura (one vote per student)."}), 409
    conn.close()
    return jsonify({"ok": True, "message": "Asante kwa kura yako!"})


@app.route("/api/admin/polls", methods=["GET", "POST"])
@require_super
def polls_admin():
    conn = db.get_db()
    if request.method == "GET":
        rows = [dict(r) for r in conn.execute("SELECT * FROM polls ORDER BY id DESC LIMIT 20").fetchall()]
        conn.close()
        return jsonify(rows)
    d = request.get_json(force=True)
    conn.execute("UPDATE polls SET active=0")
    conn.execute("INSERT INTO polls (question,semester,active,created_at) VALUES (?,?,1,?)",
                 (d["question"], d.get("semester", ""), datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return jsonify({"ok": True})


# ---------- appeals (rufani) ----------
@app.route("/api/student/appeal", methods=["POST"])
def student_appeal():
    d = request.get_json(force=True)
    t = check_student_token(d.get("token") or request.headers.get("X-Student-Token", ""))
    if not t:
        return jsonify({"error": "Login required."}), 401
    reason = (d.get("reason") or "").strip()
    if len(reason) < 10:
        return jsonify({"error": "Eleza sababu (min 10 characters)."}), 400
    conn = db.get_db()
    fb = conn.execute("SELECT id, status FROM feedback WHERE UPPER(reference_number)=? AND UPPER(registration_number)=?",
                      ((d.get("reference_number") or "").upper(), t["registration_number"])).fetchone()
    if not fb:
        conn.close()
        return jsonify({"error": "Feedback not found."}), 404
    if fb["status"] not in ("Resolved", "Closed", "Rejected/Invalid"):
        conn.close()
        return jsonify({"error": "Rufaa ni kwa maoni yaliyofungwa tu (Resolved/Closed)."}), 400
    now = datetime.utcnow().isoformat()
    conn.execute("INSERT INTO appeals (feedback_id,registration_number,reason,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                 (fb["id"], t["registration_number"], reason, "Open", now, now))
    conn.commit(); conn.close()
    return jsonify({"ok": True, "message": "Rufaa imepokelewa. Admin ataipitia upya."})


@app.route("/api/student/appeals")
def student_appeals():
    t = check_student_token(request.headers.get("X-Student-Token", "") or request.args.get("token", ""))
    if not t:
        return jsonify({"error": "Login required."}), 401
    conn = db.get_db()
    rows = [dict(r) for r in conn.execute(
        "SELECT a.*, f.reference_number FROM appeals a JOIN feedback f ON f.id=a.feedback_id "
        "WHERE a.registration_number=? ORDER BY a.id DESC", (t["registration_number"],)).fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/admin/appeals")
@require_admin
def appeals_admin():
    conn = db.get_db()
    rows = [dict(r) for r in conn.execute(
        "SELECT a.*, f.reference_number, f.title FROM appeals a JOIN feedback f ON f.id=a.feedback_id "
        "ORDER BY a.id DESC LIMIT 200").fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/admin/appeals/<int:aid>/resolve", methods=["PUT"])
@require_admin
def appeal_resolve(aid):
    d = request.get_json(force=True)
    status = d.get("status", "Closed")
    if status not in ("Under Review", "Closed"):
        return jsonify({"error": "Invalid."}), 400
    conn = db.get_db()
    a = conn.execute("SELECT * FROM appeals WHERE id=?", (aid,)).fetchone()
    if not a:
        conn.close()
        return jsonify({"error": "Not found."}), 404
    now = datetime.utcnow().isoformat()
    conn.execute("UPDATE appeals SET status=?, admin_response=?, updated_at=? WHERE id=?",
                 (status, d.get("admin_response", ""), now, aid))
    if status == "Under Review":
        conn.execute("UPDATE feedback SET status='Under Review', updated_at=? WHERE id=?", (now, a["feedback_id"]))
        conn.execute("INSERT INTO status_history (feedback_id,old_status,new_status,changed_by,created_at) VALUES (?,?,?,?,?)",
                     (a["feedback_id"], "Resolved", "Under Review", g.admin["id"], now))
    conn.commit()
    fb = conn.execute("SELECT reference_number, phone FROM feedback WHERE id=?", (a["feedback_id"],)).fetchone()
    conn.close()
    if fb and fb["phone"]:
        sms_util.send_sms(fb["phone"], f"RUCU Mikopo: rufaa yako {fb['reference_number']} sasa ni '{status}'.", fb["reference_number"])
    return jsonify({"ok": True})


# ---------- public RUCUSO AI (students, homepage widget) ----------
def _lang_sw(text):
    return any(m in text.lower() for m in
               ["nini", "nifanye", "nianzie", "wapi", "gani", "ngapi", "vipi", "jinsi",
                "naomba", "nisaidie", "mkopo", "kuwasilisha", "kufuatilia", "jibu",
                "yangu", "yako", "yake", "zetu", "tuma", "maoni", "uliza", "omba"])


STUDENT_AI_RULES = [
    (["otp", "code", "namba ya siri", "verification"],
     "sw", "OTP ni namba 6 inayotumwa kwa SMS baada ya kuweka namba yako ya simu. Ikiisha (dakika 10) omba nyingine. Hakikisha namba ni ya TZ: 06../07.. au 255..."),
    (["otp", "code", "verification"],
     "en", "OTP is the 6-digit number sent by SMS after entering your phone. It expires in 10 minutes — request a new one. Use a TZ number: 06../07.. or 255..."),
    (["track", "fuatilia", "kufuatilia", "reference", "majibu"],
     "sw", "Kufuatilia: Fungua Fuatilia \u2192 weka reference number yako (mf. RUCU-2026-000001), au ingia Kwangu (My Space) na reg + password kuona maoni yako yote na majibu ya admin."),
    (["track", "reference"],
     "en", "Tracking: open Track \u2192 enter your reference number (e.g. RUCU-2026-000001), or log in to My Space with reg + password to see everything plus admin responses."),
    (["boom", "ada", "helsb", "mkopo", "loan", "pesa"],
     "sw", "Taarifa za BOOM/ada zinatangazwa kwenye Matangazo ya ukurasa huu. Wapokea mkopo hupata SMS BOOM ikiingia. Kama hujapata ilhali wenzako wamepata, ripoti changamoto kupitia Tuma."),
    (["boom", "loan", "helsb", "fees"],
     "en", "BOOM/fee updates are posted under Announcements on this page. Loan recipients get an SMS when BOOM arrives. If others received it and you did not, report via Submit."),
    (["appeal", "rufaa", "rufani", "kutoridhika"],
     "sw", "Rufaa: ukimaliza na hujaridhika na jibu, ingia Kwangu \u2192 sehemu ya Rufaa \u2192 weka reference na sababu. Admin ataipitia upya."),
    (["appeal"],
     "en", "Appeal: if you are not satisfied with a closed response, log in to My Space \u2192 Appeals \u2192 enter the reference and reason. An admin will review it again."),
    (["anonymous", "bila jina", "siri", "anonymous"],
     "sw", "Ndiyo, unaweza tuma bila jina kuonekana (anonymous). Lakini bado lazima u-verify OTP \u2014 namba yako haitoonshwa kwa admin wa kawaida."),
    (["anonymous"],
     "en", "Yes, you can submit anonymously. You must still verify OTP \u2014 your number is hidden from normal admins."),
    (["password", "nywila", "sahau", "kuingia", "login"],
     "sw", "Password unaweka wakati wa kutuma maoni (hatua ya 3). Inatumika kuingia Kwangu (My Space). Ukisahau, tuma maoni mapya na uweke password mpya \u2014 au uliza admin."),
    (["password", "login", "forgot"],
     "en", "You set the password when submitting (step 3). It logs you into My Space. If forgotten, submit again with a new password \u2014 or ask an admin."),
    (["submit", "tuma", "wasilisha", "fomu", "maoni"],
     "sw", "Hatua: 1) Tuma \u2192 weka registration number (mf. RU/BAFIT/2024/007). 2) Weka namba ya TZ (06/07/255) \u2192 utapokea OTP kwa SMS \u2192 weka OTP. 3) Jaza fomu ya mikopo, weka password, bonyeza Tuma. Utapata reference kama RUCU-2026-000001."),
    (["submit", "form", "feedback", "how"],
     "en", "Steps: 1) Submit \u2192 enter registration number (e.g. RU/BAFIT/2024/007). 2) Enter TZ number (06/07/255) \u2192 you receive an SMS OTP \u2192 enter it. 3) Fill the loans form, set a password, press Submit. You get a reference like RUCU-2026-000001."),
]
@app.route("/api/ask", methods=["POST"])
def public_ask():
    d = request.get_json(force=True) if request.data else {}
    q = (d.get("question") or "").strip()
    if len(q) < 3:
        return jsonify({"answer": "Uliza swali kuhusu kutuma maoni, OTP, kufuatilia au mikopo. / Ask about submitting, OTP, tracking or loans."}), 400
    ip = request.remote_addr or "?"
    conn = db.get_db()
    since = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    n = conn.execute("SELECT COUNT(*) c FROM ai_log WHERE ip=? AND created_at>?", (ip, since)).fetchone()[0]
    if n >= 20:
        conn.close()
        return jsonify({"answer": "Umeuliza sana. Subiri kidogo. / Too many questions, wait a bit."}), 429
    conn.execute("INSERT INTO ai_log (ip, question, created_at) VALUES (?,?,?)",
                 (ip, q[:500], datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    sw = _lang_sw(q)
    ql = q.lower()
    for keywords, lang, answer in STUDENT_AI_RULES:
        if lang == ("sw" if sw else "en") and any(k in ql for k in keywords):
            return jsonify({"answer": answer})
    # fallback: try other language rules
    for keywords, lang, answer in STUDENT_AI_RULES:
        if any(k in ql for k in keywords):
            return jsonify({"answer": answer})
    if sw:
        return jsonify({"answer": "Mimi ni RUCUSO AI. Naweza kukusaidia: kutuma maoni, OTP/SMS, kufuatilia ripoti, password, BOOM/ada, rufaa. Uliza mfano: 'Natuma vipi maoni?'."})
    return jsonify({"answer": "I am RUCUSO AI. I can help with: submitting feedback, OTP/SMS, tracking reports, passwords, BOOM/fees, appeals. Try: 'How do I submit feedback?'."})


# ---------- RUCUSO AI ----------
@app.route("/api/ai/ask", methods=["POST"])
@require_admin
def ai_ask():
    d = request.get_json(force=True)
    out = rucuso_ai.ask(d.get("question", ""), d.get("page", ""))
    return jsonify(out)


init()

if __name__ == "__main__":
    init()
    app.run(host="0.0.0.0", port=5000, debug=True)
