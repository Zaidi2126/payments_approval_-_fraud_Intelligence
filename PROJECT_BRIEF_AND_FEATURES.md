# AI-Powered Payments Approval & Fraud Intelligence — Project Brief & Implemented Features

*Stored reference from hackathon brief + current system. Use for pitch, judging, and alignment.*

---

## The Challenge

**How might we build an AI system that automates payment approvals and detects transaction fraud in real-time — turning a manual bottleneck into instant, intelligent decisions?**

---

## The Problem

Payments teams review hundreds of payout requests daily, checking multiple systems for each one. Meanwhile, fraud hides in plain sight because manual reviews can't keep pace with sophisticated patterns.

- "I approve payouts all day. Each one requires checking multiple systems for red flags. Most could be instant, but the system can't decide."
- "Client uses a restricted card. I see the error a day later, manually review the account, then lock it. By then, they've made more transactions."
- "Fraudster deposits, makes one tiny trade, withdraws immediately. I know the pattern, but I'm reviewing these cases one by one after they've already happened."
- "When a fraud incident hits — stolen cards, coordinated abuse — I prepare files to lock accounts, recover funds, notify clients. Takes hours. High error risk."

**Core issue:** Manual approval doesn't scale, and reactive fraud detection is always too late. AI can approve the legitimate and flag the suspicious — instantly.

---

## Why This Matters Now

- Low auto-approval rates — officers spending hours on routine decisions
- Fraud detected too late — card errors, patterns found after losses
- No real-time risk scoring — decisions on incomplete information
- Slow incident response — bulk actions require manual preparation
- Alert fatigue — false positives while real fraud slips through

**Result:** Legitimate customers wait, fraudsters exploit gaps, teams drown in reactive work.

---

## The Opportunity

### 1. Intelligent Payout Approval

- **Instant risk assessment:** Evaluate every payout against multiple fraud signals in seconds
- **Multi-signal decisioning:** Payment method status, velocity, geo, trading behaviour, history
- **Smart auto-approval:** Process clean payouts instantly with clear reasoning
- **Intelligent escalation:** Flag suspicious cases with evidence for human review
- **Continuous learning:** Improve accuracy from officer feedback

### 2. Real-Time Fraud Detection & Response

- **Behavioural patterns:** No-trade fraud, short-trade abuse, card testing, velocity abuse
- **Technical signals:** Card errors, failed logins, geo/VPN anomalies, device fingerprint
- **Automated response:** High → auto-lock/notify; Medium → flag/monitor; Low → approve/log
- **Bulk incident handling:** Bulk locks, fund recovery, auto-generated client comms
- **Real-time exposure:** Instant quantification of fraud ring impact

---

## Constraints

| Constraint | Rationale |
|------------|-----------|
| Must demo live | Show real automation with sample transactions |
| AI must add value | GenAI must be core (hackathon) |
| Explainable decisions | Every approval/block has clear reasoning |
| Real-time performance | Decisions in seconds |
| Human oversight | AI for routine; humans for edge cases |

### How we meet “AI must add value” (GenAI core to the solution)

We keep the **decision itself** deterministic (speed, auditability, no LLM in the critical path), but **GenAI is core** to making the system usable, explainable, and improvable:

- **Explainability:** Every decision gets LLM-generated **reasons** and **counterfactuals** (“why this fired”, “what would flip the decision”). Without GenAI you only get raw signal names; with it, officers get natural-language reasoning and actionable guidance.
- **Discovery:** **Emerging patterns** are signal combos from the engine; GenAI **describes** each pattern and recommends action. **Natural language queries** (“Show me accounts that deposited but traded minimally”) are interpreted by GenAI into filters and run against the data — the **interface** is GenAI.
- **Human-in-the-loop:** **Review explanation** (why sent for review), **override explanation** (system vs human), and **LLM-suggested weight adjustments** after overrides make feedback and learning actionable. GenAI turns override events into concrete tuning suggestions.
- **Operations:** **Risk trajectory summary**, **fraud network summary**, **exposure explanation**, **bulk incident client message**, and **daily report narrative** are all GenAI-generated. They turn metrics and graphs into readable, shareable insight.

So GenAI is not used to *make* the approve/block decision; it is used so that **every part of the product that explains, discovers, or improves** relies on GenAI. That satisfies “GenAI must be core to your solution” for the hackathon.

---

## Questions Worth Considering

