# Nepal Missing Persons Emergency Registry

A simple, fast, mobile-first Flask app for community-reported missing persons
during disaster response.

## What it does

- **Report** a missing person (name + gender required, everything else optional:
  age, district, municipality, ward, landmark, photo, description, contact).
- **Search** by name, district, or status.
- **Live counters** at the top for MISSING and FOUND SAFE, refreshed every 30s.
- **Mark someone Found Safe** directly from their listing (records who confirmed it).
- **Duplicate detection**: when a new report is submitted, the app fuzzy-matches
  name + gender + age + ward/municipality against existing records (district
  alone is too broad after a large disaster) and shows possible matches before
  letting the reporter continue.
- **Admin dashboard** (password-protected) to reject spam/bad entries or restore them.
- Plain interface: no animations, no unnecessary color — only red for MISSING
  and green for FOUND SAFE.

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # edit SECRET_KEY / ADMIN_PASSWORD
python app.py
```

Visit http://localhost:5000

By default it uses a local SQLite file (`registry.db`) — nothing else to set up.

## Deploying for free

This is the stack to use so the whole thing costs nothing:

1. **Database — Supabase (free Postgres, 500MB)**
   - Create a free project at supabase.com
   - Go to Project Settings → Database → Connection string (URI format)
   - You'll use this as `DATABASE_URL`
   - *Why not just SQLite in production?* Render's free-tier disk is wiped on
     every redeploy/restart, so any SQLite file would randomly lose data.
     Supabase's Postgres persists.

2. **Hosting — Render.com free Web Service**
   - Push this project to a GitHub repo
   - On Render: New → Web Service → connect your repo
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
   - Add environment variables:
     - `DATABASE_URL` = (your Supabase connection string)
     - `SECRET_KEY` = (any long random string)
     - `ADMIN_PASSWORD` = (a password you'll remember)
   - Deploy. You get a free `https://yourapp.onrender.com` URL.
   - Note: free Render services sleep after 15 min of inactivity and take
     ~30–60s to wake up on the next visit. Fine for an MVP; if that's a
     problem during an active emergency, Railway's or Fly.io's free tiers
     are alternatives with different sleep behavior — check current terms,
     as free-tier policies change often.

3. **Photo storage**
   - Photos currently save to the app's local disk (`static/uploads/`), which
     is also wiped on Render free-tier redeploys. For an MVP this is
     acceptable (photos are a nice-to-have, not core data), but if you want
     photos to persist long-term, swap `save_photo()` in `app.py` for an
     upload to Supabase Storage (also free up to 1GB) instead of local disk.
   - Photos are compressed client-side in the browser before upload
     (resized to ~900px, JPEG quality 0.7) so they stay small on slow
     mobile connections.

## Design notes / trade-offs to know about

- **Trust-based moderation**: reports go live immediately (status = "missing")
  so information spreads fast in an emergency, rather than waiting in a queue.
  The admin dashboard lets you retroactively hide spam/bad entries. This
  mirrors how Google Person Finder operated after real disasters.
- **"Mark Found Safe" is open to any visitor**, not just the original reporter,
  by design — often the person who confirms someone's safety isn't the one who
  filed the report. Their name/phone is recorded on the record for accountability,
  and an admin can revert a wrong mark from the dashboard if needed.
- **Duplicate detection is assistive, not automatic**: it shows likely matches
  and asks the reporter to confirm before creating a new record, rather than
  silently merging — silent merging risks hiding a real second person with the
  same name in the same area.

## Project structure

```
app.py                 - routes
models.py               - MissingPerson SQLAlchemy model
duplicate_check.py       - fuzzy matching logic
templates/               - Jinja2 HTML
static/css/style.css      - all styling (mobile-first, minimal color)
static/js/main.js          - live counter polling + client-side photo compression
requirements.txt
Procfile                 - for Render/Railway
.env.example
```
