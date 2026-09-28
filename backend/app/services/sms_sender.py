import logging
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class SmsSender(Protocol):
    """Anything with this send() method can deliver SMS. A real provider
    (Twilio, MSG91, ...) only needs a class like LoggingSmsSender and an
    entry in get_sms_sender()."""

    def send(self, phone_number: str, text: str) -> None: ...


class LoggingSmsSender:
    """Development stand-in: writes the SMS to the log instead of sending it."""

    def send(self, phone_number: str, text: str) -> None:
        # Only the last 4 digits are logged; phone numbers are personal data.
        logger.info("SMS sent", extra={"to": f"******{phone_number[-4:]}", "sms_text": text})


def get_sms_sender() -> SmsSender:
    """Pick the SMS implementation from settings."""
    provider = get_settings().sms_provider
    if provider == "log":
        return LoggingSmsSender()
    raise ValueError(f"Unknown SMS provider: {provider}")
