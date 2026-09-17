# Nepal Missing Persons Emergency Registry

A simple, fast, mobile-first Flask app for community-reported missing persons
during disaster response.

## What it does

- **Report** a missing person (name + gender required, everything else optional:
  age, last-seen location down to ward/landmark level, home address, photo,
  description, contact).
- **Search** by name, district, status, or whether a DNA reference is on file.
- **Live counters** at the top for MISSING and FOUND SAFE, refreshed every 30s.
- **Mark someone Found Safe** directly from their listing (records who confirmed it).
- **Duplicate detection**: as the reporter types the name and location, a live
  list below the form shows already-reported people that could match, narrowing
  as more fields are filled in. A second fuzzy-matching safety-net check also
  runs on submit.
- **DNA reference (prototype)**: a relative who has already had a lab DNA test
  done can attach that lab report (file + lab name/reference number/date) to
  the missing person's listing. This does NOT perform any DNA comparison —
  it stores and surfaces the reference so a real forensic lab/government team
  can pull up the report and run their own kinship comparison against a
  recovered body's own lab report. See "DNA reference notes" below.
- **Mark Identified** (government/forensic use): once a lab has confirmed a
  match through their own process, an authorized person can mark the record
  Identified, closing the case publicly instead of leaving it as "Missing"
  indefinitely.
- **Admin dashboard** (password-protected) to reject spam/bad entries or restore them.
- Plain interface: no animations, no unnecessary color — only red for MISSING
  and green for FOUND SAFE. "Identified" is shown in neutral black/bold.

## DNA reference notes — read before showing this to anyone

This is a **prototype demonstrating the workflow**, not a production system handling
real sensitive data:

- The missing person's own sample doesn't exist (they're missing) — what gets
  attached is a **relative's reference sample/report**, which is why relationship
  to the missing person is captured (parent/child gives the strongest kinship
  signal; distant relatives are often not conclusive alone).
- **This site performs zero DNA comparison.** Actual kinship matching requires
  certified forensic software and a trained geneticist working from the raw
  STR marker data in both lab reports — that entirely happens off this site,
  at the lab/government end.
- **Uploaded DNA reports are currently public** (no access restriction), by
  explicit choice for this prototype stage, so it can be demonstrated to
  government stakeholders. Before any real deployment with real people's data,
  this needs: restricted access (a separate authorized-official login), and
  ideally encryption of uploaded report files at rest. Do not use this
  prototype's DNA feature with real reports until that's added.


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
