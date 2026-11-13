from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials

from app.database.connection import settings
from app.dependencies import bearer, get_current_user
from app.models.user import User
from app.schemas.chat import ChatAnswer, ChatRequest
from app.services.gemini_chat import answer

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.get("/status", dependencies=[Depends(get_current_user)])
def chat_status():
    return {"configured": bool(settings.gemini_api_key.get_secret_value().strip())}


@router.post("/ask", response_model=ChatAnswer, response_model_exclude_none=True)
async def ask_question(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
):
    return await answer(request, user.id, credentials.credentials)
