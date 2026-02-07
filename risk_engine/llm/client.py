"""
OpenAI client for generating reasons and counterfactuals. Falls back to deterministic text if key missing or call fails.
"""

import json

# Global count of LLM API calls (successful); printed each time so you can track usage
LLM_USE_COUNT = 0


def _llm_used(feature: str) -> None:
    global LLM_USE_COUNT
    LLM_USE_COUNT += 1
    print(f"LLM used {LLM_USE_COUNT} ({feature})")
import os
import re
from pathlib import Path
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv

# Load .env from project root (same place as manage.py) so it's always found
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")

# Fallback: use deterministic explanations from engine
from risk_engine.engine.explanations import get_reasons, get_counterfactuals
from risk_engine.engine.types import EngineInput


def _payload_to_engine_input(payload: dict) -> EngineInput:
    """Build EngineInput from payload["engine_input"] dict for fallback."""
    ei = payload["engine_input"]
    return EngineInput(
        user_id=str(ei.get("user_id", "")),
        amount=Decimal(str(ei.get("amount", 0))),
        currency=str(ei.get("currency", "USD")),
        payment_method_id=str(ei.get("payment_method_id", "")),
        payment_method_age_days=int(ei.get("payment_method_age_days", 0)),
        country=str(ei.get("country", "")),
        ip_address=str(ei.get("ip_address", "")),
        vpn_detected=bool(ei.get("vpn_detected", False)),
        total_trades=int(ei.get("total_trades", 0)),
        total_trade_volume=Decimal(str(ei.get("total_trade_volume", 0))),
        withdrawals_last_1h=int(ei["withdrawals_last_1h"]) if ei.get("withdrawals_last_1h") is not None else None,
        withdrawals_last_24h=int(ei["withdrawals_last_24h"]) if ei.get("withdrawals_last_24h") is not None else None,
        deposits_last_1h=int(ei["deposits_last_1h"]) if ei.get("deposits_last_1h") is not None else None,
        expected_country=str(ei["expected_country"]) if ei.get("expected_country") is not None else None,
    )


def _fallback_explanations(payload: dict) -> dict[str, list[str]]:
    """Return reasons and counterfactuals using deterministic engine logic."""
    engine_input = _payload_to_engine_input(payload)
    signals = payload.get("triggered_signals") or []
    return {
        "reasons": get_reasons(engine_input, signals),
        "counterfactuals": get_counterfactuals(engine_input, signals),
    }


def _parse_llm_json(content: str) -> dict[str, list[str]] | None:
    """Parse LLM response as JSON; expect keys reasons and counterfactuals. Tolerates markdown and extra text."""
    if not content or not isinstance(content, str):
        return None
    content = content.strip()
    # Remove markdown code block if present (e.g. ```json\n{...}\n```)
    content = re.sub(r"^```(?:json)?\s*\n?", "", content)
    content = re.sub(r"\n?\s*```\s*$", "", content)
    content = content.strip()
    # If there's extra text before/after, find the first { and last } and parse that
    start = content.find("{")
    if start != -1:
        end = content.rfind("}")
        if end != -1 and end >= start:
            content = content[start : end + 1]
    try:
        data = json.loads(content)
        reasons = data.get("reasons")
        counterfactuals = data.get("counterfactuals")
        if isinstance(reasons, list) and isinstance(counterfactuals, list):
            return {
                "reasons": [str(x).strip() for x in reasons if x is not None],
                "counterfactuals": [str(x).strip() for x in counterfactuals if x is not None],
            }
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def generate_explanations(payload: dict[str, Any]) -> dict[str, list[str]]:
    """
    Generate reasons and counterfactuals via OpenAI. On missing key or failure, return fallback with same shape.

    payload must include: engine_input (serializable dict), triggered_signals, decision, risk_score, confidence_score, regret_level.
    Returns: {"reasons": [...], "counterfactuals": [...]}
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        print("LLM not used")
        return _fallback_explanations(payload)

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    try:
        timeout = max(5, min(60, int(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))))
    except (TypeError, ValueError):
        timeout = 20
    try:
        max_tokens = max(100, min(1000, int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "500"))))
    except (TypeError, ValueError):
        max_tokens = 500

    system_prompt = """You are a fraud risk analyst. Output only valid JSON, no markdown, no extra text.
