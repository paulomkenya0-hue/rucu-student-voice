"""RUCUSO AI - rule-based assistant using REAL database statistics.

Never invents numbers. Every numeric claim is labelled DATABASE FACT
queried live from SQLite. Everything else is labelled AI-GENERATED SUMMARY.
Bilingual: answers in the language the admin used (EN/SW detection).
"""
import sqlite3
import database as db
from datetime import datetime, timedelta

PAGE_GUIDES = {
    "add_category": {
        "en": ["You are on Add Category.", "1. Enter category name (e.g. 'Transport').",
               "2. Enter a short description.", "3. Leave Active ON.",
               "4. Click Save. It appears in the student form immediately."],
        "sw": ["Uko kwenye Add Category (Ongeza Kategoria).",
               "1. Weka jina la category. Mfano: 'Usafiri'.",
               "2. Weka description fupi.", "3. Acha Active ikiwa ON.",
               "4. Bonyeza Save. Itaonekana kwenye fomu ya mwanafunzi mara moja."],
    },
    "dashboard": {
        "en": ["Start here: 1) Check TOTAL vs RESOLVED.", "2) Open Critical Issues first.",
               "3) Filter by category (e.g. ICT/Internet).", "4) Assign each New issue to an officer.",
               "5) Change status as you work: New > Under Review > In Progress > Resolved."],
        "sw": ["Anzia hapa: 1) Angalia TOTAL dhidi ya RESOLVED.",
               "2) Fungua Critical Issues kwanza.", "3) Chuja kwa category (mf. ICT/Internet).",
               "4) Assign kila issue New kwa officer.", "5) Badilisha status unavyofanya kazi."],
    },
}


def _is_swahili(text: str) -> bool:
    sw_markers = ["nifanye", "nini", "hapa", "nijaze", "nianzie", "nipe", "changamoto",
                  "ngapi", "zipi", "gani", "nisaidie", "jinsi", "wapi"]
    t = text.lower()
    return any(m in t for m in sw_markers)


def _stats() -> dict:
    conn = db.get_db()
    def q(sql, args=()):
        row = conn.execute(sql, args).fetchone()
        return row[0] if row else 0
    total = q("SELECT COUNT(*) FROM feedback WHERE is_demo=0")
    new = q("SELECT COUNT(*) FROM feedback WHERE status='New' AND is_demo=0")
    review = q("SELECT COUNT(*) FROM feedback WHERE status='Under Review' AND is_demo=0")
    prog = q("SELECT COUNT(*) FROM feedback WHERE status='In Progress' AND is_demo=0")
    resolved = q("SELECT COUNT(*) FROM feedback WHERE status IN ('Resolved','Closed') AND is_demo=0")
    critical = q("SELECT COUNT(*) FROM feedback WHERE priority='Critical' AND status NOT IN ('Resolved','Closed') AND is_demo=0")
    avg = conn.execute("SELECT AVG(satisfaction_rating) FROM feedback WHERE satisfaction_rating>0 AND is_demo=0").fetchone()[0]
    top_cats = conn.execute(
        "SELECT c.name, COUNT(f.id) n FROM feedback f LEFT JOIN categories c ON c.id=f.category_id "
        "WHERE f.is_demo=0 GROUP BY c.name ORDER BY n DESC LIMIT 5").fetchall()
    unresolved_by_cat = conn.execute(
        "SELECT c.name, COUNT(f.id) n FROM feedback f LEFT JOIN categories c ON c.id=f.category_id "
        "WHERE f.status NOT IN ('Resolved','Closed') AND f.is_demo=0 GROUP BY c.name ORDER BY n DESC LIMIT 5").fetchall()
    oldest = conn.execute(
        "SELECT reference_number, title, status, created_at FROM feedback "
        "WHERE status NOT IN ('Resolved','Closed','Rejected/Invalid') AND is_demo=0 "
        "ORDER BY created_at ASC LIMIT 5").fetchall()
    conn.close()
    return {"total": total, "new": new, "review": review, "prog": prog,
            "resolved": resolved, "critical": critical,
            "avg": round(avg, 2) if avg else 0,
            "top_cats": [(r[0] or "Unspecified", r[1]) for r in top_cats],
            "unresolved_by_cat": [(r[0] or "Unspecified", r[1]) for r in unresolved_by_cat],
            "oldest": [dict(r) for r in oldest]}


