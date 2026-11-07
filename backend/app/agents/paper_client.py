"""Alpaca paper-trading client (paper URL only — never live)."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

from app.agents import PAPER_URL_REQUIRED

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_PATH, override=True)


class PaperTradingError(Exception):
    """Raised when paper trading cannot proceed."""


@dataclass(frozen=True)
class PaperAccount:
    buying_power: Decimal
    equity: Decimal
    cash: Decimal


@dataclass(frozen=True)
class PaperOrder:
    id: str
    client_order_id: str
    symbol: str
    status: str
    filled_avg_price: Optional[Decimal] = None
    filled_qty: Optional[Decimal] = None
    side: str = "buy"
    order_type: str = "limit"


class PaperBroker(ABC):
    """Interface for paper brokerage operations."""

    @abstractmethod
    def get_account(self) -> PaperAccount:
        ...

    @abstractmethod
    def list_open_positions(self) -> list[str]:
        """Return uppercase symbols with open positions."""

    @abstractmethod
    def get_order_by_client_id(self, client_order_id: str) -> Optional[PaperOrder]:
        ...

    @abstractmethod
    def submit_bracket_order(
        self,
        *,
        symbol: str,
        qty: int,
        entry: Decimal,
        stop: Decimal,
        target: Decimal,
        client_order_id: str,
    ) -> PaperOrder:
        ...

    @abstractmethod
    def get_order(self, order_id: str) -> PaperOrder:
        ...


class AlpacaPaperClient(PaperBroker):
    """REST client constrained to the Alpaca paper host."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        paper_url: Optional[str] = None,
    ) -> None:
        self._key = (api_key or os.getenv("ALPACA_API_KEY") or "").strip()
        self._secret = (api_secret or os.getenv("ALPACA_API_SECRET") or "").strip()
        url = (paper_url or os.getenv("ALPACA_PAPER_URL") or "").strip().rstrip("/")
        if url != PAPER_URL_REQUIRED:
            raise PaperTradingError(
                f"ALPACA_PAPER_URL must be exactly {PAPER_URL_REQUIRED} "
                "(paper trading only; live trading is not implemented)."
            )
        self._base = url
        if not self._key or not self._secret:
            raise PaperTradingError("Alpaca paper API key/secret are not set")

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._key,
            "APCA-API-SECRET-KEY": self._secret,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base}{path}"
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.request(
                    method, url, headers=self._headers(), **kwargs
                )
        except httpx.RequestError as exc:
            raise PaperTradingError("Network error talking to Alpaca paper API") from exc
        if response.status_code >= 400:
            # Never include raw secrets; response text is ok at high level.
            raise PaperTradingError(
                f"Alpaca paper API error ({response.status_code})"
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get_account(self) -> PaperAccount:
        data = self._request("GET", "/v2/account")
        return PaperAccount(
            buying_power=Decimal(str(data.get("buying_power", "0"))),
            equity=Decimal(str(data.get("equity", "0"))),
            cash=Decimal(str(data.get("cash", "0"))),
        )

    def list_open_positions(self) -> list[str]:
        data = self._request("GET", "/v2/positions") or []
        return [str(row.get("symbol", "")).upper() for row in data if row.get("symbol")]

    def get_order_by_client_id(self, client_order_id: str) -> Optional[PaperOrder]:
        try:
            data = self._request(
                "GET",
                "/v2/orders:by_client_order_id",
                params={"client_order_id": client_order_id},
            )
        except PaperTradingError:
            return None
        if not data:
            return None
        return self._parse_order(data)

    def submit_bracket_order(
        self,
        *,
        symbol: str,
        qty: int,
        entry: Decimal,
        stop: Decimal,
        target: Decimal,
        client_order_id: str,
    ) -> PaperOrder:
        existing = self.get_order_by_client_id(client_order_id)
        if existing is not None:
            return existing
        body = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": "buy",
            "type": "limit",
            "time_in_force": "day",
            "limit_price": format(entry, "f"),
            "order_class": "bracket",
            "client_order_id": client_order_id,
            "take_profit": {"limit_price": format(target, "f")},
            "stop_loss": {"stop_price": format(stop, "f")},
        }
        data = self._request("POST", "/v2/orders", json=body)
        return self._parse_order(data)

    def get_order(self, order_id: str) -> PaperOrder:
        data = self._request("GET", f"/v2/orders/{order_id}")
        return self._parse_order(data)

    @staticmethod
    def _parse_order(data: dict[str, Any]) -> PaperOrder:
        filled = data.get("filled_avg_price")
        qty = data.get("filled_qty")
        return PaperOrder(
            id=str(data.get("id")),
            client_order_id=str(data.get("client_order_id") or ""),
            symbol=str(data.get("symbol", "")).upper(),
            status=str(data.get("status", "")),
            filled_avg_price=Decimal(str(filled)) if filled not in (None, "") else None,
            filled_qty=Decimal(str(qty)) if qty not in (None, "") else None,
            side=str(data.get("side", "buy")),
            order_type=str(data.get("type", "limit")),
        )


class FakePaperClient(PaperBroker):
    """In-memory paper broker for tests (no network)."""

    def __init__(
        self,
        *,
        buying_power: Decimal = Decimal("100000"),
        equity: Decimal = Decimal("100000"),
        open_positions: Optional[list[str]] = None,
        paper_url: str = PAPER_URL_REQUIRED,
    ) -> None:
        if paper_url != PAPER_URL_REQUIRED:
            raise PaperTradingError(
                f"ALPACA_PAPER_URL must be exactly {PAPER_URL_REQUIRED}"
            )
        self.buying_power = buying_power
        self.equity = equity
        self.open_positions = [s.upper() for s in (open_positions or [])]
        self.orders_by_client: dict[str, PaperOrder] = {}
        self.orders_by_id: dict[str, PaperOrder] = {}
        self.submit_count = 0

    def get_account(self) -> PaperAccount:
        return PaperAccount(
            buying_power=self.buying_power,
            equity=self.equity,
            cash=self.buying_power,
        )

    def list_open_positions(self) -> list[str]:
        return list(self.open_positions)

    def get_order_by_client_id(self, client_order_id: str) -> Optional[PaperOrder]:
        return self.orders_by_client.get(client_order_id)

    def submit_bracket_order(
        self,
        *,
        symbol: str,
        qty: int,
        entry: Decimal,
        stop: Decimal,
        target: Decimal,
        client_order_id: str,
    ) -> PaperOrder:
        existing = self.get_order_by_client_id(client_order_id)
        if existing is not None:
            return existing
        self.submit_count += 1
        order = PaperOrder(
            id=f"ord-{self.submit_count}",
            client_order_id=client_order_id,
            symbol=symbol.upper(),
            status="accepted",
            filled_avg_price=None,
            filled_qty=None,
        )
        self.orders_by_client[client_order_id] = order
        self.orders_by_id[order.id] = order
        return order

    def get_order(self, order_id: str) -> PaperOrder:
        order = self.orders_by_id.get(order_id)
        if order is None:
            raise PaperTradingError(f"Order {order_id} not found")
        return order

    def fill_order(
        self,
        client_order_id: str,
        price: Decimal,
        qty: int,
        status: str = "filled",
    ) -> PaperOrder:
        order = self.orders_by_client[client_order_id]
        filled = PaperOrder(
            id=order.id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            status=status,
            filled_avg_price=price,
            filled_qty=Decimal(qty),
        )
        self.orders_by_client[client_order_id] = filled
        self.orders_by_id[filled.id] = filled
        if filled.symbol not in self.open_positions:
            self.open_positions.append(filled.symbol)
        return filled
