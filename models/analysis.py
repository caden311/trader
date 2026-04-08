from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    """Structured output from Claude's analysis of a post."""

    is_relevant: bool = Field(
        description="Whether the post is relevant to financial markets or the economy"
    )
    reasoning: str = Field(
        description="Brief explanation of the analysis"
    )
    sentiment: float = Field(
        ge=-1.0,
        le=1.0,
        description="Market sentiment from -1.0 (very bearish) to 1.0 (very bullish)",
    )
    affected_sectors: list[str] = Field(
        default_factory=list,
        description="Sectors likely affected (e.g. technology, finance, energy)",
    )
    affected_tickers: list[str] = Field(
        default_factory=list,
        description="Specific ETF tickers to trade (e.g. SPY, XLF, XLE)",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the analysis from 0.0 to 1.0",
    )
    direction: str = Field(
        description="Suggested trade direction: buy, sell, or hold",
        pattern="^(buy|sell|hold)$",
    )
    urgency: str = Field(
        description="How quickly the market might react: immediate, moderate, or low",
        pattern="^(immediate|moderate|low)$",
    )
