# Admin page: conflicted decisions and signal weights

Backend APIs for the **admin page** that shows overturned transactions, LLM explanations, and current signal weights. The FE can use these to build the page.

---

## 1. List conflicted transactions (overrides)

**GET** `{BASE_URL}/api/admin/conflicted-decisions`

Returns all decisions where the **human overturned** the system (system said approve/block, human said the opposite). For each, the backend fills an LLM-generated **system explanation** (why the system did what it did) and shows the **human note** (if any). Explanations are generated on first request and cached.

**Response (200):**
```json
{
  "conflicted_decisions": [
    {
      "human_review_id": "uuid",
      "risk_decision_id": "uuid",
      "payout_request_id": "uuid",
      "reviewed_at": "2026-02-07T12:00:00",
      "reviewer_id": "reviewer_1",
      "system_decision": "block",
      "human_decision": "approve",
      "human_note": "Customer verified; false positive.",
      "system_explanation": "The system decided to block because... The human approved and noted...",
      "risk_score": 65,
      "triggered_signals": ["velocity_abuse", "geo_vpn_anomaly"],
      "reasons": ["..."],
      "approved_for_learning": false,
      "payout_summary": "user_id=... amount=... currency=... ..."
    }
  ]
}
```

---

## 2. Current signal weights (and pending suggestion)

**GET** `{BASE_URL}/api/admin/weights`

Returns the **current signal weights** used by the engine, and optionally a **pending suggestion** from the last approved override.

**Response (200):**
```json
{
  "signal_weights": {
    "no_trade_fraud": 40,
    "short_trade_abuse": 25,
    "new_payment_method_risk": 15,
    "velocity_abuse": 30,
    "geo_vpn_anomaly": 25
  },
  "pending_suggestion": null
}
```

After an admin approves an override (see below), `pending_suggestion` will contain the LLM-suggested weights until they are applied or overwritten.

---

## 3. Approve override (for learning)

**POST** `{BASE_URL}/api/admin/conflicted-decisions/<review_id>/approve`

- `review_id`: UUID of the **HumanReview** (from `human_review_id` in the list).

Marks that override as **approved for learning** and asks the LLM to suggest new signal weights. The suggestion is stored as **pending** and returned; the admin can then apply it via PATCH weights.

**Response (200):**
```json
{
  "approved_for_learning": true,
  "suggested_weights": {
    "no_trade_fraud": 38,
    "short_trade_abuse": 25,
    "new_payment_method_risk": 15,
    "velocity_abuse": 28,
    "geo_vpn_anomaly": 25
  },
  "current_weights": { ... }
}
```

**Errors:** 404 if review not found; 400 if that review is not an override (system and human already agree).

---

## 4. Update signal weights

**PATCH** `{BASE_URL}/api/admin/weights`

**Body:**
```json
{
  "signal_weights": {
    "no_trade_fraud": 38,
    "velocity_abuse": 28
  }
}
```

Only included keys are updated; others keep their current value. Values must be integers 0–100. All new decisions use these weights (stored in DB).

**Response (200):**
```json
{
  "signal_weights": {
    "no_trade_fraud": 38,
    "short_trade_abuse": 25,
    "new_payment_method_risk": 15,
    "velocity_abuse": 28,
    "geo_vpn_anomaly": 25
  }
}
```

---

## 5. Human review create – accept vs conflict

**Full details:** see **`HUMAN_REVIEW_API.md`**.

The human has two options:

- **Accept** – Agree with the system. Body: `{ "risk_decision_id", "reviewer_id", "action": "accept" }`. No note.
- **Conflict** – Overturn. Body: `{ "risk_decision_id", "reviewer_id", "action": "conflict", "final_decision": "approve"|"block", "note": "required text" }`. `final_decision` must differ from system; `note` is required and appears on the admin conflicted-decisions page.

---

## Suggested admin page layout

1. **Top section:** Current **signal weights** (from GET `/api/admin/weights`). Show each signal and its weight; optionally a button “Apply pending suggestion” that PATCHes with `pending_suggestion` if present.

2. **List:** **Conflicted decisions** (from GET `/api/admin/conflicted-decisions`). For each row:
   - Payout summary, system decision, human decision, human note.
   - **System explanation** (LLM): why the system did what it did and what the human said.
   - **Approve for learning** button (POST `/api/admin/conflicted-decisions/<review_id>/approve`). After click, show the suggested weights and an option to apply them.

3. **Apply weights:** When the admin applies a suggestion, PATCH `/api/admin/weights` with the suggested (or edited) `signal_weights`.
