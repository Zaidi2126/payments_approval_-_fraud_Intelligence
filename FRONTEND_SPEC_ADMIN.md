# Frontend spec: Admin page (conflicted decisions & signal weights)

**You own the admin experience.** This doc is the single source of truth for what the FE must build and how it must behave. No shortcuts.

---

## What you’re building

One **admin-only page** with two main areas:

1. **Signal weights** – Show current engine weights; show and apply “pending suggestion” when it exists.
2. **Conflicted transactions** – List every case where a human **overturned** the system; show AI explanation + human note; let admin “approve for learning” and optionally apply suggested weights.

Base URL for all API calls: use the same `BASE_URL` as the rest of the app (e.g. `http://localhost:8000` or your deployed API). Send `Content-Type: application/json` where relevant.

---

## 1. Page access and layout

- **Route:** e.g. `/admin` or `/admin/conflicted` — your choice, but it must be clearly an admin-only route (protect it with whatever auth you use).
- **Title:** e.g. “Admin – Conflicted decisions & signal weights”.
- **Layout:**
  - **Top:** “Current signal weights” block (see §2).
  - **Below:** “Conflicted decisions” list (see §3).
- **Loading / errors:** Show loading states for any API call. On 4xx/5xx, show a clear error message and do not replace existing data with garbage.

---

## 2. Current signal weights (top section)

**Data:**  
- **GET** `{BASE_URL}/api/admin/weights`  
- Response: `{ "signal_weights": { ... }, "pending_suggestion": null | { ... } }`

**You must:**

1. **On load** (and after any action that changes weights), call GET `/api/admin/weights` and store `signal_weights` and `pending_suggestion`.
2. **Display** all current weights in a clear, readable way (e.g. table or list).  
   - Keys are: `no_trade_fraud`, `short_trade_abuse`, `new_payment_method_risk`, `velocity_abuse`, `geo_vpn_anomaly`.  
   - Show the **signal name** (you may format for display, e.g. `no_trade_fraud` → “No trade fraud”) and its **integer value** (0–100).
3. **If `pending_suggestion` is not null:**  
   - Show a distinct block: “Pending weight suggestion” (from last “Approve for learning”).  
   - Show the suggested weights (same keys as above).  
   - Provide two actions:  
     - **“Apply suggestion”** – Send **PATCH** `{BASE_URL}/api/admin/weights` with body `{ "signal_weights": <pending_suggestion> }`. On 200, refetch GET `/api/admin/weights` and update the UI; clear any local “pending” state from the response (backend will return `pending_suggestion: null` after you’ve applied if you refetch).  
     - **“Dismiss”** – Optional: you may call PATCH with current weights only to “confirm” current and clear pending, or just hide pending in UI until next approve; backend does not have a dedicated “dismiss” endpoint, so “Dismiss” can be UI-only (hide pending until next time an override is approved).
4. **Optional:** Let admin **manually edit** one or more weights and **“Save”** – same PATCH with `{ "signal_weights": { "signal_name": value, ... } }`. Only send the keys that changed; backend merges with current. After 200, refetch GET `/api/admin/weights`.

---

## 3. Conflicted decisions list

**Data:**  
- **GET** `{BASE_URL}/api/admin/conflicted-decisions`  
- Response: `{ "conflicted_decisions": [ ... ] }`

Each item has at least:  
`human_review_id`, `risk_decision_id`, `payout_request_id`, `reviewed_at`, `reviewer_id`, `system_decision`, `human_decision`, `human_note`, `system_explanation`, `risk_score`, `triggered_signals`, `reasons`, `approved_for_learning`, `payout_summary`.

**You must:**

1. **On load**, call GET `/api/admin/conflicted-decisions` and render the list. If the list is empty, show a clear message (e.g. “No conflicted decisions”).
2. **Per row (per conflicted decision), show:**
   - **Ids:** e.g. payout request id (or a short link) and risk decision id if useful for support.
   - **When:** `reviewed_at` (formatted).
   - **Who:** `reviewer_id`.
   - **System vs human:**  
     - System decision: `system_decision` (approve/block).  
     - Human decision: `human_decision` (approve/block).  
     - Make the **override** obvious (e.g. “System: Block → Human: Approve”).
   - **Human note:** `human_note` (if empty, show “—”).  
   - **AI explanation:** `system_explanation` (backend/LLM-generated: why the system did what it did and what the human said). Show it in a readable block (e.g. a short paragraph or expandable section).  
   - **Risk context:** `risk_score`, `triggered_signals` (and optionally `reasons`).  
   - **Payout summary:** `payout_summary` (backend gives a one-line summary; you can show it as-is or break it into fields).  
   - **Status:** `approved_for_learning` – e.g. badge “Approved for learning” or “Not yet approved”.
