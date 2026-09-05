# Deploying Metrik

Two separate deployments: the FastAPI backend (Render) and the React
frontend (Vercel). Free tier on both is enough for a hackathon demo.

## 1. Backend — Render

1. Push this repo to GitHub (already done if you're reading this from there).
2. On [render.com](https://render.com): **New +** → **Blueprint** → connect
   this repo. Render reads `render.yaml` at the repo root and configures
   itself — root directory `backend`, build command, start command.
3. Before the first deploy finishes, open the service → **Environment** and
   set `GROQ_API_KEY` (get one free at console.groq.com/keys). Without it,
   the chatbot falls back to canned rule-based answers instead of a live
   LLM — the app still works, just with a weaker chat feature.
4. Once live, note the service URL, e.g. `https://metrik-api.onrender.com`.
   Test it directly: `https://metrik-api.onrender.com/docs` should show the
   FastAPI interactive docs.

**Known limitation:** the free instance type has an ephemeral filesystem —
`metrik.db` (accounts, machines, scrap-saved totals) resets on every
redeploy or restart. Fine for a judging window; if you need it to persist
long-term, attach a paid instance type with a persistent disk (Render
dashboard → the service → **Disks**), and uncomment/add a `disk:` block in
`render.yaml`.

## 2. Frontend — Vercel

1. On [vercel.com](https://vercel.com): **Add New** → **Project** → import
   this repo, set **Root Directory** to `frontend`.
2. Framework preset: Vite (auto-detected). Build command `npm run build`,
   output directory `dist` (Vercel's Vite preset sets these automatically).
3. Under **Environment Variables**, add:
   ```
   VITE_API_BASE = https://metrik-api.onrender.com/api
   ```
   (your actual Render URL from step 1, with `/api` on the end — this is
   read by `frontend/src/api.js` and `frontend/src/auth.jsx`; without it,
   the build falls back to the relative `/api` path that only works in
   local dev behind Vite's proxy.)
4. Deploy. `frontend/vercel.json` is already in the repo and handles the
   client-side routing rewrite (React Router) — no extra config needed.

## Before sharing the link with judges

- **The demo login (`demo` / `metrik123`) is the intended path in.** Signup
  works too, but password hashing here is deliberately lightweight (see
  `backend/utils/auth.py`'s own docstring) — the signup form now shows a
  warning not to reuse a real password, since this is a public demo.
- CORS is wide open (`allow_origins=["*"]` in `backend/api/main.py`) by
  design for this demo — fine for a read-mostly hackathon app with no
  sensitive data, not something to carry into a real production deploy
  without revisiting.

## Redeploying after a code change

Both Render and Vercel auto-redeploy on every push to `main` once
connected — just `git push`.
