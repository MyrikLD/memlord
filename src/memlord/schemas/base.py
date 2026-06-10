from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    """Base for all schemas: immutable (frozen) by default.

    Freezing prevents accidental post-construction mutation of validated DTOs
    (which silently bypasses validation in Pydantic). Subclasses may add their
    own `model_config` — it is merged with this one, so `frozen` is retained.
    """

    model_config = ConfigDict(frozen=True)
