# Deploy RUCU Student Voice with Supabase (Postgres)

App inajitambua yenyewe: `DATABASE_URL` ikianza na `postgres` → Supabase/Postgres,
la sivyo → SQLite ya local (`rucu_voice.db`). Hakuna kubadilisha code.

## Hatua

1. **Supabase**: supabase.com → New project → Settings → Database → kopia
   `Connection string` (URI). Jaza password.
2. **Schema**: Supabase → SQL Editor → bandika yaliyomo kwenye
   `supabase_schema.sql` → Run. (Tables zote + indexes.)
3. **Admin wa kwanza**: run `python make_admin.py "PasswordYako"` → kopia SQL
   inayotoka → Supabase SQL Editor → Run. Kisha login kwa
   `admin@rucu.ac.tz` + password hiyo.
4. **Render (bure)**: New → Web Service → chagua repo/folder →
   Build `pip install -r requirements.txt`, Start `gunicorn app:app`
   → Environment → ongeza `DATABASE_URL` → Deploy.
   Railway/Heroku: tumia `Procfile` iliyopo.
5. **Verify**: fungua URL → `/submit` → `/dashboard`. SMS bado ni demo-log
   mpaka uweke Beem/Africa'sTalking key Settings.
6. **Uploads**: kwa sasa files zinahifadhiwa `uploads/` kwenye server.
   Ukitaka kudumu: Supabase Storage bucket `attachments` + badilisha
   `UPLOAD_DIR` kutumia supabase-py (hatua inayofuata).

## Muhimu
- `.env` kamwe usii-commit (tumia `.env.example` kama kiolezo).
- Badilisha password ya admin mara tu baada ya login ya kwanza.
- Backup: Supabase → Database → Backups (automatic kwenye plan).
