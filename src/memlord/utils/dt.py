from datetime import UTC, datetime


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)
