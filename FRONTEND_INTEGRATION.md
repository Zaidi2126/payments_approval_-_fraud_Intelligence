# Frontend integration: "Send today's report" button

This describes how to wire a **Send today's report** (or similar) button so it sends the latest daily summary to Slack.

---

## 1. What the button does

On click, the frontend calls the backend; the backend:

- Takes the **latest** daily metrics (most recent date in the DB, i.e. "today" when data exists).
- Optionally includes calibration stats for that same date.
- Sends that summary to Slack via the configured webhook.
- Returns a JSON response so the FE can show success or error.

No request body is required. The backend uses the same logic as `python manage.py send_daily_slack_summary`.

---

## 2. API contract

### Endpoint

| Method | URL |
|--------|-----|
| **POST** | `{BASE_URL}/api/reports/send-daily-summary` |

Example: `https://your-api.com/api/reports/send-daily-summary` or `http://localhost:8000/api/reports/send-daily-summary`.

### Request

- **Method:** `POST`
- **Headers:** 
  - `Content-Type: application/json`
- **Body:** **Required.** The frontend provides the Slack webhook URL; the backend uses it only for this request (not stored).

```json
{
  "slack_webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
}
```

The user enters (or configures) the webhook in the FE; the FE sends it in the body when the button is clicked.

### Response (success)

- **Status:** `200 OK`
- **Body:**
```json
{
  "success": true,
  "message": "Daily report sent to Slack.",
  "report": {
    "date": "2025-02-07",
    "total_requests": 150,
    "auto_approved": 100,
    "auto_blocked": 20,
    "sent_to_review": 30,
    "accuracy_percent": 85.5,
    "overconfidence_rate": 2.0,
    "underconfidence_rate": 5.0
  }
}
```

- `report` always has: `date`, `total_requests`, `auto_approved`, `auto_blocked`, `sent_to_review`.
- If calibration exists for that date, `report` also includes: `accuracy_percent`, `overconfidence_rate`, `underconfidence_rate`.

### Response (errors)

| Status | Meaning | Body shape |
|--------|--------|------------|
| **400 Bad Request** | Missing or empty `slack_webhook_url` in body | `{ "success": false, "error": "slack_webhook_url is required. Send it in the request body: ..." }` |
| **404 Not Found** | No daily metrics in DB | `{ "success": false, "error": "No daily metrics found. Run recompute_daily_metrics or seed_demo_data first." }` |
| **502 Bad Gateway** | Slack request failed (network, invalid webhook, etc.) | `{ "success": false, "error": "Failed to send to Slack: <details>", "report": { ... } }` |

All error responses have `success: false` and an `error` string. Use them for toast/alert text.

---

## 3. What the frontend needs to do

1. **Button**  
   - Label: e.g. "Send today's report" or "Send daily summary to Slack".
   - On click: send `POST` to `{API_BASE}/api/reports/send-daily-summary`.

2. **Request**  
   - Use your API base URL (env var or config).
   - **Body must include** `slack_webhook_url`: the Slack Incoming Webhook URL (user enters it in the FE or it comes from your config).
   - Example body: `{ "slack_webhook_url": "https://hooks.slack.com/services/..." }`.

3. **Success (200)**  
   - Show a success message, e.g. "Report sent to Slack."
   - Optionally show a short summary from `response.report` (e.g. "Report for {report.date}: {report.total_requests} requests, …").

4. **Errors (4xx/5xx)**  
   - Parse `response.error` and show it in a toast/alert.
   - 400 → Missing or invalid `slack_webhook_url` in request body.
   - 404 → No report data yet.
   - 502 → Slack delivery failed (bad URL, network, etc.).

5. **Loading**  
   - Disable the button (and/or show a spinner) while the request is in progress to avoid double sends.

---

## 4. Example: fetch (vanilla JS)

```js
const API_BASE = 'http://localhost:8000';  // or your API URL

async function sendDailyReport(slackWebhookUrl) {
  // slackWebhookUrl: from input field, config, or state
  const button = document.getElementById('send-report-btn');
  button.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/api/reports/send-daily-summary`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slack_webhook_url: slackWebhookUrl }),
    });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || 'Failed to send report');
      return;
    }
    alert(data.message);  // "Daily report sent to Slack."
    // optional: show data.report
  } catch (e) {
    alert('Network error: ' + e.message);
  } finally {
    button.disabled = false;
  }
}
```

---

## 5. Example: axios (React / Vue / etc.)

```js
const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

async function sendDailyReport(slackWebhookUrl) {
  try {
    const { data } = await axios.post(`${API_BASE}/api/reports/send-daily-summary`, {
      slack_webhook_url: slackWebhookUrl,
    });
    // data.success === true, data.message, data.report
    toast.success(data.message);
    // optional: set state with data.report for a small summary
  } catch (err) {
    const message = err.response?.data?.error || err.message;
    toast.error(message);
  }
}
```

Wire `sendDailyReport` to your button’s `onClick` / `@click`, and pass the webhook URL (from an input field, settings, or state).

---

## 6. CORS

The backend allows all origins for CORS (`CORS_ALLOW_ALL_ORIGINS = True`). If your FE runs on another port (e.g. 3000) or domain, the browser will allow the `POST` request. For production you may restrict allowed origins in the backend.

---

## 7. Where the webhook URL comes from

The **frontend** is responsible for providing the Slack webhook URL. For example:
- User types it into an input or “Slack webhook” field in settings.
- Or it’s stored in your FE config / env (e.g. `REACT_APP_SLACK_WEBHOOK_URL`).

The backend uses the URL only for that single request and does not store it. If the FE does not send `slack_webhook_url`, the API returns **400**.
