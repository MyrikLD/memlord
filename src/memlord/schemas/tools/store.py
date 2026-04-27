from pydantic import BaseModel


class StoreResult(BaseModel):
    name: str
    created: bool
