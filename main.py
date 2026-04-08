import structlog

from config.settings import settings

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)

logger = structlog.get_logger()


def main() -> None:
    # Validate required API keys
    missing = []
    if not settings.alpaca_api_key:
        missing.append("ALPACA_API_KEY")
    if not settings.alpaca_secret_key:
        missing.append("ALPACA_SECRET_KEY")
    if not settings.anthropic_api_key:
        missing.append("ANTHROPIC_API_KEY")

    if missing:
        logger.error("missing_api_keys", keys=missing)
        print(f"\nMissing required API keys: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your keys.")
        return

    logger.info(
        "starting_trump_trader",
        paper_trading=settings.paper_trading,
        poll_interval=settings.poll_interval_seconds,
    )

    from core.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    orchestrator.run()


if __name__ == "__main__":
    main()
