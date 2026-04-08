SECTOR_ETF_MAP: dict[str, str] = {
    "broad_market": "SPY",
    "technology": "XLK",
    "finance": "XLF",
    "energy": "XLE",
    "healthcare": "XLV",
    "industrials": "XLI",
    "emerging_markets": "EEM",
    "china": "FXI",
    "bonds": "TLT",
    "gold": "GLD",
    "defense": "ITA",
    "crypto": "BITO",
    "real_estate": "XLRE",
    "consumer_staples": "XLP",
    "consumer_discretionary": "XLY",
    "utilities": "XLU",
    "materials": "XLB",
    "semiconductors": "SMH",
    "transportation": "IYT",
}


def sectors_to_tickers(sectors: list[str]) -> list[str]:
    """Map sector names to ETF tickers. Unknown sectors default to SPY."""
    tickers = []
    for sector in sectors:
        key = sector.lower().replace(" ", "_")
        ticker = SECTOR_ETF_MAP.get(key)
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    if not tickers:
        tickers.append("SPY")
    return tickers
