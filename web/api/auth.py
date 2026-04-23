"""Authentication endpoints: exchange handshake, logout, session status."""

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
    return {"ok": True, "csrf_token": csrf_token}


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    store = request.app.state.session_store
    session_id = request.cookies.get("tally_session", "")
    if session_id:
        store.revoke(session_id)
    response.delete_cookie("tally_session", path="/")
    response.delete_cookie("tally_csrf", path="/")


@router.get("/me")
async def me(request: Request) -> dict[str, object]:
    store = request.app.state.session_store
    session_id = request.cookies.get("tally_session", "")
    if not session_id or not store.verify(session_id):
        raise Unauthenticated("Not authenticated")
    return {"authenticated": True, "session_id": session_id}
