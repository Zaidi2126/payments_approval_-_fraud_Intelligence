# Frontend spec: all 6 AI-powered features

Backend is done. Below is what the FE must implement for each feature. Base URL = your API root (e.g. `http://localhost:8000`).

---

## 1. Extra fraud signals (card, login, device)

**What it is:** The engine now uses three extra inputs when you send them: card declines, failed logins, and device id. Same payment decision API; new optional fields.

**What the FE should do:**

- **POST /api/payouts/decision**  
  Request body may now include (all optional):
  - `card_decline_count_24h` (integer) – card decline count in last 24h for this user/card.
  - `failed_login_count_24h` (integer) – failed login count in last 24h for this user.
  - `device_id` (string) – device or fingerprint id. If the same `device_id` is used by 3+ different `user_id`s, the engine adds a “device shared” risk signal.

- **Where to get the data:**  
  From your auth/payment providers or internal logs. If you don’t have them yet, omit the fields; the engine still works with the existing payload.

- **No new screens required.**  
  Only pass these when you have them (e.g. from a “risk context” service or when building the payload for the decision call).

---

## 2. Fraud network (who’s connected to whom)

**What it is:** For a given user, the API returns other users linked by same payment method, same IP, or same device. Optionally an AI summary of the “network” (e.g. possible fraud ring).

**API:**

- **GET** `{BASE_URL}/api/fraud-network?user_id=<user_id>&summary=1`
  - `user_id` (required): user to inspect.
  - `summary`: if `1`, `true`, or `yes`, response includes an AI-generated `summary` string.

**Response (200):**

```json
{
  "nodes": [{"user_id": "u1", "label": "u1"}, {"user_id": "u2", "label": "u2"}],
  "edges": [{"from": "u1", "to": "u2", "link_type": "payment_method"}],
  "summary": "Optional 2–3 sentence AI summary when summary=1."
}
```

**What the FE should do:**

- Add a **“Fraud network”** (or “Linked accounts”) entry point, e.g. from a user detail or history row: “View network”.
- Call the API with that user’s `user_id` and `summary=1`.
- Draw a **graph**:  
  - **Nodes** = `nodes` (e.g. circles with `label`).  
  - **Edges** = `edges` (lines between `from` and `to`). Use `link_type` for colour or legend (e.g. payment_method = red, ip_address = blue, device_id = green).
- Show the **summary** in a short paragraph above or below the graph (AI explanation of what this network might mean).
- Use any graph library you like (e.g. D3, vis.js, Cytoscape, or a simple list of “Linked: u2 (payment method), u3 (IP)” if you skip a visual graph).

---

## 3. Exposure (how much money at risk)

**What it is:** Sum of payout amounts for a set of users over a time window, plus an AI one-liner explaining the exposure.

**API:**

- **GET** `{BASE_URL}/api/exposure?user_ids=id1,id2,id3&days=30`
  - `user_ids` (required): comma-separated user ids.
  - `days` (optional): window in days (default 30, max 365).

**Response (200):**

```json
{
  "user_ids": ["id1", "id2"],
  "total_exposure": 15000.50,
  "currency": "USD",
  "days": 30,
  "user_count": 2,
  "explanation": "AI-generated one-sentence explanation of the exposure."
}
```

**What the FE should do:**

- Where you show a **list of users** (e.g. fraud network, or “flagged users”), add an action: **“Calculate exposure”** (or “Total at risk”).
- Call the API with the current set of `user_ids` (and optional `days`).
- Show **total_exposure** and **currency** prominently (e.g. “$15,000.50 at risk”).
- Show **explanation** as a short line or tooltip (AI summary for reports).

---

## 4. Bulk incident (flag many accounts + draft message)

**What it is:** Flag a list of users (e.g. after detecting a fraud ring). Future payouts for those users get an extra “account flagged” risk. The API also returns an AI-drafted client message you can use for notifications.

**API:**

