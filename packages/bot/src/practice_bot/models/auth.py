"""Models for bot access control."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AuthStatus = Literal["pending", "approved", "rejected"]


class PendingUser(BaseModel):
    """Someone waiting for the admin to approve their access."""

    model_config = ConfigDict(frozen=True)

    telegram_id: int = Field(description="Telegram user ID")
    full_name: str = Field(description="Name reported by Telegram")
    telegram_username: str | None = Field(
        default=None, description="Telegram @username, when the user has one"
    )
    created_at: str | None = Field(
        default=None, description="When the request was recorded"
    )

    @property
    def label(self) -> str:
        """Return a display label combining the name and @username."""
        if self.telegram_username:
            return f"{self.full_name} (@{self.telegram_username})"
        return self.full_name