Schema: {"reasons": ["string", ...], "counterfactuals": ["string", ...]}
- reasons: one short judge-friendly sentence per triggered signal, referencing the field values that caused it.
- counterfactuals: one short actionable suggestion per signal (what would reduce risk for that signal).
- Order must match the triggered_signals list: first reason/counterfactual for first signal, etc.
- Handle these signal names: no_trade_fraud, short_trade_abuse, new_payment_method_risk, velocity_abuse, geo_vpn_anomaly."""

    user_prompt = (
        f"Triggered signals: {payload.get('triggered_signals', [])}. "
        f"Decision: {payload.get('decision')}. Risk score: {payload.get('risk_score')}. "
        f"Confidence: {payload.get('confidence_score')}. Regret level: {payload.get('regret_level')}. "
        f"Engine input (key facts): {json.dumps(payload.get('engine_input', {}), default=str)}. "
        "Output JSON with reasons and counterfactuals arrays only."
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_completion_tokens=max_tokens,
            timeout=timeout,
        )
        content = (resp.choices[0].message.content or "").strip()
        parsed = _parse_llm_json(content)
        if parsed:
            _llm_used("explanations")
            return parsed
        print("LLM not used (response was not valid JSON)")
    except Exception as e:
        print(f"LLM not used ({type(e).__name__}: {e})")
    return _fallback_explanations(payload)


def generate_trajectory_summary(
    user_id: str,
    window_days: int,
    points: list[dict],
    trend: str,
    momentum: int,
    fallback_summary: str,
) -> str:
    """
    Generate a short natural-language summary for risk trajectory via LLM.
    Returns fallback_summary if API key missing or call fails.
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return fallback_summary

    n = len(points)
    if n == 0:
        return fallback_summary

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    try:
        to = max(5, min(60, int(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))))
    except (TypeError, ValueError):
        to = 20
    try:
        max_tok = max(150, min(400, int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "500"))))
    except (TypeError, ValueError):
        max_tok = 250

    first_score = points[0]["risk_score"]
    last_score = points[-1]["risk_score"]
    # Last few scores and decisions for context (e.g. last 10)
    recent = points[-10:] if len(points) >= 10 else points
    recent_scores = [p["risk_score"] for p in recent]
    recent_decisions = [p["decision"] for p in recent]
    approved_count = sum(1 for d in recent_decisions if str(d).lower() == "approved")
    declined_count = len(recent_decisions) - approved_count

    system_instruction = (
        "You are a fraud risk analyst. Given a user's risk trajectory (scores and decisions over time), "
        "write a 2–3 sentence summary that: (1) briefly describes the current trend and level of risk; "
        "(2) gives a clear prediction about fraud likelihood in the near term—e.g. 'elevated risk of a fraudulent "
        "transaction in the next 5–10 transactions', 'likely to attempt fraud in the next week', 'low risk in the "
        "short term', or 'watchlist: consider extra scrutiny in the next 2 weeks'. Be specific (next N transactions "
        "or next week/2 weeks). Output plain text only, no bullets or JSON."
    )
    user_prompt = (
        f"User {user_id}, last {window_days} days. "
        f"Total decisions: {n}. Risk scores (oldest to newest): {recent_scores}. "
        f"Decisions: {recent_decisions}. Approved: {approved_count}, Declined: {declined_count}. "
        f"First score: {first_score}, last score: {last_score}. Trend: {trend}. Momentum: {momentum}. "
        "Write the 2–3 sentence predictive summary as described."
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt},
            ],
            max_completion_tokens=max_tok,
            timeout=to,
        )
        content = (resp.choices[0].message.content or "").strip()
        if content:
            _llm_used("trajectory summary")
            return content
        print("LLM not used for trajectory (empty response from API)")
    except Exception as e:
        err_msg = str(e).lower()
        # If configured model is invalid (e.g. gpt-5-mini), retry with gpt-4o-mini
        if model != "gpt-4o-mini" and ("model" in err_msg or "invalid" in err_msg or "not found" in err_msg):
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_completion_tokens=max_tok,
                    timeout=to,
                )
                content = (resp.choices[0].message.content or "").strip()
                if content:
                    _llm_used("trajectory summary fallback model")
                    return content
            except Exception:
                pass
        print(f"LLM not used for trajectory ({type(e).__name__}: {e})")
    return fallback_summary