- What signals are most predictive of fraud vs false alarms?
- How do you handle brand-new customers with no behavioural history?
- When should AI be conservative (block) vs aggressive (approve)?
- Can you detect fraud patterns that don't match any known typology?
- How do you balance speed (instant approval) with accuracy (catch fraud)?
- What's the right interface for fraud investigators reviewing alerts?
- Can the system explain why one withdrawal is approved and another flagged?

---

## What Would Blow Our Minds

- **Dramatic auto-approval increase:** Safely process most payouts instantly while keeping accuracy
- **Predictive fraud flagging:** Identify pre-fraud signatures before withdrawal attempt
- **Real-time pattern discovery:** Detect new fraud patterns and flag similar accounts
- **Incident response in seconds:** Detect fraud rings and execute bulk containment instantly
- **Learning from outcomes:** Measurable improvement in confidence from validated decisions
- **Natural language fraud queries:** e.g. "Show me accounts that deposited but traded minimally"
- **Fraud network visualisation:** Graph of connected accounts via shared devices / IPs / cards

---

## What’s Implemented (Current System)

*Aligned to the brief and judge-facing talking points. As many points as possible.*

**All features at a glance:** (official challenge feature) Payout decision (single) • (official challenge feature) Payout history (filters) • (official challenge feature) Risk trajectory (points, trend, momentum, chat) • (official challenge feature) Human reviews (create, list) • (official challenge feature) Review/override explanations (LLM) • (official challenge feature) Daily metrics • (official challenge feature) Calibration stats • (bonus feature) **Slack — daily report to Slack** (API + CLI) • (official challenge feature) Conflicted decisions (list, approve-for-learning) • (bonus feature) Admin weights • (bonus feature) Fraud readiness simulate (scenarios, optional rating explanation) • (official challenge feature) Emerging patterns (with cases/account_ids, optional refresh_descriptions) • (official challenge feature) Fraud network (graph + optional LLM summary) • (official challenge feature) Exposure (user_ids, days + LLM explanation) • (official challenge feature) Bulk incident (flag + draft client message) • (official challenge feature) Natural language query (question → filters → results with summary + transactions) • (bonus feature) Health check • (official challenge feature) Seed & management commands (recompute, seed_demo_data); (bonus feature) send_daily_slack_summary.

### 1. Risk Trajectory & Momentum *(official challenge feature — predictive fraud flagging)*

- **Per-user risk timeline:** `GET /api/users/<user_id>/risk-trajectory?days=7` — time-ordered points (ts, risk_score, decision) per payout.
- **Configurable window:** Query param `days` (1–365).
- **Trend:** `rising` | `falling` | `flat` from first vs last risk score.
- **Momentum:** Integer -100..100 (score delta; positive = risk increasing).
- **Summary:** 2–3 sentence narrative (LLM or fallback).
- **Chat structure:** Response includes `chat: [{ role: "user" }, { role: "assistant", content: summary }]` for UI.
- **Pitch:** "We don’t just score a payout. We track how risk evolves per user over time and react before fraud happens."

### 2. Fraud Readiness Simulation *(bonus feature)*

- **Simulated attacks:** `POST /api/fraud-readiness/simulate` — run fraud patterns against the engine *before* fraud happens.
- **Base payload:** user_id, amount, currency, payment_method_id, payment_method_age_days, country, ip_address, vpn_detected, total_trades, total_trade_volume + optional velocity, expected_country, card_decline_count_24h, failed_login_count_24h, device_id / device_shared_account_count, account_flagged.
- **Nine patterns:** no_trade_fraud, short_trade_abuse, new_payment_method_risk, velocity_abuse, geo_vpn_anomaly, card_decline_risk, failed_login_risk, device_shared_risk, account_flagged_risk.
- **Readiness level per scenario:** low (&lt;25), medium (25–59), high (≥60) from risk score.
- **Snapshot persistence:** Each scenario creates a `FraudReadinessSnapshot` row.
- **Rating explanation:** Each result includes `rating_explanation` — LLM when `include_rating_explanation: true` (slower), else short fallback (fast, avoids client timeout).
- **Pitch:** "We don’t just detect fraud. We continuously test our defenses by simulating top fraud patterns and measuring readiness."

### 3. Confidence & Regret Index *(official challenge feature — learning from outcomes, explainable)*

