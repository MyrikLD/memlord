from pydantic import BaseModel


class DeleteResult(BaseModel):
    success: bool
    name: str
