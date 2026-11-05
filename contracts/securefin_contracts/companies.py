"""Companies and users. Written by services/api."""
from datetime import datetime

from pydantic import Field

from .common import Contract, Language, Role


class Company(Contract):
    id: int
    name: str = Field(min_length=1, max_length=200)
    tax_id: str | None = Field(default=None, max_length=20)
    default_language: Language = Language.AR
    created_at: datetime


class User(Contract):
    id: int
    company_id: int
    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    full_name: str = Field(min_length=1, max_length=120)
    role: Role
    language: Language = Language.AR
    is_active: bool = True
    created_at: datetime
