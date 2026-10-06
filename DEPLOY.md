# Deploying Agenclave (a public, clickable demo)

The whole product (React UI + FastAPI API) ships as **one process** from a single
`Dockerfile`. Goal: a public URL anyone can open on a phone, with **no risk of
spending API credits**.

## Run it locally first (sanity check)

```bash
docker build -t agenclave .
docker run --rm -p 8000:8000 -e SECRET_KEY="local-test-secret" agenclave
# open http://localhost:8000  -> Triage works; /about explains the project
```

## Deploy to a host

Any Docker host works. **Render** is the simplest free option:

1. Push this branch to GitHub.
2. Render → **New → Web Service** → connect the repo.
3. Render auto-detects the `Dockerfile`. Instance type: free/starter is fine.
4. Set environment variables (below) and deploy. You get a `*.onrender.com` URL.

Railway and Fly.io work the same way (both detect the `Dockerfile`; Fly: `fly launch`).

## Environment variables

| Var | Required | Notes |
|-----|----------|-------|
| `SECRET_KEY` | **Yes** | Any long random string. The dev default must **not** ship publicly (it signs JWTs). |
| `PORT` | Auto | Render/Railway/Fly inject this; the image honours it. |
| `BLACKBOX_API_KEY` (or `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) | No | Without a key, live runs can't fire and the Live toggle is hidden. See below before setting one. |
| `AGENCLAVE_BLACKBOX_API_BASE` | No | Defaults to `https://enterprise.blackbox.ai/v1`. The old `api.blackbox.ai` host returns 404. |

## Spending money: what a key on the public instance means

- Without a provider key, nothing on the public URL can spend credits. Triage and dry
  runs work for anyone.
- With a key set, two guards apply: a live run needs a logged-in user, and all users
  share one cap of `AGENCLAVE_LIVE_DAILY_CAP` live runs per UTC day (default 20),
  counted in the database. Registration is open, so treat the cap as the real limit:
  20 runs on the open-source fleet is a few cents a day.
- The cap lives in the database. On the free instance SQLite resets on restart, so
  set `DATABASE_URL` (Neon works) if the cap and the accounts should persist.

## Good to know

- **SQLite is ephemeral here.** The DB lives at `/app/data` and resets on redeploy.
  Fine for a demo. To persist accounts, attach a disk/volume (Render Disk, Fly Volume)
  mounted at `/app/data`.
- **Image is torch-free.** It installs `requirements-serve.txt` (the runtime subset),
  not the full training stack - fast builds, small image. Use `requirements.txt` only
  to retrain models or run tests.
- The trained classifier (`models/`) is baked into the image, so triage works out of
  the box; live best-of-N needs a provider key (see above).

## Before you share the link (checklist)

1. Open the URL on a phone, logged out - Triage returns a result, a dry code-fix run
   shows the routing decision, `/about` loads, no console errors.
2. `SECRET_KEY` is set. If a provider key is set, `POST /runs` with `live: true` and
   no token returns 401.
3. The repo link in `frontend/src/pages/AboutPage.jsx` (`REPO_URL`) points at the real
   public repo.
