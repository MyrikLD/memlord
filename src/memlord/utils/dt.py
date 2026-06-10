from datetime import UTC, datetime


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def as_naive_utc(dt: datetime | None) -> datetime | None:
    """Normalize a datetime to naive UTC, matching how timestamps are stored.

    Aware datetimes (e.g. an ISO string with offset from a client) are converted
    to UTC and stripped of tzinfo; naive datetimes are assumed to already be UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt
