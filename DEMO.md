# deriv_guard — Demo Runbook

Quick setup and curl commands to demo the system with realistic data.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
```

## Seed demo data

Creates payout requests, risk decisions, and human reviews so you can demo daily metrics, calibration, risk trajectory, and fraud readiness in minutes.

```bash
# Default: 3 days, 50 payouts/day, 20% get a human review
python manage.py seed_demo_data

# Custom volume
python manage.py seed_demo_data --days 5 --per_day 100 --reviews 0.25
```

After seeding, daily metrics and calibration stats are recomputed automatically.

## Start server

```bash
python manage.py runserver
```

Base URL: `http://127.0.0.1:8000`

---

## Curl commands to show off

### 1) Create a payout decision

```bash
curl -s -X POST http://127.0.0.1:8000/api/payouts/decision \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "amount": 150.50,
    "currency": "USD",
    "payment_method_id": "pm_abc",
    "payment_method_age_days": 10,
    "country": "US",
    "ip_address": "192.168.1.1",
    "vpn_detected": false,
    "total_trades": 5,
    "total_trade_volume": 500
  }'
```

### 2) Create a human review

Use the `risk_decision_id` from the decision response above.

```bash
curl -s -X POST http://127.0.0.1:8000/api/reviews \
  -H "Content-Type: application/json" \
  -d '{
    "risk_decision_id": "<PASTE_RISK_DECISION_ID>",
    "reviewer_id": "reviewer_1",
    "final_decision": "approve"
  }'
```

### 3) Daily metrics

```bash
curl -s http://127.0.0.1:8000/api/metrics/daily
```

### 4) Calibration metrics

```bash
curl -s http://127.0.0.1:8000/api/metrics/calibration
```

### 5) Risk trajectory (by user)

After seeding, use a demo user id (e.g. `demo_user_0_0`).

```bash
curl -s "http://127.0.0.1:8000/api/users/demo_user_0_0/risk-trajectory?days=7"
```

### 6) Fraud readiness simulation

```bash
curl -s -X POST http://127.0.0.1:8000/api/fraud-readiness/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "sim_user",
    "amount": 200,
    "currency": "USD",
    "payment_method_id": "pm_1",
    "payment_method_age_days": 5,
    "country": "US",
    "ip_address": "10.0.0.1",
    "vpn_detected": false,
    "total_trades": 10,
    "total_trade_volume": 1000
  }'
```

---

## Demo flow (after seeding)

1. **Start server:** `python manage.py runserver`
2. **Daily metrics:** `curl -s http://127.0.0.1:8000/api/metrics/daily`
3. **Calibration:** `curl -s http://127.0.0.1:8000/api/metrics/calibration`
4. **Risk trajectory:** `curl -s "http://127.0.0.1:8000/api/users/demo_user_0_1/risk-trajectory?days=7"`
5. **Create a decision:** use curl #1 above
6. **Create a review:** use curl #2 with the returned `risk_decision_id`
7. **Fraud readiness:** use curl #6 above