- **Confidence score (0–100):** From (A) margin from decision thresholds, (B) number of triggered signals, (C) missing-data penalty (expected_country, velocity).
- **Confidence band:** low &lt; 50, medium 50–79, high ≥ 80 — in `confidence_and_regret_index`.
- **Regret level:** low (&lt;200), medium (200–1000), high (&gt;1000) by amount — "how bad if we're wrong".
- **Calibration stats:** Per-date accuracy %, overconfidence_rate, underconfidence_rate, avg_confidence_correct/incorrect; recomputed from HumanReview.
- **API:** `GET /api/metrics/calibration`; used in daily report and Slack.
- **Pitch:** "Our system knows when it might be wrong and measures its own decision quality over time."

### 4. Human-in-the-Loop Feedback Loop *(official challenge feature — intelligent escalation, human oversight, continuous learning)*

- **AI decides:** Engine approve/review/block; humans handle edge cases and overrides.
- **Create review:** `POST /api/reviews` — risk_decision_id, reviewer_id, final_decision (approve|block), note (optional).
- **History includes human outcome:** human_final_decision, human_reviewed_at, human_overrode in history.
- **Review explanation:** `GET /api/decisions/&lt;risk_decision_id&gt;/review-explanation` — LLM paragraph on why sent for review.
- **Override explanation:** When human overturns, admin sees LLM system_explanation + human summary (filled on first view).
- **Conflicted decisions:** `GET /api/admin/conflicted-decisions` — where human ≠ system decision.
- **Approve for learning:** `POST /api/admin/conflicted-decisions/&lt;review_id&gt;/approve` — mark override for weight tuning; updates SystemScore.
- **Pitch:** "Humans don’t replace the AI. They train and calibrate it continuously."

### 5. Explainability with Counterfactuals *(official challenge feature — explainable decisions)*

- **Triggered signals:** List of signal names in every decision response and history.
- **Reasons:** One sentence per signal — why that signal fired (LLM or deterministic from engine/explanations).
- **Counterfactuals:** Actionable “how to flip the decision” (e.g. use older payment method, increase trade volume)
- **Pitch:** "We’re not just saying why it failed. We’re saying how to make it pass."

- **Stored on RiskDecision:** reasons and counterfactuals persisted for audit and display.

### 6. Deterministic Engine vs Generative AI *(official challenge feature — AI must add value, real-time performance)*

- **Decision path:** 100% deterministic — run_all_detectors → compute_risk_score → get_decision, get_regret_level, get_confidence_score. No LLM in the critical path.
- **GenAI used for:** (1) reasons & counterfactuals (with deterministic fallback), (2) risk trajectory summary, (3) review explanation, (4) override explanation, (5) daily report narrative, (6) emerging pattern description, (7) simulator rating explanation, (8) fraud network summary, (9) exposure explanation, (10) bulk incident client message, (11) NL query → structured filters, (12) weight suggestion after override (admin).
- **Pitch:** "We don’t let LLMs make financial decisions. We use them to make decisions understandable and improvable."

### 7. End-to-End Demo & Real Metrics *(official challenge feature — demo live, instant decisions)*

- **Live decision:** `POST /api/payouts/decision` — full payload; creates PayoutRequest + RiskDecision; returns decision, risk_score, confidence_score, regret_level, triggered_signals, reasons, counterfactuals, confidence_and_regret_index.
- **History:** `GET /api/payouts/history` — optional filters: limit, days, decision, user_id; includes human review fields.
- **Risk trajectory:** Per-user trend and momentum (see §1).
- **Simulate:** Fraud readiness (see §2).
- **Daily metrics:** `GET /api/metrics/daily` — total_requests, auto_approved, auto_blocked, sent_to_review, accuracy_percent, false_positive_rate, false_negative_rate.
- **Calibration:** `GET /api/metrics/calibration` (see §3).
- **Fraud network:** `GET /api/fraud-network?user_id=X&summary=1` — nodes, edges (payment_method_id, ip_address, device_id), optional LLM summary.
- **Exposure:** `GET /api/exposure?user_ids=id1,id2&days=30` — total withdrawal volume, currency, user_count, optional LLM explanation.
- **Bulk incident:** `POST /api/incidents/bulk-action` — user_ids, action, reason; creates AccountFlag rows; optional LLM-drafted client message.
- **Natural language query:** `POST /api/query` — body `{"question": "..."}` → LLM filters → DB query → results with per-user summary + up to 10 recent transactions per user (payout_request_id, amount, currency, decision, risk_score, created_at).
- **Emerging patterns:** `GET /api/patterns/emerging?days=7` — signal combos (count ≥3), case_count, LLM description (cached; optional refresh_descriptions=1), account_ids, cases (transaction details per case).

