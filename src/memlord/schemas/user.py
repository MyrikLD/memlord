from pydantic import BaseModel


class UserInfo(BaseModel):
    id: int
    display_name: str
