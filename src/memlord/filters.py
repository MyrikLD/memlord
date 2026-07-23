from sqlalchemy import or_

from memlord.models import Memory
from memlord.utils.dt import utcnow


def not_expired(model=Memory):
    """SQL condition matching memories that have not expired.

    A memory is active when it has no expiry (`expires_at IS NULL`) or its
    expiry is still in the future. Compared against naive-UTC `utcnow()` to
    match the `expires_at` column type.

    Pass an `aliased(Memory)` as `model` to apply the condition to that alias
    in self-join queries.
    """
    return or_(model.expires_at.is_(None), model.expires_at > utcnow())
