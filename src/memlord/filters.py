from sqlalchemy import or_

from memlord.models import Memory
from memlord.utils.dt import utcnow


def not_expired():
    """SQL condition matching memories that have not expired.

    A memory is active when it has no expiry (`expires_at IS NULL`) or its
    expiry is still in the future. Compared against naive-UTC `utcnow()` to
    match the `expires_at` column type.
    """
    return or_(Memory.expires_at.is_(None), Memory.expires_at > utcnow())
