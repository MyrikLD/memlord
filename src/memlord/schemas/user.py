from pydantic import BaseModel


class UserInfo(BaseModel):
    id: int
    display_name: str
    email: str = ""
    email_verified: bool = False