- **POST** `{BASE_URL}/api/incidents/bulk-action`  
  Body (JSON):
  ```json
  {
    "user_ids": ["user1", "user2"],
    "action": "flag",
    "reason": "Fraud ring detected."
  }
  ```
  - `user_ids` (required): list of user ids (max 500).
  - `action`: e.g. `"flag"` (default).
  - `reason`: short reason (stored and used for the draft message).

**Response (200):**

```json
{
  "flagged_count": 2,
  "reason": "Fraud ring detected.",
  "drafted_client_message": "AI-generated 2–3 sentence client notification."
}
```

**What the FE should do:**

- Add a **“Bulk actions”** or **“Incident response”** flow (e.g. from fraud network or from a multi-select list of users).
- Form: multi-select or paste **user_ids**, **reason** (required), and optional **action** (default “flag”).
- On submit, call the API. Show success and **flagged_count**.
- Show **drafted_client_message** in a copyable block (e.g. “Use this message for client emails/notifications”) so ops can copy and send.

---

## 5. Natural language query (“show me accounts that…”)

**What it is:** User types a question in plain English; the API uses AI to turn it into filters, runs the query, and returns matching user ids.

**API:**

- **POST** `{BASE_URL}/api/query`  
  Body (JSON):
  ```json
  { "question": "Show me accounts that deposited but traded minimally" }
  ```

**Response (200):**

```json
{
  "question": "Show me accounts that deposited but traded minimally",
  "interpreted_filters": { "total_trades_max": 2, "total_trade_volume_max": 100 },
  "results": [{"user_id": "u1"}, {"user_id": "u2"}],
  "count": 2
}
```

If the AI could not interpret the question, `interpreted_filters` may be `null` and `results` may be `[]`; optional `message` explains.

**What the FE should do:**

- Add a **“Natural language search”** or **“Ask a question”** box (e.g. on an investigator/fraud dashboard).
- User types a question and submits (button or Enter).
- Call the API with `question`.
- Show **interpreted_filters** so the user sees what the AI understood (builds trust).
- Show **results** as a list of `user_id`s (or links to user detail). Show **count**.
- If `results` is empty and `interpreted_filters` is null, show the `message` and suggest rephrasing.

---

## 6. Emerging patterns (new fraud patterns the system found)

**What it is:** The backend groups recent block/review decisions by signal combo; combos that appear often are “emerging patterns.” Each pattern gets an AI-generated short description.

**API:**

- **GET** `{BASE_URL}/api/patterns/emerging?days=7`
  - `days` (optional): look back window (default 7, max 90).

**Response (200):**

```json
{
  "patterns": [
    {
      "signal_combo": "velocity_abuse,geo_vpn_anomaly",
      "case_count": 12,
      "description": "AI-generated one-sentence description and recommended action."
    }
  ],
  "days": 7
}
```

**What the FE should do:**

- Add an **“Emerging patterns”** (or “New patterns”) section or page (e.g. on admin or fraud dashboard).
- On load, call the API (e.g. `days=7` or user-selectable).
- Render **patterns** as cards or rows: show **signal_combo**, **case_count**, and **description**.
- Optionally add a “Refresh” button to refetch.

---

## Quick reference: new endpoints

| Feature           | Method | Endpoint                          | Key request                                      | Key response                          |
|------------------|--------|-----------------------------------|---------------------------------------------------|---------------------------------------|
| Extra signals    | POST   | /api/payouts/decision             | card_decline_count_24h, failed_login_count_24h, device_id (optional) | (unchanged)                           |
| Fraud network    | GET    | /api/fraud-network?user_id=X&summary=1 | -                                                | nodes, edges, summary                 |
| Exposure         | GET    | /api/exposure?user_ids=id1,id2&days=30 | -                                                | total_exposure, explanation           |
| Bulk incident    | POST   | /api/incidents/bulk-action        | user_ids, reason, action                          | flagged_count, drafted_client_message |
| NL query         | POST   | /api/query                        | question                                         | interpreted_filters, results, count   |
| Emerging patterns| GET    | /api/patterns/emerging?days=7     | -                                                | patterns[] (signal_combo, case_count, description) |

All of these (except extra signals on the existing decision call) are new; use them to build the 6 flows above so the product feels like one AI-powered system.