def _fallback_daily_report(context: dict) -> str:
    """Build a detailed deterministic report when LLM is unavailable."""
    date = context.get("date", "")
    total = context.get("total_requests", 0)
    auto_approved = context.get("auto_approved", 0)
    auto_blocked = context.get("auto_blocked", 0)
    sent_to_review = context.get("sent_to_review", 0)
    cal = context.get("calibration") or {}

    pct = lambda a, t: f" ({100 * a / t:.1f}%)" if t else ""
    lines = [
        f"# Daily Payouts Report — {date}",
        "",
        "## Volume & throughput",
        f"- Total payout requests: {total}.",
        f"- Auto-approved: {auto_approved}{pct(auto_approved, total)}." if total else "- No requests.",
        f"- Auto-blocked: {auto_blocked}{pct(auto_blocked, total)}." if total else "",
        f"- Sent to human review: {sent_to_review}{pct(sent_to_review, total)}." if total else "",
        "",
    ]
    if cal.get("reviewed_count"):
        acc = cal.get("accuracy_percent", 0)
        over = cal.get("overconfidence_rate", 0)
        under = cal.get("underconfidence_rate", 0)
        lines.extend([
            "## Accuracy & calibration",
            f"- Decisions reviewed by humans: {cal.get('reviewed_count')} (correct: {cal.get('correct_count')}, incorrect: {cal.get('incorrect_count')}).",
            f"- Accuracy: {acc}%.",
            f"- Overconfidence rate (wrong but confident): {over}%.",
            f"- Underconfidence rate (right but low confidence): {under}%.",
            "",
            "## Summary",
            "Report generated without AI. Enable OPENAI_API_KEY for an AI-generated detailed analysis and recommendations.",
        ])
    return "\n".join(lines)


def generate_daily_report(context: dict) -> str:
    """
    Generate a very detailed daily payouts/fraud report via LLM from a context dict.
    context should include: date, total_requests, auto_approved, auto_blocked, sent_to_review,
    and optionally calibration (accuracy_percent, overconfidence_rate, underconfidence_rate,
    reviewed_count, correct_count, incorrect_count, avg_confidence_correct, avg_confidence_incorrect),
    and optionally decisions_breakdown (e.g. risk_score_distribution, avg_risk_score).
    Returns fallback report if API key missing or call fails.
    """
    fallback = _fallback_daily_report(context)

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return fallback

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    try:
        to = max(10, min(90, int(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))))
    except (TypeError, ValueError):
        to = 30
    try:
        max_tok = max(500, min(2000, int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "500"))))
    except (TypeError, ValueError):
        max_tok = 1500

    # Build a rich prompt
    import json as _json
    data_blob = _json.dumps(context, indent=2, default=str)

    system_instruction = (
        "You are a senior fraud and risk operations analyst writing an internal daily report for leadership. "
        "Given JSON data for one day's payout decisions and calibration metrics, write a VERY DETAILED report. "
        "Use clear sections with headers. Include: (1) Executive summary — 3–4 sentences on the day's outcome and risk level. "
        "(2) Volume and throughput — total requests, auto-approved vs auto-blocked vs sent to review, percentages and what they imply. "
        "(3) Accuracy and calibration — accuracy %, overconfidence and underconfidence rates, what they mean for model trust and reviewer workload. "
        "(4) Risk and pattern insights — any notable distribution of risk scores or decisions; highlight anomalies or trends. "
        "(5) Recommendations — 3–5 concrete actions: e.g. tune thresholds, review specific bands, add monitoring, or retrain. "
        "Write in professional but readable English. Use bullet points or short paragraphs. Output plain text (no JSON). Length: at least 400 words."
    )
    user_prompt = (
        f"Daily report data (JSON):\n{data_blob}\n\n"
        "Write the full detailed report as described above."
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt},
            ],
            max_completion_tokens=max_tok,
            timeout=to,
        )
        content = (resp.choices[0].message.content or "").strip()
        if content:
            _llm_used("daily report")
            return content
        print("LLM not used for daily report (empty response)")
    except Exception as e:
        err_msg = str(e).lower()
        if model != "gpt-4o-mini" and ("model" in err_msg or "invalid" in err_msg or "not found" in err_msg):
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_completion_tokens=max_tok,
                    timeout=to,
                )
                content = (resp.choices[0].message.content or "").strip()
                if content:
                    _llm_used("daily report fallback model")
                    return content
            except Exception:
                pass
        print(f"LLM not used for daily report ({type(e).__name__}: {e})")
    return fallback


