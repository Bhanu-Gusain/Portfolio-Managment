"""Local LLM (Ollama) wrapper. Narrative explanations only — never decides trades.

If Ollama is not running, callers receive a friendly `OllamaError` which the
UI renders as "AI insights unavailable" rather than a crash. This keeps the
app plug-and-play for users who don't install Ollama.
"""
from __future__ import annotations

import json

import requests

from utils.config import get_settings
from utils.logging import get_logger

log = get_logger(__name__)


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self):
        s = get_settings()
        self.base = s.ollama_base_url.rstrip("/")
        self.model = s.ollama_model
        self.timeout = s.ollama_timeout_seconds

    def generate(self, prompt: str, system: str | None = None) -> str:
        url = f"{self.base}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if system:
            payload["system"] = system
        try:
            r = requests.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise OllamaError(
                f"Cannot reach Ollama at {self.base}. Install Ollama and run `ollama serve` "
                f"to enable AI insights. Details: {exc}"
            ) from exc
        if r.status_code != 200:
            raise OllamaError(f"Ollama returned {r.status_code}: {r.text[:200]}")
        data = r.json()
        return (data.get("response") or "").strip()


def is_available() -> bool:
    """Quick health check. UI uses this to show/hide the AI tab."""
    s = get_settings()
    try:
        r = requests.get(f"{s.ollama_base_url.rstrip('/')}/api/tags", timeout=2)
        return r.status_code == 200
    except requests.RequestException:
        return False


SYSTEM_PROMPT = (
    "You are an investment analyst assistant for an Indian retail investor. "
    "You explain quant signals in plain English. You NEVER decide trades. "
    "Be concise, factual, and reference the structured data provided. No disclaimers."
)


def analyze_portfolio(snapshot_payload: dict) -> str:
    client = OllamaClient()
    prompt = (
        "Summarise the health of this portfolio in 3 short paragraphs: "
        "(1) overall positioning, (2) top concerns, (3) what to watch. "
        "Use only the JSON below — do not invent numbers.\n\n"
        f"```json\n{json.dumps(snapshot_payload, indent=2, default=str)}\n```"
    )
    return client.generate(prompt, system=SYSTEM_PROMPT)


def explain_stock(symbol: str, score: float, breakdown: dict, technicals: dict) -> str:
    client = OllamaClient()
    prompt = (
        f"Explain in 4–6 sentences why {symbol} received a score of {score}/10 from our quant engine. "
        "Reference the factor breakdown and the latest technical snapshot. "
        "Do not recommend a trade — only explain the score.\n\n"
        f"FACTOR BREAKDOWN:\n```json\n{json.dumps(breakdown, indent=2)}\n```\n\n"
        f"TECHNICALS:\n```json\n{json.dumps(technicals, indent=2, default=str)}\n```"
    )
    return client.generate(prompt, system=SYSTEM_PROMPT)


def suggest_rebalance(positions: list[dict], rebalance_actions: list[dict]) -> str:
    client = OllamaClient()
    prompt = (
        "Narrate the proposed rebalance plan in 3 paragraphs: "
        "(1) what is being trimmed/exited and why, (2) where capital is being redeployed, "
        "(3) the resulting risk profile. Use only the JSON below.\n\n"
        f"POSITIONS:\n```json\n{json.dumps(positions, indent=2, default=str)}\n```\n\n"
        f"PROPOSED ACTIONS:\n```json\n{json.dumps(rebalance_actions, indent=2, default=str)}\n```"
    )
    return client.generate(prompt, system=SYSTEM_PROMPT)
