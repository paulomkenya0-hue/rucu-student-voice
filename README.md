---
title: RUCU Student Voice
emoji: 🎓
colorFrom: blue
colorTo: navy
sdk: docker
app_port: 7860
pinned: false
---

# RUCU STUDENT VOICE & INSTITUTIONAL FEEDBACK SYSTEM (2026/2027)

Ruaha Catholic University — maoni ya wanafunzi kuhusu Wizara ya Mikopo (HELSB/BOOM/Ada).
Branding: **RUCU** (sio RCU). AI: **RUCUSO AI** (jukwaani + admin).

## Run (local)
```
pip install -r requirements.txt
python app.py
```
Open: http://localhost:5000 · Admin: http://localhost:5000/admin-login
Default admin: `admin@rucu.ac.tz` / `RucuAdmin2026` (badilisha baada ya login).

## Vipengele
- **My Space (`/my`)**: kila mwanafunzi ana sehemu yake — wasifu, maoni + majibu, rufaa, kura, SMS, matangazo.
- **Gate lazima**: reg (RU/COURSE/YEAR/NUMBER) → simu TZ → OTP SMS → fomu + password.
- **Matangazo**, **kura ya muhula 1–5★**, **rufani**, **SLA/OVERDUE**, **SW/EN toggle**.
- **RUCUSO AI**: widget hadharani (`/api/ask`) + admin assistant (`Ask RUCUSO AI`).
- **Ripoti**: PDF/Excel na "Approved by" + aliyetengeneza.
- **BOOM bulk SMS** kwa wapokea mkopo.
- **SEO**: `/robots.txt`, `/sitemap.xml`.

## Roster (majina ya wanafunzi)
Admin > Roster: upload `.xlsx`/`.csv` yenye `full_name, registration_number, programme, year_of_study, phone`.
PDF: export kwenda Excel kwanza.

## SMS
Default `demo-log` (ina-log + inaonyesha code demo). Live Tanzania: Beem/Africa'sTalking credit → Settings.

## Deploy
- **Supabase + Render/Railway**: tazama `DEPLOY_SUPABASE.md` (`DATABASE_URL`).
- **Hugging Face Spaces (Docker)**: `Dockerfile` + `README` frontmatter zipo tayari. Bila `DATABASE_URL` app inatumia SQLite.

Developed by Paulo Mkenya © Ruaha Catholic University
