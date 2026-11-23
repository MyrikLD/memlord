from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased

from memlord.models import Memory, MemoryTag, Tag
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


def canonical_tag_id(tag=Tag):
    """Id of the tag's group head: its parent when it is an alias, else itself."""
    return func.coalesce(tag.parent_id, tag.id)


def tag_group_select(model=Memory):
    """Base query over the tags of `model`, widened to their whole alias groups.

    Returns `(select, requested)` where `requested` is a `Tag` alias ranging
    over every tag in the same group as one attached to the memory. Filter
    `requested` by name to match a memory through any spelling of a tag; the
    query is correlated on `model.id` for use as EXISTS or a scalar subquery.
    """
    attached = aliased(Tag)
    requested = aliased(Tag)
    q = (
        select(MemoryTag.memory_id)
        .select_from(MemoryTag)
        .join(attached, attached.id == MemoryTag.tag_id)
        .join(
            requested,
            and_(
                requested.workspace_id == attached.workspace_id,
                canonical_tag_id(requested) == canonical_tag_id(attached),
            ),
        )
        .where(MemoryTag.memory_id == model.id)
    )
    return q, requested


def has_tag(condition, model=Memory):
    """EXISTS condition: `model` carries a tag whose group has a tag matching
    `condition(requested_tag)`."""
    q, requested = tag_group_select(model)
    return q.where(condition(requested)).exists()
