"""/sandbox/chat: ask a question; an LLM answers with the metadata-advisor skill and MCP tools."""

from functools import cache
from typing import Annotated

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import settings

from . import llm, rate_limit
from .schemas import SuggestRequest, SuggestResponse

router = APIRouter(prefix="/sandbox/chat", tags=["sandbox: chat"])


@cache
def _client(api_key: str) -> anthropic.AsyncAnthropic:
    """One Anthropic client per key, reused across requests."""
    return anthropic.AsyncAnthropic(api_key=api_key)


def get_chat_client() -> llm.ChatClient | None:
    """The Anthropic client, or None when no key is configured."""
    return _client(settings.ANTHROPIC_API_KEY) if settings.ANTHROPIC_API_KEY else None


# None instead of raising here: the 503 comes after FastAPI has validated the body.
ChatClientDep = Annotated[llm.ChatClient | None, Depends(get_chat_client)]


@router.post(
    "/suggest",
    responses={
        429: {"description": "Too many questions from this client; see Retry-After"},
        502: {"description": "The model provider failed or the assistant didn't finish"},
        503: {"description": "No ANTHROPIC_API_KEY is configured"},
    },
)
async def suggest(
    payload: SuggestRequest, client: ChatClientDep, request: Request
) -> SuggestResponse:
    """Answer one staff question, guided by the metadata-advisor skill and the definitions."""
    if client is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Sandbox chat needs ANTHROPIC_API_KEY. Set it in .env.development.local.",
        )
    # Checked after the key and the body, so a refused question is a real question.
    wait = rate_limit.limiter.check(rate_limit.client_key(request))
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many questions. Try again in {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )
    try:
        return await llm.answer(
            client,
            settings.SANDBOX_CHAT_MODEL,
            payload.prompt,
            turns=payload.turns,
            keyword=payload.context,
            page=payload.page,
        )
    except anthropic.AnthropicError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"The model provider failed: {type(exc).__name__}."
        ) from None
    except llm.ChatFailed as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
