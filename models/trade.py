from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TradeIntent(BaseModel):
    """A proposed trade before risk checks and execution."""

    symbol: str
    side: TradeSide
    quantity: int = Field(ge=1)
    stop_loss_pct: float = Field(default=0.03, description="Stop loss as decimal (0.03 = 3%)")
    take_profit_pct: float = Field(default=0.05, description="Take profit as decimal (0.05 = 5%)")
    post_id: str
    reasoning: str


class TradeRecord(BaseModel):
    """A completed trade logged for audit."""

    id: str | None = None
    post_id: str
    symbol: str
    side: str
    quantity: int
    order_id: str
    status: str
    executed_at: datetime
    entry_price: float | None = None
    analysis_confidence: float
    analysis_sentiment: float
