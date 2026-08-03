"""Document upload and management endpoints."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, File, Request, UploadFile

from application.rag.knowledge_base_cache import (
    get_or_build_document_store,
)
from domain.documents.chunker import chunk_text
from web.api._errors import NotFound, ValidationError
from web.api.schemas import (
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentSource,
    DocumentUploadResponse,
)

logger = logging.getLogger("tally.web.documents")

v1_router = APIRouter()

_SUPPORTED_EXTENSIONS = frozenset({".md", ".txt"})
_MAX_FILE_SIZE = 1_048_576  # 1 MiB


def _resolve_document_store(request: Request, project_id: int):
    """Resolve project and build a DocumentStore, or raise."""
    from application.rag.document_store import DocumentStore

    registry = request.app.state.project_registry
    row = registry.resolve_by_id(project_id)
    if row is None or row.archived_at:
        raise NotFound(f"project {project_id} not found")
    store = get_or_build_document_store(
        request.app.state.document_store_cache,
        row.name,
        request.app.state.base_path,
    )
    if store is None:
        raise ValidationError(
            "Document store unavailable; check embedding provider",
            details={"project_id": project_id},
        )
    assert isinstance(store, DocumentStore)
    return store


@v1_router.get(
    "/{project_id}/documents",
    response_model=DocumentListResponse,
)
async def list_documents(
    project_id: int,
    request: Request,
) -> DocumentListResponse:
    """List ingested documents for a project."""
    store = _resolve_document_store(request, project_id)
    sources = await asyncio.to_thread(store.list_sources)
    return DocumentListResponse(
        items=[DocumentSource(name=s["name"], chunks=s["chunks"]) for s in sources],
    )


@v1_router.post(
    "/{project_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=201,
)
async def upload_document(
    project_id: int,
    request: Request,
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    """Upload and ingest a .md or .txt file."""
    filename = file.filename or "unnamed"
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

    if ext not in _SUPPORTED_EXTENSIONS:
        exts = ", ".join(sorted(_SUPPORTED_EXTENSIONS))
        raise ValidationError(
            f"Unsupported file type: {ext}. Supported: {exts}",
            details={"filename": filename},
        )

    raw = await file.read()
    if len(raw) > _MAX_FILE_SIZE:
        raise ValidationError(
            f"File exceeds {_MAX_FILE_SIZE // 1024} KiB limit",
            details={"filename": filename, "size": len(raw)},
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(
            "File is not valid UTF-8",
            details={"filename": filename},
        ) from exc

    chunks = chunk_text(text)
    if not chunks:
        raise ValidationError(
            "File is empty or whitespace-only",
            details={"filename": filename},
        )

    store = _resolve_document_store(request, project_id)
    count = await asyncio.to_thread(store.add_chunks, filename, chunks)
    await asyncio.to_thread(_seal_stale_sessions, request, project_id)
    return DocumentUploadResponse(filename=filename, chunks=count)


@v1_router.delete(
    "/{project_id}/documents/{filename:path}",
    response_model=DocumentDeleteResponse,
)
async def delete_document(
    project_id: int,
    filename: str,
    request: Request,
) -> DocumentDeleteResponse:
    """Remove all chunks for a document by filename."""
    store = _resolve_document_store(request, project_id)
    removed = await asyncio.to_thread(store.remove_by_filename, filename)
    if removed == 0:
        raise NotFound(f"no document found: {filename}")
    await asyncio.to_thread(_seal_stale_sessions, request, project_id)
    return DocumentDeleteResponse(filename=filename, chunks_removed=removed)


def _seal_stale_sessions(request: Request, project_id: int) -> None:
    """Seal documents-mode sessions after a store change."""
    from application.chat.sealing import seal_sessions_by_mode
    from factories.persistence import (
        create_chat_session_service,
    )

    try:
        svc = create_chat_session_service(
            request.app.state.project_registry, project_id
        )
        seal_sessions_by_mode(
            project_id,
            mode="documents",
            session_repo=svc.session_repo,
        )
    except Exception:
        logger.warning(
            "document session sealing failed for project %d",
            project_id,
        )