def generate_review_explanation(context: dict) -> str:
    """
    Generate an explanation for the user: why this payout was sent for review (why the system could not auto-approve or auto-block).
    context: risk_score, triggered_signals, reasons, payout_summary (optional).
    Returns fallback text if LLM unavailable.
    """
    fallback = (
        f"Risk score {context.get('risk_score', 0)} fell in the review band (25–59). "
        f"Signals: {context.get('triggered_signals', [])}. "
        f"Reasons: {context.get('reasons', [])}. "
        "A human decision is required to approve or block."
    )
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return fallback

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    try:
        to = max(5, min(30, int(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))))
    except (TypeError, ValueError):
        to = 15
    import json as _json
    data_blob = _json.dumps(context, indent=2, default=str)
    prompt = (
        "You are a fraud risk analyst. A payout was sent for human review (the system did not auto-approve or auto-block). "
        "Given the following JSON (risk score, triggered signals, reasons), write one short paragraph in plain text "
        "explaining why the system could not make a definitive decision: what put the risk in the 'review' band and what "
        "the reviewer should consider. Be clear and concise. No bullet points. Output only the paragraph.\n\n"
        f"Data:\n{data_blob}"
    )
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=250,
            timeout=to,
        )
        content = (resp.choices[0].message.content or "").strip()
        if content:
            _llm_used("review explanation")
            return content
    except Exception as e:
        print(f"LLM not used for review explanation ({type(e).__name__}: {e})")
    return fallback


def generate_override_explanation(context: dict) -> str:
    """
    Generate a short explanation for an admin: why the system made its decision,
    and what the human reviewer said (note + final decision). Used for conflicted (overturned) decisions.
    context: system_decision, human_decision, risk_score, triggered_signals, reasons, human_note, payout_summary (optional).
    Returns fallback text if LLM unavailable.
    """
    fallback = (
        f"The system decided to {context.get('system_decision', '?')} (risk score {context.get('risk_score', 0)}, "
        f"signals: {context.get('triggered_signals', [])}). "
        f"The human reviewer overturned to {context.get('human_decision', '?')}. "
        f"Reviewer note: {context.get('human_note') or '(none)'}."
    )
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return fallback

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    try:
        to = max(5, min(30, int(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))))
    except (TypeError, ValueError):
        to = 15
    import json as _json
    data_blob = _json.dumps(context, indent=2, default=str)
    prompt = (
        "You are a fraud risk analyst. A payout was first decided by an automated system, then a human reviewer "
        "overturned that decision. Given the following JSON, write two short paragraphs in plain text:\n"
        "1) Why the system did what it did: which signals and risk score led to the system's decision; refer to the reasons if present.\n"
        "2) What the human said: summarize the human's final decision and their note (if any).\n"
        "Be concise and factual. No bullet points. Output only the two paragraphs.\n\n"
        f"Data:\n{data_blob}"
    )
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=300,
            timeout=to,
        )
        content = (resp.choices[0].message.content or "").strip()
        if content:
            _llm_used("override explanation")
            return content
    except Exception as e:
        print(f"LLM not used for override explanation ({type(e).__name__}: {e})")
    return fallback


