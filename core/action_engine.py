"""Daily action engine. Reads scores + technicals from DB, persists SELL/ADD/WATCH signals."""
from __future__ import annotations

from dataclasses import dataclass

from core.technical_engine import trend_improving
from db.repositories import prices_repo, scores_repo, signals_repo
from utils.logging import get_logger
from utils.time import today_iso

log = get_logger(__name__)


@dataclass(frozen=True)
class Action:
    symbol: str
    action: str  # SELL | ADD | WATCH
    score: float
    trend_label: str
    reason: str

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "score": self.score,
            "trend_label": self.trend_label,
            "reason": self.reason,
        }


def generate(symbols: list[str]) -> list[Action]:
    date = today_iso()
    signals_repo.clear_signals_for_date(date)

    actions: list[Action] = []
    for sym in symbols:
        score_row = scores_repo.get_score(sym)
        ind = prices_repo.latest_indicators(sym)
        if not score_row or not ind:
            continue
        score = score_row["score"]
        trend = ind.get("trend_label") or "weak"
        action: Action | None = None

        if score < 4 and trend in ("weak", "down"):
            action = Action(sym, "SELL", score, trend, f"score {score:.1f} + trend {trend}")
        elif score >= 7 and trend in ("strong_up", "up"):
            action = Action(sym, "ADD", score, trend, f"score {score:.1f} + trend {trend}")
        elif 5 <= score < 7:
            df = prices_repo.load_prices(sym).reset_index().rename(columns={"index": "date"})
            if trend_improving(df):
                action = Action(sym, "WATCH", score, trend, f"score {score:.1f}, ema21 crossing ema50")

        if action is not None:
            signals_repo.insert_signal(date, sym, action.action, action.reason, score, trend)
            actions.append(action)

    log.info("Generated %d daily actions", len(actions))
    return actions