def ask(question: str, page: str = "") -> dict:
    sw = _is_swahili(question)
    lang = "sw" if sw else "en"
    s = _stats()
    ql = question.lower()
    fact = (f"DATABASE FACT — Total: {s['total']}, New: {s['new']}, "
            f"Under Review: {s['review']}, In Progress: {s['prog']}, "
            f"Resolved/Closed: {s['resolved']}, Critical open: {s['critical']}, "
            f"Avg satisfaction: {s['avg']}/5.")

    # Beginner / how-to intents
    if any(k in ql for k in ["nijaze nini", "nifanye nini", "add category", "ongeza category"]):
        steps = PAGE_GUIDES["add_category"][lang]
        head = "RUCUSO AI — hatua kwa hatua:" if sw else "RUCUSO AI — step by step:"
        return {"answer": head + "\n" + "\n".join(steps), "fact": None, "lang": lang}
    if any(k in ql for k in ["nianzie wapi", "dashboard ina maana", "where do i start", "what does this dashboard"]):
        steps = PAGE_GUIDES["dashboard"][lang]
        extra = ("\n\n" + fact) if True else ""
        return {"answer": ("Anzia hapa:\n" if sw else "Start here:\n") + "\n".join(steps) + extra,
                "fact": fact, "lang": lang}
    if any(k in ql for k in ["complaints za ict", "ict complaints", "kuona complaints", "filter", "chuja"]):
        a = ("1. Nenda Issues.\n2. Kwenye Category chagua 'ICT/Internet'.\n3. Kwenye Type chagua 'Complaint'.\n4. Bonyeza Filter."
             if sw else "1. Go to Issues.\n2. Set Category to 'ICT/Internet'.\n3. Set Type to 'Complaint'.\n4. Click Filter.")
        return {"answer": a, "fact": fact, "lang": lang}
    if any(k in ql for k in ["report ya mwezi", "monthly report", "tengeneza report", "generate report", "export"]):
        a = ("1. Nenda Reports.\n2. Chagua Monthly Report + mwezi.\n3. Bonyeza Generate.\n4. Export PDF au Excel."
             if sw else "1. Go to Reports.\n2. Choose Monthly Report + month.\n3. Click Generate.\n4. Export PDF or Excel.")
        return {"answer": a, "fact": fact, "lang": lang}
    if any(k in ql for k in ["badilisha status", "change status"]):
        a = ("1. Fungua issue.\n2. Chagua status mpya.\n3. Bonyeza Update Status. Historia itahifadhiwa."
             if sw else "1. Open the issue.\n2. Pick the new status.\n3. Click Update Status. History is saved.")
        return {"answer": a, "fact": fact, "lang": lang}
    if any(k in ql for k in ["assign"]):
        a = ("1. Fungua issue.\n2. Chagua officer kwenye Assign.\n3. Bonyeza Assign."
             if sw else "1. Open the issue.\n2. Choose an officer under Assign.\n3. Click Assign.")
        return {"answer": a, "fact": fact, "lang": lang}
    if any(k in ql for k in ["unresolved"]):
        lines = [f"- {n}: {c}" for c, n in s["unresolved_by_cat"]] or ["- none"]
        head = "AI-GENERATED SUMMARY — categories zenye unresolved nyingi zaidi:" if sw else "AI-GENERATED SUMMARY — categories with most unresolved:"
        return {"answer": head + "\n" + "\n".join(lines) + "\n\n" + fact, "fact": fact, "lang": lang}
    if any(k in ql for k in ["mwezi huu", "sana", "top", "changamoto gani", "most reported", "recurring"]):
        lines = [f"- {n} reports: {c}" for c, n in s["top_cats"]] or ["- no data yet"]
        head = ("Kulingana na data iliyotumwa (Based on submitted data) — top categories:"
                if sw else "Based on the submitted data — top categories:")
        note = ("\n\nKumbuka: hii ni AI-GENERATED SUMMARY, si hitimisho rasmi la chuo."
                if sw else "\n\nNote: this is an AI-GENERATED SUMMARY, not an official institutional conclusion.")
        return {"answer": head + "\n" + "\n".join(lines) + note + "\n\n" + fact, "fact": fact, "lang": lang}
    if any(k in ql for k in ["satisfaction", "kuridhika"]):
        a = (f"DATABASE FACT — Average satisfaction: {s['avg']}/5 kutoka kwenye reports {s['total']}."
             if sw else f"DATABASE FACT — Average satisfaction: {s['avg']}/5 across {s['total']} reports.")
        return {"answer": a, "fact": fact, "lang": lang}
    if any(k in ql for k in ["mdamrefu", "longest", "overdue", " Aman ", "kaa muda", "stuck"]):
        lines = [f"- {o['reference_number']}: {o['title']} ({o['status']}, {o['created_at'][:10]})" for o in s["oldest"]] or ["- none"]
        head = "AI-GENERATED SUMMARY — issues zilizokaa muda mrefu bila kutatuliwa:" if sw else "AI-GENERATED SUMMARY — longest-waiting open issues:"
        return {"answer": head + "\n" + "\n".join(lines) + "\n\n" + fact, "fact": fact, "lang": lang}
    if any(k in ql for k in ["analyze this report", "chambua", "summarize", "muhtasari"]):
        lines = [f"- {n}x {c}" for c, n in s["top_cats"]]
        a = ("Based on the submitted data:\n" + "\n".join(lines) +
             f"\nResolved: {s['resolved']}/{s['total']}. Critical open: {s['critical']}. "
             f"Avg satisfaction {s['avg']}/5.\nAreas needing attention: " +
             (s["unresolved_by_cat"][0][0] if s["unresolved_by_cat"] else "none yet") +
             ".\n(AI-GENERATED SUMMARY — confirm with an authorized administrator.)")
        return {"answer": a, "fact": fact, "lang": lang}
    # default: guide + facts
    if sw:
        a = ("Mimi ni RUCUSO AI — Your System Assistant. Uliza kama:\n"
             "- 'Nianzie wapi?'\n- 'Ni changamoto gani zimeripotiwa sana mwezi huu?'\n"
             "- 'Ninawezaje kutoa report ya mwezi?'\n\n" + fact)
    else:
        a = ("I am RUCUSO AI — Your System Assistant. Try:\n"
             "- 'Where do I start?'\n- 'Which challenges are most reported?'\n"
             "- 'How do I generate a monthly report?'\n\n" + fact)
    return {"answer": a, "fact": fact, "lang": lang}
