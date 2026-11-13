from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StringConstraints

from app.dependencies import get_current_user

router = APIRouter(prefix="/chat", tags=["Chat"], dependencies=[Depends(get_current_user)])


class ChatRequest(BaseModel):
    question: Annotated[
        str, StringConstraints(min_length=1, max_length=4000, strip_whitespace=True)
    ]


@router.post("/ask", status_code=503)
def ask_question(request: ChatRequest):
    # The data/agent pipeline is not implemented yet. Never return demo statistics
    # as if they were an answer obtained from real open data.
    raise HTTPException(
        status_code=503,
        detail="Datové zdroje pro odpovědi se teprve připravují. Zkuste to prosím později.",
    )
