# Human Review API – crystal clear for FE

**Endpoint:** `POST {BASE_URL}/api/reviews`

The human reviewer has **exactly two choices** for each system decision (approve/block):

1. **Accept** – I agree with the system. No note needed.
2. **Conflict** – I overturn the system. I **must** choose the new outcome (approve or block) and **must** write a note explaining why.

---

## Request body (JSON)

| Field | Type | Required | When | Description |
|-------|------|----------|------|-------------|
| `risk_decision_id` | UUID | **Always** | — | The risk decision being reviewed. |
| `reviewer_id` | string | **Always** | — | Who is reviewing (e.g. user id or name). |
| `action` | string | **Always** | — | **`"accept"`** or **`"conflict"`**. |
| `final_decision` | string | When `action` is **`"conflict"`** | conflict only | **`"approve"`** or **`"block"`**. Must be **different** from the system’s decision. Ignored when `action` is `"accept"`. |
| `note` | string | When `action` is **`"conflict"`** | conflict only | **Required and non-empty** when conflicting. Explain why you are overturning the system. Ignored when `action` is `"accept"`. |

---

## Option 1: Human accepts (agrees with system)

**Request:**
```json
{
  "risk_decision_id": "550e8400-e29b-41d4-a716-446655440000",
  "reviewer_id": "reviewer_123",
  "action": "accept"
}
```

- Do **not** send `final_decision` or `note` (or send empty; they are ignored).
- Backend sets the human’s final decision to the **system’s decision** and stores an empty note.

**Response (201):**
```json
{
  "human_review_id": "uuid",
  "risk_decision_id": "uuid",
  "action": "accept",
  "final_decision": "block",
  "note": "",
  "reviewed_at": "2026-02-07T12:00:00"
}
```
`final_decision` in the response will match the system decision.

---

## Option 2: Human conflicts (overturns system)

**Request:**
```json
{
  "risk_decision_id": "550e8400-e29b-41d4-a716-446655440000",
  "reviewer_id": "reviewer_123",
  "action": "conflict",
  "final_decision": "approve",
  "note": "Customer verified identity and source of funds; false positive on velocity."
}
```

- **`final_decision`** is **required** and must be **`"approve"`** or **`"block"`**.
- **`final_decision`** must **differ** from the system’s decision (e.g. system said block → human must send approve or block; if system said block, human must send approve).
- **`note`** is **required** and must be **non-empty** (after trimming). This is the explanation for the conflict and is shown on the admin “conflicted decisions” page.

**Response (201):**
```json
{
  "human_review_id": "uuid",
  "risk_decision_id": "uuid",
  "action": "conflict",
  "final_decision": "approve",
  "note": "Customer verified identity and source of funds; false positive on velocity.",
  "reviewed_at": "2026-02-07T12:00:00"
}
```

---

## Validation errors (400)

| Situation | Response body (example) |
|-----------|-------------------------|
| Missing or invalid `action` | `{"action": ["\"accept\" or \"conflict\" required."]}` |
| `action` is `"conflict"` but `final_decision` missing | `{"final_decision": ["Required when action is 'conflict'. Send 'approve' or 'block'."]}` |
| `action` is `"conflict"` but `note` empty or missing | `{"note": ["Required when action is 'conflict'. Explain why you are overturning the system decision."]}` |
| `action` is `"conflict"` but `final_decision` equals system decision | `{"final_decision": ["When conflicting, final_decision must differ from the system decision."]}` |
| `risk_decision_id` not found | `{"risk_decision_id": ["RiskDecision with this id does not exist."]}` |
| Decision is `"review"` (not approve/block) | `{"risk_decision_id": ["Only decisions 'approve' or 'block' can be human-reviewed."]}` |

---

## FE checklist

- [ ] **Accept flow:** Send only `risk_decision_id`, `reviewer_id`, `action: "accept"`. Do not require a note or final_decision in the UI.
- [ ] **Conflict flow:** Send `risk_decision_id`, `reviewer_id`, `action: "conflict"`, `final_decision` (the new outcome), and `note`. In the UI, **require** the note (e.g. “Reason for conflict (required)”) and disable submit until it’s non-empty. Ensure `final_decision` is the **opposite** of the system decision (e.g. if system = block, show “Approve” as the conflict option so the user picks approve).
- [ ] Show which decision the system made so the user knows what they’re accepting or conflicting.
- [ ] On 201, use `human_review_id` and/or show success; on 400, show the error message(s) from the response body.