3. **Action per row:**  
   - If `approved_for_learning` is **false**, show a button: **“Approve for learning”**.  
   - On click:  
     - **POST** `{BASE_URL}/api/admin/conflicted-decisions/<human_review_id>/approve`  
       - Use `human_review_id` from this row (UUID).  
     - On **200:**  
       - Update the row so it shows as approved (e.g. set `approved_for_learning: true` and show “Approved for learning”).  
       - Backend returns `suggested_weights` and `current_weights`.  
       - **Either:**  
         - Show the suggested weights in a small modal/section and a single “Apply these weights” that does PATCH `/api/admin/weights` with `suggested_weights`, then refetch weights and conflicted list;  
         - **Or** just refetch GET `/api/admin/weights` so the top section now shows `pending_suggestion` and the admin applies from there.  
       - Pick one flow and stick to it so the admin always knows where to apply.  
     - On **400:** Show error (e.g. “This review is not an override”).  
     - On **404:** Show error (“Review not found”).  
   - If `approved_for_learning` is **true**, do not show the button again (or show “Approved” as disabled).
4. **Refresh:** Provide a way to refresh the list (e.g. “Refresh” button that calls GET `/api/admin/conflicted-decisions` again and replaces the list).

---

## 4. Human review form – accept vs conflict (mandatory)

**Full API details:** see **`HUMAN_REVIEW_API.md`** in the repo. Summary below.

The human has **exactly two options** when reviewing a system decision:

- **Accept** – “I agree with the system.” No note, no final_decision needed.
- **Conflict** – “I overturn the system.” They **must** choose the new outcome (approve or block) and **must** write a **note** explaining why.

**POST** `{BASE_URL}/api/reviews` — body (JSON):

| Field | When | Required | Notes |
|-------|------|----------|--------|
| `risk_decision_id` | Always | Yes | UUID of the risk decision. |
| `reviewer_id` | Always | Yes | Who is reviewing. |
| `action` | Always | Yes | **`"accept"`** or **`"conflict"`**. |
| `final_decision` | Only when `action` is `"conflict"` | Yes (then) | `"approve"` or `"block"`. Must **differ** from system decision. |
| `note` | Only when `action` is `"conflict"` | Yes (then) | Non-empty. Explain why they conflicted. Shown on admin page. |

**Accept example:**
```json
{ "risk_decision_id": "...", "reviewer_id": "r1", "action": "accept" }
```

**Conflict example:**
```json
{
  "risk_decision_id": "...",
  "reviewer_id": "r1",
  "action": "conflict",
  "final_decision": "approve",
  "note": "Customer verified; false positive."
}
```

**You must:**

1. Show the **system decision** (approve/block) so the reviewer knows what they’re accepting or conflicting.
2. **Accept:** One action (e.g. “Accept system decision”). On submit send only `risk_decision_id`, `reviewer_id`, `action: "accept"`. No note field.
3. **Conflict:** One action (e.g. “Conflict / overturn”). On submit send `risk_decision_id`, `reviewer_id`, `action: "conflict"`, `final_decision` (the **new** outcome, so the opposite of the system), and **`note`**. The **note field is required** in the UI when conflicting: disable submit until the user has entered non-empty text. Show validation errors from the API (400) if note is missing or final_decision equals system.
4. On 201, show success and include `human_review_id` / `reviewed_at` from the response.

---

## 5. API summary (copy-paste reference)

| What | Method | URL | Body (if any) |
|------|--------|-----|----------------|
| List conflicted decisions | GET | `{BASE_URL}/api/admin/conflicted-decisions` | — |
| Current + pending weights | GET | `{BASE_URL}/api/admin/weights` | — |
| Approve override (for learning) | POST | `{BASE_URL}/api/admin/conflicted-decisions/<review_id>/approve` | — |
| Update signal weights | PATCH | `{BASE_URL}/api/admin/weights` | `{ "signal_weights": { "no_trade_fraud": 40, ... } }` |
| Create human review (accept or conflict) | POST | `{BASE_URL}/api/reviews` | See `HUMAN_REVIEW_API.md`. Accept: `{ "risk_decision_id", "reviewer_id", "action": "accept" }`. Conflict: `{ "risk_decision_id", "reviewer_id", "action": "conflict", "final_decision", "note" }`. |

All request bodies: **JSON**. All responses: **JSON** unless otherwise specified.

---

## 6. What “good” looks like

- Admin opens the page and **immediately** sees current weights and the list of conflicted transactions.  
- For each conflict, they see **why the system did what it did** and **what the human said** (AI explanation + note).  
- With one click they can **“Approve for learning”** and then **apply** the suggested weights (either inline or from the top section).  
- After apply, the **weights** at the top update and **new decisions** use the new weights (backend handles that).  
- No silent failures: **loading** and **error** states are always clear.

You’re the boss of the FE: implement this exactly, then we can iterate on copy and layout.
