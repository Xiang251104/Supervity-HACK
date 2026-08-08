"""The AI Manager chat endpoint.

The path is fixed by two things that already exist: the frontend posts to
`/api/ai/chat`, and `app/authz.map.json` already grants that path to `admin`
and `user`. Both are left alone.

Everything this returns is composed from stored records — see
`app/services/ai_manager.py` for why there is no model behind it.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..schemas.ai_manager import ChatRequest, ChatResponse, ToolCallOut
from ..security import get_current_user
from ..services.ai_manager import answer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Manager"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    _current_user: dict | None = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Answer a question about the agent's own output.

    A failed lookup returns an honest sentence rather than a 500, because a
    chat panel that errors mid-demo reads worse than one that says it does not
    know — and the caller has no useful recovery for a 500 either way.
    """
    try:
        result = answer(
            db,
            body.message,
            history=body.history,
            page=body.context.page if body.context else None,
        )
    except Exception:  # pragma: no cover - defensive, the handlers are pure reads
        logger.exception("AI Manager could not answer a question")
        return ChatResponse(
            response=(
                "I could not reach the records needed to answer that. "
                "Nothing has changed, and the decision history is unaffected."
            ),
            tool_calls=[],
        )

    return ChatResponse(
        response=result.response,
        tool_calls=[ToolCallOut(**call) for call in result.tool_calls],
    )
