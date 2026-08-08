"""Request and response shapes for the grounded AI Manager chat.

The response shape is fixed by the frontend that already calls this endpoint
(`frontend/src/components/ai/AIManager.tsx`): it reads `response` and an
optional `tool_calls`. Renaming either breaks the chat silently, so both stay
as they are.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatTurn(BaseModel):
    """One earlier message, replayed by the frontend on every request."""

    model_config = ConfigDict(extra="ignore")

    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=8000)


class ChatContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page: str | None = Field(default=None, max_length=300)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=50)
    context: ChatContext | None = None


class ToolCallOut(BaseModel):
    """One lookup that actually ran, so the UI's "used N tools" is truthful."""

    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: Any | None = None


class ChatResponse(BaseModel):
    response: str
    tool_calls: list[ToolCallOut] = Field(default_factory=list)
