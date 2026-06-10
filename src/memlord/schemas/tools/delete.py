from ..base import Schema


class DeleteResult(Schema):
    success: bool
    name: str
