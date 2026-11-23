# Deploying the HappySmile demo (Railway + Vercel)

```
 Browser ──► Vercel (pages: /, /console, /voice)
               │  /v1/* is forwarded (same site, so cookies + security policy just work)
               ▼
            Railway: web service (FastAPI + call worker in one process) ──► Railway Postgres
```

- **Railway** runs the backend from [backend/Dockerfile](backend/Dockerfile): on every start it applies
  migrations, seeds the demo clinics/slots/staff, turns the browser voice demo on, then serves.
  The worker runs inside the web process (`RUN_WORKER=true`), so it is one service plus a database.
- **Vercel** serves the static pages and forwards `/v1/*` to Railway ([vercel.json](vercel.json)).
  Vercel can't host the backend itself: its functions can't keep the worker loop or database pool alive.
- The Railway URL on its own is a complete site too; Vercel is the nicer front door.

`APP_ENV=demo` is a public demo mode: synthetic data, browser calls allowed (no telephony), but it refuses
to start without a real `IP_HASH_SALT` and its own `DEMO_STAFF_PASSWORD` (the dev passwords in the README
would otherwise let anyone into the console). Visitors are told to use made-up details.

## 1. Railway (backend + database)

1. https://railway.com → **New Project → Deploy from GitHub repo** → `Happy-Smile`.
2. Click the new service → **Settings**:
   - **Root Directory**: `backend`
   - **Config-as-code → Railway Config File**: `/backend/railway.json` (Dockerfile build + `/healthz` health check)
3. In the project: **+ Create → Database → PostgreSQL**.
4. App service → **Variables → Raw Editor**, paste and fill in the two secrets:

   ```
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   APP_ENV=demo
   RUN_WORKER=true
   IP_HASH_SALT=<32+ random characters>
   DEMO_STAFF_PASSWORD=<your console password, 10+ characters>
   VOICE_AGENT_ENABLED=true
   TELEPHONY_PROVIDER=browser
   CALLING_WINDOW_START=00:00
   CALLING_WINDOW_END=23:59
   LAST_CALL_CUTOFF_MIN=0
   STAFF_HOURS_START=00:00
   STAFF_HOURS_END=23:59
   DEDUPE_HOURS=0
   RATE_LIMIT_PHONE_PER_HOUR=100
   AUTO_KILL_SWITCH=false
   ```

   Random salt in PowerShell: `-join ((1..32) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })`

   Optional, Groq understanding (otherwise rules only). Type the key into Railway yourself; never commit it:

   ```
   GROQ_API_KEY=<your key>
   LLM_DIALOGUE_MODEL=qwen/qwen3.8-27b
   LLM_GUARD_MODEL=qwen/qwen3.8-27b
   LLM_SUMMARY_MODEL=qwen/qwen3.8-27b
   ```

5. **Settings → Networking → Generate Domain**. Open `https://<your-app>.up.railway.app/healthz`:
   it should say `{"ok":true,"env":"demo"}`. The deploy log shows migrations, seeding and
   `Orchestrator worker ... started`.

## 2. Vercel (front end)

1. [vercel.json](vercel.json) forwards `/v1/*` to the Railway domain (`happy-smile-production-f9599d2d.up.railway.app`).
   If the Railway domain ever changes, update both lines there, commit and push.
2. https://vercel.com → **Add New → Project** → import `Happy-Smile`.
   - **Root Directory**: leave as the repository root
   - **Framework Preset**: Other (build command and output folder come from `vercel.json`)
3. **Deploy**, then open the Vercel URL: the form, `/console` and `/voice` all work from there.

## Using the demo

- Form → pick Riverside, Hillcrest or Lotus Square → **Call me now** → the tab rings → **Answer**,
  allow the microphone (Chrome or Edge; both sites are HTTPS, which the microphone needs).
- Console: `/console` opens without a login as **Demo visitor** (front desk for all three pilot clinics;
  no Ops, kill switch or experiment settings). `OPEN_CONSOLE` is on by default with `APP_ENV=demo`; set it to
  `false` to require sign-in. Ops/admin: sign in via `POST /v1/auth/login` as `ops` or `admin` with your
  `DEMO_STAFF_PASSWORD` (the console then uses that session). Staging/production refuse `OPEN_CONSOLE`.
- Slots are topped up every 6 hours, so the demo keeps a rolling week of appointments.

## Costs and limits

- Railway has no permanent free tier: a one-off trial credit, then the Hobby plan (about $5/month,
  usage-based). One small service plus Postgres fits comfortably.
- Vercel Hobby is free for personal projects.
- Live updates in the console use a long-lived connection; if Vercel cuts it, the browser reconnects
  automatically. Opening the console on the Railway URL avoids that entirely.
- Real phone calls need a telephony provider (not built); the demo calls the browser instead.