### 8. Fraud Signals & Detectors (Deterministic) *(official challenge feature — multi-signal decisioning, behavioural + technical signals)*

- **no_trade_fraud:** total_trades ≤ 1, total_trade_volume very low, payment_method_age_days ≤ 7.
- **short_trade_abuse:** total_trades ≤ 3 and total_trade_volume &lt; 50% of amount.
- **new_payment_method_risk:** payment_method_age_days ≤ 3.
- **velocity_abuse:** withdrawals_last_1h ≥ 3 OR withdrawals_last_24h ≥ 10 OR deposits_last_1h ≥ 5.
- **geo_vpn_anomaly:** vpn_detected and (expected_country missing or ≠ country).
- **card_decline_risk:** card_decline_count_24h ≥ 2.
- **failed_login_risk:** failed_login_count_24h ≥ 3.
- **device_shared_risk:** device_shared_account_count ≥ 3 (same device across accounts).
- **account_flagged_risk:** account_flagged true (bulk-flagged user).
- **Scoring:** Additive signal weights (configurable via EngineConfig); score capped 0–100. Example weights: no_trade_fraud 40, account_flagged_risk 100.

### 9. Decision Bands & Thresholds *(official challenge feature — smart auto-approval, automated response)*

- **Approve:** risk_score 0–24.
- **Review:** risk_score 25–59.
- **Block:** risk_score 60–100.
- **Regret:** low &lt; 200, medium 200–1000, high &gt; 1000 (amount in currency units).

### 9a. How Risk Score, Signal Points, and Confidence Work (Plain Explanation) *(official challenge feature — supports decisioning & explainability)*

**Risk score (0–100)**  
- This is the **single number** that drives the decision: approve, review, or block.  
- It is **not** a probability. It is the **sum of points** from every fraud signal that fired for this payout.  
- **How it’s built:**  
  - Start at **0**.  
  - Run all detectors (no_trade_fraud, velocity_abuse, geo_vpn_anomaly, etc.).  
  - For each detector that **fires**, add that signal’s **weight** (points).  
  - Sum all those points and **cap the total at 100**.  
- **Example:** If only `new_payment_method_risk` (15) and `velocity_abuse` (30) fire → risk_score = 15 + 30 = **45** → decision = **review** (25–59).  
- **Example:** If `no_trade_fraud` (40) + `short_trade_abuse` (25) + `new_payment_method_risk` (15) fire → 80 → **block** (60–100).

**Risk points / signal points (the weights)**  
- Each **fraud signal** has a fixed **weight** (points). When that signal is triggered, that many points are added to the risk score.  
- Weights are **configurable** in the DB (EngineConfig key `signal_weights`); if not set, the engine uses code defaults.  
- **Default weights (points per signal):**

| Signal | Points (weight) |
|--------|------------------|
| no_trade_fraud | 40 |
| short_trade_abuse | 25 |
| new_payment_method_risk | 15 |
| velocity_abuse | 30 |
| geo_vpn_anomaly | 25 |
| card_decline_risk | 35 |
| failed_login_risk | 30 |
| device_shared_risk | 40 |
| account_flagged_risk | 100 |

- So “risk points” = the points contributed by each triggered signal; **risk score** = sum of those points (capped at 100).

**The points the system gives itself (confidence score 0–100)**  
- The system also outputs a **confidence score** (0–100). This is **how sure the system is** about its own decision — a self-assessment, not the risk of the user.  
- It is built from three **components** (all in the 0–100 range after combining):

1. **Margin (up to 50 points)**  
   - How far the risk score is from the **nearest decision boundary** (24, 25, 59, 60).  
   - Deep in approve (e.g. score 5) or deep in block (e.g. 90) → high margin → more points.  
   - Right on the edge (e.g. 24 or 25) → low margin → fewer points.  
   - Formula: margin_score = min(50, margin × 2).

2. **Signal bonus (up to 30 points)**  
   - More **triggered signals** → more evidence → higher confidence.  
   - Formula: min(30, number_of_signals × 10). So 0 signals → 0, 3 signals → 30.

3. **Missing-data penalty (0, 10, or 20 points subtracted)**  
   - No `expected_country` → −10.  
   - No velocity data (withdrawals_last_1h, withdrawals_last_24h, deposits_last_1h) → −10.  
   - So confidence is reduced when the system had less context.

- **Final confidence** = margin_score + signals_bonus − penalty, then clamped to 0–100.  
- **Confidence band** (for display): low &lt; 50, medium 50–79, high ≥ 80.