def suggest_weight_adjustment(context: dict, current_weights: dict) -> dict:
    """
    Suggest updated signal weights after a human override, so the system would align better with the human.
    context: system_decision, human_decision, risk_score, triggered_signals, reasons, human_note, payout_summary (optional).
    current_weights: e.g. {"no_trade_fraud": 40, "short_trade_abuse": 25, ...}.
    Returns a dict of suggested weights (same keys as current_weights); if LLM fails, returns current_weights unchanged.
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return dict(current_weights)

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    try:
        to = max(5, min(30, int(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))))
    except (TypeError, ValueError):
        to = 15
    import json as _json
    data = {**context, "current_signal_weights": current_weights}
    data_blob = _json.dumps(data, indent=2, default=str)
    prompt = (
        "You are a fraud risk analyst. The automated system used signal weights to compute a risk score and decided "
        "to approve or block. A human reviewer overturned that decision. To make the system align better with the human "
        "in similar cases, suggest new signal weights (integer values only).\n"
        "Rules: (1) Return ONLY a JSON object with the same keys as current_signal_weights and integer values. "
        "Example: {\"no_trade_fraud\": 38, \"short_trade_abuse\": 25, \"new_payment_method_risk\": 15, \"velocity_abuse\": 28, \"geo_vpn_anomaly\": 25}. "
        "(2) If the system blocked but human approved, consider reducing weights of signals that fired. "
        "(3) If the system approved but human blocked, consider increasing weights of signals that fired. "
        "(4) Keep changes small (e.g. ±5 points per signal). (5) No explanation, only the JSON object.\n\n"
        f"Data:\n{data_blob}"
    )
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=200,
            timeout=to,
        )
        content = (resp.choices[0].message.content or "").strip()
        if content:
            parsed = _parse_llm_json(content)
            if isinstance(parsed, dict) and parsed:
                # Ensure only integer values and only keys that exist in current_weights
                result = {}
                for k in current_weights:
                    if k in parsed and isinstance(parsed[k], (int, float)):
                        result[k] = max(0, min(100, int(parsed[k])))
                    else:
                        result[k] = current_weights[k]
                _llm_used("weight suggestion")
                return result
    except Exception as e:
        print(f"LLM not used for weight suggestion ({type(e).__name__}: {e})")
    return dict(current_weights)


def generate_fraud_network_summary(nodes: list, edges: list, link_types: list) -> str:
    """LLM: summarize a fraud network (connected accounts) in 2-3 sentences."""
    fallback = f"Network has {len(nodes)} accounts and {len(edges)} links (types: {link_types}). Review for potential fraud ring."
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return fallback
    import json as _json
    data = {"nodes_count": len(nodes), "edges_count": len(edges), "link_types": link_types, "sample_edges": edges[:15]}
    prompt = f"Given this fraud network data (accounts linked by shared payment method, IP, or device), write 2-3 short sentences summarizing what it likely represents and what an investigator should do. Plain text only.\n\n{_json.dumps(data)}"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=200,
            timeout=20,
        )
        content = (resp.choices[0].message.content or "").strip()
        if content:
            _llm_used("fraud network summary")
            return content
    except Exception:
        pass
    return fallback


def generate_exposure_explanation(total_amount: float, currency: str, user_count: int) -> str:
    """LLM: one-sentence explanation of exposure for a report."""
    fallback = f"Total exposure: {total_amount} {currency} across {user_count} user(s)."
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return fallback
    prompt = f"Write one short sentence explaining fraud exposure for a manager: {total_amount} {currency} across {user_count} accounts. Professional tone."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=80,
            timeout=15,
        )
        content = (resp.choices[0].message.content or "").strip()
        if content:
            _llm_used("exposure explanation")
            return content
    except Exception:
        pass
    return fallback


def generate_bulk_incident_message(reason: str, action: str, user_count: int) -> str:
    """LLM: draft a short client-facing message (e.g. account locked due to fraud)."""
    fallback = f"Your account has been restricted due to: {reason}. Contact support for assistance."
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return fallback
    prompt = f"Draft a short, professional client message (2-3 sentences) for users whose accounts were flagged. Reason: {reason}. Action: {action}. Number of accounts: {user_count}. Do not use bullet points."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=150,
            timeout=15,
        )
        content = (resp.choices[0].message.content or "").strip()
        if content:
            _llm_used("bulk incident message")
            return content
    except Exception:
        pass
    return fallback


# Allowed filter keys for natural language query (LLM must return only these)
_NL_QUERY_ALLOWED_KEYS = frozenset({
    "total_trades_max", "total_trades_min", "total_trade_volume_max", "total_trade_volume_min",
    "payment_method_age_max", "vpn_detected", "decision",
})


def _parse_nl_query_json(content: str) -> dict | None:
    """Parse LLM response as JSON for NL query: expect a dict with filter keys. Tolerates markdown and extra text."""
    if not content or not isinstance(content, str):
        return None
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*\n?", "", content)
    content = re.sub(r"\n?\s*```\s*$", "", content)
    content = content.strip()
    start = content.find("{")
    if start == -1:
        return None
    end = content.rfind("}")
    if end == -1 or end < start:
        return None
    try:
        data = json.loads(content[start : end + 1])
        if not isinstance(data, dict):
            return None
        # Keep only allowed keys with valid types
        out = {}
        for k, v in data.items():
            if k not in _NL_QUERY_ALLOWED_KEYS:
                continue
            if k == "decision" and v is not None:
                out[k] = str(v).strip().lower()
            elif k == "vpn_detected" and v is not None:
                out[k] = bool(v)
            elif k in ("total_trades_max", "total_trades_min", "payment_method_age_max") and v is not None:
                try:
                    out[k] = int(v)
                except (TypeError, ValueError):
                    pass
            elif k in ("total_trade_volume_max", "total_trade_volume_min") and v is not None:
                try:
                    out[k] = float(v)
                except (TypeError, ValueError):
                    pass
        return out if out else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def interpret_natural_language_query(question: str, schema_description: str) -> dict | None:
    """
    LLM: turn natural language into structured filters for querying.
    Returns e.g. {"total_trades_max": 2, "total_trade_volume_max": 100} or None.
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None
    prompt = (
        f"Schema: {schema_description}\n\n"
        "User question: " + question + "\n\n"
        "Return ONLY a JSON object with filter keys and values. Use these keys only: total_trades_max (int), total_trades_min (int), "
        "total_trade_volume_max (float), total_trade_volume_min (float), payment_method_age_max (int), vpn_detected (bool), "
        "decision (approve|review|block). Omit keys you cannot infer. "
        "E.g. 'traded less and withdrew a lot' -> low total_trades_max and high total_trade_volume_min (withdrawal volume). "
        "Example: {\"total_trades_max\": 5, \"total_trade_volume_min\": 500}. No explanation."
    )
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=150,
            timeout=20,
        )
        content = (resp.choices[0].message.content or "").strip()
        if content:
            parsed = _parse_nl_query_json(content)
            if parsed is not None:
                _llm_used("natural language query")
                return parsed
    except Exception:
        pass
    return None


