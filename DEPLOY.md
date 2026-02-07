# Deploy the backend for free (few clicks)

Easiest option: **Render** — free tier, connect GitHub, deploy. You can add the demo dataset **after** deploying using the Shell.

---

## Option 1: Render (recommended — ~5 minutes)

### 1. Push your code to GitHub

If you haven’t already:

```bash
git init
git add .
git commit -m "Initial commit"
# Create a repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 2. Deploy with one Blueprint (few clicks)

1. Go to [render.com](https://render.com) and sign up / log in (free).
2. **New** → **Blueprint**.
3. Connect your GitHub account and select the repo that contains this project.
4. Render will detect `render.yaml`. Click **Apply**.
5. Wait for the **database** and **web service** to be created and deployed (a few minutes).
6. Your API will be at: `https://deriv-guard-api.onrender.com` (or the URL shown in the dashboard).

### 3. Add the dataset after deploying

Render’s free tier uses **PostgreSQL** (no SQLite). Migrations run automatically if you add a **release command** (see below). To load the demo data **after** the first deploy:

1. In Render dashboard, open your **web service** (e.g. `deriv-guard-api`).
2. Open the **Shell** tab (or **Settings** → **Build & Deploy** → you can run one-off commands via Shell).
3. In the Shell, run:

```bash
python manage.py migrate
python manage.py seed_demo_data --clear
python manage.py recompute_daily_metrics
python manage.py recompute_calibration_stats
```

After this, the API will have the curated demo data (payouts, reviews, patterns, etc.).

**Optional — run migrations on every deploy:**  
In the Render dashboard for your web service: **Settings** → **Build & Deploy** → **Release Command** set to:

```bash
python manage.py migrate
```

Then every deploy runs migrations; you only run the seed commands above when you want to (re)load the dataset.

### 4. Optional environment variables

In the web service → **Environment** add:

- `OPENAI_API_KEY` — for LLM explanations (if missing, deterministic fallback is used).
- `OPENAI_MODEL` — e.g. `gpt-4o-mini`.
- `SLACK_WEBHOOK_URL` — if you use the daily Slack summary.

---

## Option 2: Manual Render (without Blueprint)

If you prefer not to use `render.yaml`:

1. **New** → **PostgreSQL** → create a free database → copy **Internal Database URL**.
2. **New** → **Web Service** → connect repo → choose this repo.
3. **Settings:**
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn deriv_guard.wsgi:application --bind 0.0.0.0:$PORT`
   - **Environment:** add `DATABASE_URL` = (paste the Internal Database URL), `SECRET_KEY` (generate a random string), `DEBUG` = `False`.
4. Deploy. Then open **Shell** and run the same commands as in step 3 above to add the dataset.

---

## Free tier notes (Render)

- **Web service:** Spins down after ~15 minutes of no traffic; first request after that may take 30–60 seconds (cold start).
- **PostgreSQL:** Free plan is suitable for demo; data persists across deploys.
- **Hours:** 750 hours/month free for the web service.

---

## Other free options (alternative)

| Platform        | Pros                    | Cons                          |
|----------------|-------------------------|-------------------------------|
| **Railway**    | Simple, free $5 credit  | Credit-based; need Postgres   |
| **Fly.io**     | Persistent volumes      | CLI setup; more steps         |
| **PythonAnywhere** | Persistent, free tier | More manual WSGI/config       |

For “easiest in few clicks + add data after deploy”, Render + Blueprint + Shell for seed is the recommended path.