**Summary**  
- **Risk score** = sum of **signal points** (weights) for all triggered signals, capped at 100 → drives **approve / review / block**.  
- **Signal points** = the weight (points) each detector adds when it fires; configurable.  
- **Confidence score** = the points the system gives itself for “how sure I am” (margin + signal bonus − missing-data penalty), 0–100.

### 10. Data Models & Persistence *(supports all official + bonus features)*

- **PayoutRequest:** id, user_id, amount, currency, payment_method_id, payment_method_age_days, country, ip_address, vpn_detected, total_trades, total_trade_volume, card_decline_count_24h, failed_login_count_24h, device_id, created_at.
- **RiskDecision:** 1:1 with PayoutRequest; risk_score, decision, confidence_score, regret_level, triggered_signals, reasons, counterfactuals, review_explanation.
- **HumanReview:** n:1 with RiskDecision; reviewer_id, final_decision, note, system_explanation, approved_for_learning.
- **DailyMetrics:** per date — total_requests, auto_approved, auto_blocked, sent_to_review, accuracy_percent, false_positive_rate, false_negative_rate.
- **CalibrationStats:** per date — reviewed_count, correct/incorrect, accuracy_percent, avg_confidence_correct/incorrect, overconfidence_rate, underconfidence_rate.
- **FraudReadinessSnapshot:** simulated_pattern, simulated_risk_score, readiness_level.
- **EmergingPattern:** signal_combo, case_count, description (LLM), first_seen, last_seen.
- **AccountFlag:** user_id, reason — used by engine for account_flagged_risk.
- **EngineConfig:** key-value (e.g. signal_weights) for admin tuning; engine reads at runtime.
- **SystemScore:** singleton — tracks "how well the system is doing" from accepted vs overridden decisions.

### 11. Admin & Operations *(mix: official — conflicted/learning; bonus — admin weights, commands)*

- **Conflicted decisions:** List and approve-for-learning (see §4).
- **Admin weights:** `GET /api/admin/weights` — current signal weights (from EngineConfig or defaults).
- **Management commands:** `recompute_daily_metrics`, `recompute_calibration_stats`, `seed_demo_data` (optional `--clear`, `--reviews`), `send_daily_slack_summary` (see §11a).

### 11a. Slack Integration (Daily Report to Slack) *(bonus feature)*

- **Feature:** Send the latest daily payouts summary and an LLM-generated detailed report to a Slack channel via an incoming webhook.
- **API:** `POST /api/reports/send-daily-summary`  
  - **Body (optional):** `{ "slack_webhook_url": "https://hooks.slack.com/services/..." }`. If provided, that URL is used for this request only; otherwise the server uses `SLACK_WEBHOOK_URL` from the environment.  
  - **Behaviour:** Loads latest DailyMetrics and CalibrationStats for that date, builds a report (total_requests, auto_approved, auto_blocked, sent_to_review, accuracy_percent, overconfidence_rate, underconfidence_rate), calls the LLM to generate a long-form detailed narrative (generate_daily_report), then POSTs a Slack attachment (title "Daily Payouts Summary", fields + full report text, green color) to the webhook.  
  - **Response:** `{ "success": true, "message": "Daily report sent to Slack.", "report": { ... } }` or 400 if webhook missing, 404 if no metrics, 502 if Slack request fails.
- **CLI (scheduled / cron):** `python manage.py send_daily_slack_summary` — uses `SLACK_WEBHOOK_URL` from `.env`; posts same daily summary + LLM report to Slack. Exits with a message if webhook or metrics are missing.
- **Config:** Set `SLACK_WEBHOOK_URL` in `.env` for the management command; or have the frontend pass `slack_webhook_url` in the API body so no env is needed for the API.
- **Pitch:** "Daily digest of payouts and calibration goes straight to Slack so the team stays informed without opening the dashboard."

### 12. LLM Use Cases (All) *(official: explanations, review/override, daily report narrative, NL query, pattern description, fraud network/exposure/bulk messaging; bonus: weight suggestion, simulator rating explanation)*

