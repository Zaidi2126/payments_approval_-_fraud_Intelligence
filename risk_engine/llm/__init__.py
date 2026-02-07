"""
LLM client for generating reasons and counterfactuals. Fallback to deterministic text if API key missing or call fails.
"""

from .client import generate_explanations

__all__ = ["generate_explanations"]
