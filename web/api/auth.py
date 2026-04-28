"""Authentication endpoint: exchange one-time handshake for session cookies."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from web.api._errors import Unauthenticated

router = APIRouter()


class ExchangeBody(BaseModel):
    token: str


@router.post("/exchange")
async def exchange(
    body: ExchangeBody, request: Request, response: Response
) -> dict[str, object]:
    registry = request.app.state.handshake_registry
    store = request.app.state.session_store
    if not registry.consume(body.token):
        raise Unauthenticated("Invalid or expired token")
    session_id, csrf_token = store.create()
    response.set_cookie(
        "tally_session",
        session_id,
        httponly=True,
        samesite="strict",
        secure=True,
        path="/",
    )
    response.set_cookie(
        "tally_csrf",
        csrf_token,
        httponly=False,
        samesite="strict",
        secure=True,
        path="/",
    )
    return {"ok": True}