- **generate_explanations:** Reasons and counterfactuals for a decision (with deterministic fallback).
- **generate_trajectory_summary:** 2–3 sentence risk trajectory summary.
- **generate_daily_report:** Long-form daily report from metrics + calibration.
- **generate_review_explanation:** Why a payout was sent for review.
- **generate_override_explanation:** Why the system decided + what the human did.
- **suggest_weight_adjustment:** After human override, suggest new signal weights (admin).
- **generate_fraud_network_summary:** 2–3 sentence summary of linked accounts.
- **generate_exposure_explanation:** One-sentence exposure for managers.
- **generate_bulk_incident_message:** Draft client message for bulk-flagged users.
- **interpret_natural_language_query:** Question → structured filters (JSON).
- **describe_emerging_pattern:** One sentence + recommendation per signal combo.
- **explain_simulator_rating:** Why a simulated scenario got its score/decision.
- **LLM use counter:** Global count printed on each successful LLM call for cost/usage visibility.

### 13. Config & Tuning *(official challenge feature — continuous learning / tuning)*

- **Signal weights:** Stored in EngineConfig key `signal_weights`; engine uses when present else code defaults.
- **OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TIMEOUT_SECONDS, OPENAI_MAX_OUTPUT_TOKENS:** Env-driven; LLM calls skip or fallback when key missing.

### 14. Seed & Demo *(official challenge feature — must demo live)*

- **seed_demo_data:** Curated dataset: approve (low/medium regret), review (1–2 signals), block (multi-signal), one per pattern, trajectory user (4 payouts), minimal_trader (NL query), fraud network users (shared pm_shared_1, dev_shared_1), human reviews. Optional `--clear` to wipe payout-related data first; then `recompute_daily_metrics` and `recompute_calibration_stats`.

### 15. Health & Observability *(bonus feature)*

- **GET /health:** Simple health check.
- **Debug prints:** Simulate flow and simulator LLM log progress (can be removed for production).

---

## Mapping “What Would Blow Our Minds” → Implemented

*All rows below are **official challenge feature** (from the challenge's "What Would Blow Our Minds").*

| Ask | Implemented |
|-----|-------------|
| Dramatic auto-approval increase | Engine approve 0–24; review 25–59; block 60+; confidence/regret and calibration show safe automation |
| Predictive fraud flagging | Risk trajectory + momentum; emerging patterns; NL query for “traded minimally” etc. |
| Real-time pattern discovery | Emerging patterns API (combos from block/review, LLM-described); cases per pattern |
| Incident response in seconds | Bulk incident API (flag accounts, draft message); fraud network for linked accounts |
| Learning from outcomes | Calibration stats from HumanReview; accuracy, over/underconfidence; admin conflicted-decisions + approve-for-learning |
| Natural language fraud queries | `POST /api/query` with question → LLM filters → DB query → results with account summary + transactions |
| Fraud network visualisation | `GET /api/fraud-network` — nodes/edges by shared payment_method, IP, device_id; optional LLM summary |

---

## Quick API Reference (for demo)

- `POST /api/payouts/decision` — single payout decision (body: user_id, amount, currency, payment_method_id, payment_method_age_days, country, ip_address, vpn_detected, total_trades, total_trade_volume, optional: expected_country, withdrawals_*, deposits_*, card_decline_count_24h, failed_login_count_24h, device_id)
- `GET /api/payouts/history` — decision history with filters
- `GET /api/users/<user_id>/risk-trajectory?days=7` — points, trend, momentum, summary, chat
- `POST /api/fraud-readiness/simulate` — scenarios (default 5 patterns), optional `include_rating_explanation: true` for LLM
- `GET /api/metrics/daily` — daily metrics
- `GET /api/metrics/calibration` — calibration stats
- `POST /api/reports/send-daily-summary` — send daily report (metrics + LLM narrative) to Slack; body optional: `{ "slack_webhook_url": "https://hooks.slack.com/..." }`; else uses `SLACK_WEBHOOK_URL` from env
- `POST /api/reviews` — create human review (risk_decision_id, final_decision, note)
- `GET /api/fraud-network?user_id=X&summary=1` — graph + optional LLM summary
- `GET /api/exposure?user_ids=id1,id2&days=30` — total exposure + LLM explanation
- `POST /api/incidents/bulk-action` — bulk flag + optional client message
- `POST /api/query` — body `{"question": "..."}` → interpreted_filters, results (with summary + transactions)
- `GET /api/patterns/emerging?days=7` — patterns with case_count, description, account_ids, cases (transaction details); optional `refresh_descriptions=1`

---

*Last updated to include: labelling of every feature as (official challenge feature) or (bonus feature) per the challenge brief; risk trajectory chat, simulator rating_explanation, NL query, emerging patterns cases/account_ids, exposure, seed_demo_data, confidence/regret and calibration, Slack §11a.*