def explain_simulator_rating(
    pattern: str,
    risk_score: int,
    decision: str,
    triggered_signals: list,
    reasons: list,
) -> str:
    """LLM: explain why this scenario was rated this risk score and decision (for Decision Simulator)."""
    print(f"[simulate-llm] explain_simulator_rating called for pattern={pattern!r} score={risk_score}")
    signals_str = ", ".join(triggered_signals) if triggered_signals else "none"
    reasons_str = " | ".join(reasons[:5]) if reasons else "N/A"
    fallback = (
        f"This scenario ({pattern}) received risk score {risk_score} and decision '{decision}' "
        f"because it triggered: {signals_str}. {reasons_str}"
    )
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        print("[simulate-llm] No OPENAI_API_KEY, using fallback")
        return fallback
    prompt = (
        f"In a fraud decision simulator, a scenario named '{pattern}' was evaluated. "
        f"Result: risk score {risk_score} (0-100), decision '{decision}'. "
        f"Triggered signals: {signals_str}. "
        f"System reasons: {reasons_str}. "
        "Write 1-2 short sentences in plain English explaining why it was rated this way (what about the scenario led to this score and decision). No bullets."
    )
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=150,
            timeout=15,
        )
        content = (resp.choices[0].message.content or "").strip()
        if content:
            _llm_used("simulator rating explanation")
            print(f"[simulate-llm] Got LLM response ({len(content)} chars)")
            return content
        print("[simulate-llm] LLM returned empty content")
    except Exception as e:
        print(f"[simulate-llm] LLM exception: {type(e).__name__}: {e}")
    return fallback


def describe_emerging_pattern(signal_combo: str, case_count: int) -> str:
    """LLM: name and describe an emerging fraud pattern (signal combo)."""
    fallback = f"Pattern: {signal_combo} ({case_count} cases). Consider reviewing similar cases."
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return fallback
    prompt = f"Fraud pattern: signals {signal_combo}, observed in {case_count} cases. Write one short sentence describing what this pattern likely means and one recommended action. Plain text only."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=120,
            timeout=15,
        )
        content = (resp.choices[0].message.content or "").strip()
        if content:
            _llm_used("emerging pattern description")
            return content
    except Exception:
        pass
    return fallback
