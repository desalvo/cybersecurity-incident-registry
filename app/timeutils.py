from datetime import datetime, timezone


def utcnow():
    """Return a UTC timestamp stored as naive datetime for legacy DB columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
