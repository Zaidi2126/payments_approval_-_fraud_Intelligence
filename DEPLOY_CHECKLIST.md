# Deploy checklist — do these steps (GitHub push is done)

Repo is already pushed to: **https://github.com/Zaidi2126/payments_approval_-_fraud_Intelligence**

---

## 1. Deploy on Render (in browser)

1. Go to **https://render.com** and sign in (or sign up).
2. Click **New** → **Blueprint**.
3. Connect GitHub if needed, then select repo: **Zaidi2126/payments_approval_-_fraud_Intelligence**.
4. Render will detect `render.yaml`. Click **Apply**.
5. Wait for the **database** and **web service** to finish deploying (a few minutes). Your API URL will be like:  
   **https://deriv-guard-api.onrender.com**

---

## 2. Load the demo dataset (Render Shell)

When the web service is **Live**:

1. In Render dashboard, open your **web service** (e.g. `deriv-guard-api`).
2. Open the **Shell** tab.
3. Copy-paste and run these four commands one by one (or run the block):

```bash
python manage.py migrate
python manage.py seed_demo_data --clear
python manage.py recompute_daily_metrics
python manage.py recompute_calibration_stats
```

---

## 3. Optional: add env vars (for LLM + Slack)

In the web service → **Environment** → **Add Environment Variable**:

| Key | Value (example) |
|-----|------------------|
| `OPENAI_API_KEY` | Your OpenAI API key (for explanations, NL query, etc.) |
| `OPENAI_MODEL` | `gpt-4o-mini` (or leave default) |
| `SLACK_WEBHOOK_URL` | `https://hooks.slack.com/...` (only if you use Slack summary) |

Save; Render will redeploy. After that, the API is ready to use at the URL from step 1.

---

## 4. Quick test

- Health: **GET** `https://deriv-guard-api.onrender.com/health`
- Daily metrics: **GET** `https://deriv-guard-api.onrender.com/api/metrics/daily`

(First request after idle may take 30–60 s due to free-tier spin-up.)
