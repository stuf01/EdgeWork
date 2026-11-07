"""Six-agent paper-trading pipeline (NOVA → ORIN → VESK → LUMA; KIRA; DASH)."""

from __future__ import annotations

PAPER_URL_REQUIRED = "https://paper-api.alpaca.markets"

AGENT_JOBS = {
    "NOVA": "Scanner — find watchlist candidates that pass required checklist rules",
    "ORIN": "Forecaster — score setups and estimate expected move (no ML)",
    "VESK": "Risk — size and veto; vetoes are final",
    "LUMA": "Decider — propose, watch, or skip (never overrides a veto)",
    "KIRA": "Executor — place paper bracket orders only after human approval",
    "DASH": "Reviewer — grade process/outcome and suggest experiments",
}
