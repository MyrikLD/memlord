from datetime import datetime, UTC


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)
