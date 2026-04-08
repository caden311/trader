from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Post(BaseModel):
    """A Truth Social post from Trump's account."""

    id: str
    text: str
    created_at: datetime
    url: str | None = None
    has_media: bool = False
