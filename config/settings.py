from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # API keys
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    anthropic_api_key: str = ""

    # Risk parameters
    max_position_pct: float = 0.05
    max_open_positions: int = 5
    daily_loss_limit_pct: float = 0.05
    trade_cooldown_seconds: int = 300
    confidence_threshold: float = 0.7

    # Long/short stop-loss and take-profit
    long_stop_loss_pct: float = 0.03
    long_take_profit_pct: float = 0.05
    short_stop_loss_pct: float = 0.02
    short_take_profit_pct: float = 0.04

    # Safety limits
    buying_power_multiplier: float = 2.0
    max_short_exposure_pct: float = 0.15
    max_single_short_pct: float = 0.03
    min_equity_floor: float = 1000.0

    # Polling
    poll_interval_seconds: int = 30

    # Trading
    use_extended_hours: bool = False
    paper_trading: bool = True


settings = Settings()
