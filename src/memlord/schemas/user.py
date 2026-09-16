from .base import Schema


class UserInfo(Schema):
    id: int
    display_name: str
    email: str = ""
    email_verified: bool = False
    totp_enabled: bool = False
