from app.config import config


def pytest_configure() -> None:
    object.__setattr__(config.gemini, "order_extraction_enabled", False)
