import re

PHONE_NUMBER_PATTERN = re.compile(r"^\+?[0-9]{10,15}$")


def validate_phone_number(phone_number: str | None) -> str | None:
    """Allow an optional leading + and 10 to 15 digits, e.g. +919876543210."""
    if phone_number is None:
        return None
    cleaned = phone_number.replace(" ", "").replace("-", "")
    if not PHONE_NUMBER_PATTERN.match(cleaned):
        raise ValueError("must be 10 to 15 digits, optionally starting with +")
    return cleaned
