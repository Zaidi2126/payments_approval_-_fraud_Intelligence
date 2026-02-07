"""
OpenAI client for generating reasons and counterfactuals. Falls back to deterministic text if key missing or call fails.
"""

import json
import os
import re
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv

load_dotenv()

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
    """Parse LLM response as JSON; expect keys reasons and counterfactuals."""
    content = content.strip()
    # Remove markdown code block if present
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        data = json.loads(content)
        if isinstance(data.get("reasons"), list) and isinstance(data.get("counterfactuals"), list):
            return {
                "reasons": [str(x) for x in data["reasons"]],
                "counterfactuals": [str(x) for x in data["counterfactuals"]],
            }
    except (json.JSONDecodeError, TypeError):
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
        return _fallback_explanations(payload)

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    timeout = max(5, min(60, int(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))))
    max_tokens = max(100, min(1000, int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "500"))))

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
            max_tokens=max_tokens,
            timeout=timeout,
        )
        content = (resp.choices[0].message.content or "").strip()
        parsed = _parse_llm_json(content)
        if parsed:
            return parsed
    except Exception:
        pass
    return _fallback_explanations(payload)
